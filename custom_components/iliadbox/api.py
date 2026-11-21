"""Minimal async client for the Freebox OS API exposed by the Iliadbox."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from ipaddress import ip_address
import logging
import re
import time
from typing import Any

import aiohttp
from yarl import URL

from .const import APP_ID, APP_NAME, APP_VERSION, DEVICE_NAME

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)


class IliadboxError(Exception):
    """Generic API error."""


class IliadboxConnectionError(IliadboxError):
    """The box cannot be reached."""


class IliadboxUnsupportedError(IliadboxError):
    """The endpoint is not supported by this box."""


class IliadboxSSLError(IliadboxConnectionError):
    """The box certificate could not be verified."""


class IliadboxAuthError(IliadboxError):
    """The app token is invalid or was revoked."""


class IliadboxPermissionError(IliadboxError):
    """The app lacks a permission on the box (e.g. 'settings')."""

    def __init__(self, permission: str, url: str) -> None:
        self.permission = permission
        label = PERMISSION_LABELS.get(permission, permission)
        super().__init__(
            f'The box did not allow this action: the "Home Assistant" app lacks the '
            f'"{label}" permission. To fix it, open {url} in a browser, go to '
            f'Access management → Applications → Home Assistant, enable "{label}" and '
            f"save, then retry (no restart needed)."
        )


# Labels shown by the box web interface for the API permission names
PERMISSION_LABELS = {
    "settings": "Modify settings",
    "explorer": "Access to files",
    "calls": "Access to calls",
    "contacts": "Access to contacts",
    "downloader": "Access to downloads",
    "parental": "Parental control",
    "pvr": "Recordings",
    "tv": "TV",
    "camera": "Cameras",
    "home": "Home automation",
    "player": "Player control",
    "vm": "Virtual machines",
}

# English text for the box error codes. The box also sends a "msg", but it is
# localized in the box language (e.g. Italian): it is only logged.
ERROR_MESSAGES = {
    "auth_required": "the session expired",
    "invalid_token": "the authorization of Home Assistant was revoked on the box",
    "pending_token": "the authorization request was not confirmed on the box yet",
    "denied_from_external_ip": "the box refuses requests from outside its local network",
    "new_apps_denied": "the box does not accept new applications (check Access management)",
    "apps_denied": "the box has API access disabled for applications",
    "ratelimited": "too many requests, retry in a few seconds",
    "invalid_request": "the box rejected the request as invalid",
    "inval": "the box rejected the values sent",
    "internal_error": "internal error on the box",
    "busy": "the box is busy, retry in a few seconds",
    "noent": "the requested item does not exist on the box",
    "exists": "the item already exists on the box",
    "nodev": "the box does not have this feature",
}


def normalize_host(host: str) -> str:
    """Accept a hostname or IP literal, never a URL, credentials or path."""
    host = host.strip().removeprefix("[").removesuffix("]")
    try:
        return str(ip_address(host))
    except ValueError:
        if (
            not host
            or len(host) > 253
            or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host)
        ):
            raise ValueError("Enter a hostname or IP address without a scheme or path") from None
        if any(
            not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
            for part in host.split(".")
        ):
            raise ValueError("Invalid hostname")
        return host.lower()


def object_result(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IliadboxError(f"Invalid response structure for {path}")
    return value


def list_result(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise IliadboxError(f"Invalid response structure for {path}")
    return value


class IliadboxClient:
    """Talks to the Iliadbox (Freebox OS API)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        use_ssl: bool = False,
        app_token: str | None = None,
        verify_ssl: bool = False,
    ) -> None:
        self._session = session
        scheme = "https" if use_ssl else "http"
        self.host = normalize_host(host)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        self._root = str(URL.build(scheme=scheme, host=self.host, port=port))
        self.configuration_url = self._root
        self.permissions_checked_at = 0.0
        # Permissions granted to the app, read when the session opens
        self.permissions: set[str] = set()
        # False skips certificate checks (self-signed or name not matching the IP)
        self._ssl: bool = use_ssl and verify_ssl
        self._app_token = app_token
        self._session_token: str | None = None
        self._base_url: str | None = None
        self._login_lock = asyncio.Lock()
        self.info: dict[str, Any] = {}

    async def discover(self) -> dict[str, Any]:
        """Read /api_version and build the versioned base URL."""
        _LOGGER.debug(
            "Discovering box at %s (certificate verification %s)",
            self._root,
            "on" if self._ssl else "off",
        )
        try:
            async with self._session.get(
                f"{self._root}/api_version", timeout=TIMEOUT, ssl=self._ssl
            ) as resp:
                resp.raise_for_status()
                info = await resp.json(content_type=None)
        except aiohttp.ClientSSLError as err:
            raise IliadboxSSLError(f"Certificate check failed: {err}") from err
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise IliadboxConnectionError(f"Cannot reach box: {err}") from err

        info = object_result(info, "api_version")
        version = info.get("api_version")
        base = info.get("api_base_url")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
            raise IliadboxError("Invalid API version")
        if not isinstance(base, str) or not re.fullmatch(r"/[a-zA-Z0-9_/]+/", base):
            raise IliadboxError("Invalid API base path")
        major = version.split(".")[0]
        self._base_url = f"{self._root}{base}v{major}/"
        self.info = info
        _LOGGER.debug(
            "Found %s (%s), API %s, base URL %s",
            info.get("box_model_name"),
            info.get("device_type"),
            info.get("api_version"),
            self._base_url,
        )
        return info

    async def request_authorization(self) -> tuple[str, int]:
        """Ask the box for a new app token; it must be confirmed on the box."""
        result = await self._request(
            "POST",
            "login/authorize/",
            json={
                "app_id": APP_ID,
                "app_name": APP_NAME,
                "app_version": APP_VERSION,
                "device_name": DEVICE_NAME,
            },
            auth=False,
        )
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("app_token"), str)
            or not isinstance(result.get("track_id"), int)
        ):
            raise IliadboxError("Invalid authorization response")
        self._app_token = result["app_token"]
        _LOGGER.info(
            "Authorization requested (track_id %s): confirm it on the box",
            result["track_id"],
        )
        return result["app_token"], result["track_id"]

    async def authorization_status(self, track_id: int) -> str:
        """Return unknown / pending / timeout / granted / denied."""
        result = await self._request("GET", f"login/authorize/{track_id}", auth=False)
        if not isinstance(result, dict) or result.get("status") not in {
            "unknown",
            "pending",
            "timeout",
            "granted",
            "denied",
        }:
            raise IliadboxError("Invalid authorization status")
        _LOGGER.debug("Authorization %s status: %s", track_id, result["status"])
        return result["status"]

    async def open_session(self) -> None:
        """Open a session using the HMAC of the challenge with the app token."""
        async with self._login_lock:
            await self._open_session()

    async def _open_session(self) -> None:
        """Open a session while holding the login lock."""
        if not self._app_token:
            raise IliadboxAuthError("No app token")
        _LOGGER.debug("Opening session")
        login = await self._request("GET", "login/", auth=False)
        if not isinstance(login, dict) or not isinstance(login.get("challenge"), str):
            raise IliadboxError("Invalid login challenge")
        password = hmac.new(
            self._app_token.encode(), login["challenge"].encode(), hashlib.sha1
        ).hexdigest()
        result = await self._request(
            "POST",
            "login/session/",
            json={"app_id": APP_ID, "password": password},
            auth=False,
        )
        if not isinstance(result, dict) or not isinstance(result.get("session_token"), str):
            raise IliadboxError("Invalid session response")
        if not isinstance(result.get("permissions", {}), dict):
            raise IliadboxError("Invalid session permissions")
        self.permissions_checked_at = time.monotonic()
        self._session_token = result["session_token"]
        self.permissions = {k for k, v in (result.get("permissions") or {}).items() if v}
        _LOGGER.info(
            "Session opened, permissions: %s",
            ", ".join(sorted(self.permissions)) or "none",
        )

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        auth: bool = True,
        retry: bool = True,
    ) -> Any:
        if self._base_url is None:
            await self.discover()
        if auth and self._session_token is None:
            async with self._login_lock:
                if self._session_token is None:
                    await self._open_session()

        request_token = self._session_token
        headers = {}
        if auth:
            headers["X-Fbx-App-Auth"] = request_token
        _LOGGER.debug("%s %s", method, path)
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                json=json,
                headers=headers,
                timeout=TIMEOUT,
                ssl=self._ssl,
            ) as resp:
                # Preserve structured API errors (including auth) on 4xx responses.
                if resp.status == 429 or resp.status >= 500:
                    raise IliadboxConnectionError(f"HTTP {resp.status} on {path}")
                data = await resp.json(content_type=None)
                if not isinstance(data, dict) or not isinstance(data.get("success"), bool):
                    raise IliadboxError(f"Invalid response structure for {path}")
                if data["success"]:
                    resp.raise_for_status()
        except aiohttp.ClientSSLError as err:
            raise IliadboxSSLError(f"Certificate check failed: {err}") from err
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise IliadboxConnectionError(f"Request {path} failed: {err}") from err

        if data.get("success"):
            return data.get("result")

        code = data.get("error_code", "")
        if not isinstance(code, str):
            raise IliadboxError(f"Invalid error response for {path}")
        _LOGGER.debug("%s %s failed: %s", method, path, code)
        if auth and retry and code in ("auth_required", "invalid_session"):
            _LOGGER.info("Session expired, logging in again")
            if self._session_token == request_token:
                self._session_token = None
            return await self._request(method, path, json, auth, retry=False)
        if code == "insufficient_rights":
            # Permissions are fixed when a session opens: if the user granted the
            # permission meanwhile, a new session picks it up
            if auth and retry:
                _LOGGER.debug("Missing permission on %s, retrying with a new session", path)
                if self._session_token == request_token:
                    self._session_token = None
                return await self._request(method, path, json, auth, retry=False)
            raise IliadboxPermissionError(
                data.get("missing_right") or "settings", self.configuration_url
            )
        reason = ERROR_MESSAGES.get(code, f'box error "{code or "unknown"}"')
        if code in (
            "invalid_token",
            "pending_token",
            "auth_required",
            "invalid_session",
        ):
            raise IliadboxAuthError(reason[0].upper() + reason[1:])
        if code == "nodev":
            raise IliadboxUnsupportedError(reason)
        raise IliadboxError(f"The box refused {method} {path}: {reason}")

    async def get_connection(self) -> dict[str, Any]:
        return object_result(await self._request("GET", "connection/"), "connection/")

    async def get_system(self) -> dict[str, Any]:
        return object_result(await self._request("GET", "system/"), "system/")

    async def get_lan_hosts(self) -> list[dict[str, Any]]:
        hosts = list_result(await self._request("GET", "lan/browser/pub/"), "lan/browser/pub/")
        for host in hosts:
            ident = host.get("l2ident")
            if not isinstance(ident, dict) or not isinstance(ident.get("id"), str):
                raise IliadboxError("Invalid LAN host identity")
        return hosts

    async def get_wifi_config(self) -> dict[str, Any]:
        return object_result(await self._request("GET", "wifi/config/"), "wifi/config/")

    async def set_wifi_enabled(self, enabled: bool) -> None:
        _LOGGER.info("Turning Wi-Fi %s", "on" if enabled else "off")
        await self._request("PUT", "wifi/config/", json={"enabled": enabled})

    async def get_wifi_radios(self) -> list[dict[str, Any]]:
        """One summary per radio, merging BSS and AP status.

        The BSS payload also holds the Wi-Fi keys: only the fields listed here
        are kept, so keys never reach Home Assistant state or logs.
        """
        bss_list, aps = await asyncio.gather(
            self._request("GET", "wifi/bss/"), self._request("GET", "wifi/ap/")
        )
        bss_list = list_result(bss_list, "wifi/bss/")
        aps = list_result(aps, "wifi/ap/")
        aps_by_id = {
            ap.get("id"): object_result(ap.get("status") or {}, "wifi/ap/status")
            for ap in aps or []
        }
        radios = []
        for bss in bss_list or []:
            status = object_result(bss.get("status") or {}, "wifi/bss/status")
            params = (
                bss.get("shared_bss_params")
                if bss.get("use_shared_params")
                else bss.get("bss_params")
            ) or {}
            params = object_result(params, "wifi/bss/params")
            ap = aps_by_id.get(bss.get("phy_id"), {})
            radios.append(
                {
                    "id": bss.get("id"),
                    "phy_id": bss.get("phy_id"),
                    "band": status.get("band"),
                    "state": status.get("state"),
                    "ssid": params.get("ssid"),
                    "hidden": params.get("hide_ssid"),
                    "encryption": params.get("encryption"),
                    "clients": status.get("sta_count"),
                    "guest_ssid": status.get("custom_key_ssid"),
                    "channel": ap.get("primary_channel"),
                    "channel_width": ap.get("channel_width"),
                }
            )
        return radios

    async def get_guest_keys(self) -> list[dict[str, Any]]:
        keys = list_result(await self._request("GET", "wifi/custom_key/"), "wifi/custom_key/")
        for key in keys:
            if not isinstance(key.get("id"), int) or not isinstance(key.get("params"), dict):
                raise IliadboxError("Invalid guest access")
            remaining = key.get("remaining")
            if remaining is not None and (
                isinstance(remaining, bool) or not isinstance(remaining, (int, float))
            ):
                raise IliadboxError("Invalid guest expiry")
        return keys

    async def create_guest_key(
        self,
        description: str,
        key: str,
        duration: int,
        max_use_count: int,
        access_type: str,
    ) -> dict[str, Any]:
        """Create a guest access. duration in seconds, max_use_count 0 = unlimited."""
        _LOGGER.info(
            "Creating guest Wi-Fi access '%s' (%ss, %s, max devices %s)",
            description,
            duration,
            access_type,
            max_use_count or "unlimited",
        )
        result = await self._request(
            "POST",
            "wifi/custom_key/",
            json={
                "description": description,
                "key": key,
                "duration": duration,
                "max_use_count": max_use_count,
                "access_type": access_type,
            },
        )
        if not isinstance(result, dict) or not isinstance(result.get("id"), int):
            raise IliadboxError(
                "Invalid guest creation response; check existing accesses before retrying"
            )
        return result

    async def delete_guest_key(self, key_id: int) -> None:
        _LOGGER.info("Deleting guest Wi-Fi access %s", key_id)
        await self._request("DELETE", f"wifi/custom_key/{key_id}")

    async def reboot(self) -> None:
        _LOGGER.warning("Rebooting the box")
        await self._request("POST", "system/reboot/")
