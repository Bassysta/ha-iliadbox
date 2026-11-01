"""Minimal async client for the Freebox OS API exposed by the Iliadbox."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any

import aiohttp

from .const import APP_ID, APP_NAME, APP_VERSION, DEVICE_NAME

_LOGGER = logging.getLogger(__name__)

TIMEOUT = aiohttp.ClientTimeout(total=10)


class IliadboxError(Exception):
    """Generic API error."""


class IliadboxConnectionError(IliadboxError):
    """The box cannot be reached."""


class IliadboxSSLError(IliadboxConnectionError):
    """The box certificate could not be verified."""


class IliadboxAuthError(IliadboxError):
    """The app token is invalid or was revoked."""


class IliadboxPermissionError(IliadboxError):
    """The app lacks a permission on the box (e.g. 'settings')."""

    def __init__(self, permission: str, host: str) -> None:
        self.permission = permission
        label = PERMISSION_LABELS.get(permission, permission)
        super().__init__(
            f"The box did not allow this action: the \"Home Assistant\" app lacks the "
            f"\"{label}\" permission. To fix it, open http://{host} in a browser, go to "
            f"Access management → Applications → Home Assistant, enable \"{label}\" and "
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
        self.host = host
        self._root = f"{scheme}://{host}:{port}"
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
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise IliadboxConnectionError(f"Cannot reach box: {err}") from err

        major = str(info.get("api_version", "8.0")).split(".")[0]
        base = info.get("api_base_url", "/api/")
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
        self._app_token = result["app_token"]
        _LOGGER.info(
            "Authorization requested (track_id %s): confirm it on the box",
            result["track_id"],
        )
        return result["app_token"], result["track_id"]

    async def authorization_status(self, track_id: int) -> str:
        """Return unknown / pending / timeout / granted / denied."""
        result = await self._request(
            "GET", f"login/authorize/{track_id}", auth=False
        )
        _LOGGER.debug("Authorization %s status: %s", track_id, result["status"])
        return result["status"]

    async def open_session(self) -> None:
        """Open a session using the HMAC of the challenge with the app token."""
        if not self._app_token:
            raise IliadboxAuthError("No app token")
        _LOGGER.debug("Opening session")
        login = await self._request("GET", "login/", auth=False)
        password = hmac.new(
            self._app_token.encode(), login["challenge"].encode(), hashlib.sha1
        ).hexdigest()
        try:
            result = await self._request(
                "POST",
                "login/session/",
                json={"app_id": APP_ID, "password": password},
                auth=False,
            )
        except IliadboxError as err:
            raise IliadboxAuthError(str(err)) from err
        self._session_token = result["session_token"]
        self.permissions = {k for k, v in (result.get("permissions") or {}).items() if v}
        _LOGGER.info(
            "Session opened, permissions: %s", ", ".join(sorted(self.permissions)) or "none"
        )
        if "settings" not in self.permissions:
            _LOGGER.warning(
                "The app lacks the \"Modify settings\" permission: Wi-Fi switch, reboot and "
                "guest Wi-Fi will fail. Enable it on http://%s → Access management → "
                "Applications → Home Assistant",
                self.host,
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
                    await self.open_session()

        headers = {}
        if auth:
            headers["X-Fbx-App-Auth"] = self._session_token
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
                data = await resp.json(content_type=None)
        except aiohttp.ClientSSLError as err:
            raise IliadboxSSLError(f"Certificate check failed: {err}") from err
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise IliadboxConnectionError(f"Request {path} failed: {err}") from err

        if data.get("success"):
            return data.get("result")

        code = data.get("error_code", "")
        _LOGGER.debug("%s %s failed: %s (%s)", method, path, data.get("msg"), code)
        if auth and retry and code in ("auth_required", "invalid_session"):
            _LOGGER.info("Session expired, logging in again")
            self._session_token = None
            return await self._request(method, path, json, auth, retry=False)
        if code == "insufficient_rights":
            # Permissions are fixed when a session opens: if the user granted the
            # permission meanwhile, a new session picks it up
            if auth and retry:
                _LOGGER.debug("Missing permission on %s, retrying with a new session", path)
                self._session_token = None
                return await self._request(method, path, json, auth, retry=False)
            raise IliadboxPermissionError(data.get("missing_right") or "settings", self.host)
        reason = ERROR_MESSAGES.get(code, f"box error \"{code or 'unknown'}\"")
        if code in ("invalid_token", "pending_token", "denied_from_external_ip"):
            raise IliadboxAuthError(reason[0].upper() + reason[1:])
        raise IliadboxError(f"The box refused {method} {path}: {reason}")

    async def get_connection(self) -> dict[str, Any]:
        return await self._request("GET", "connection/")

    async def get_system(self) -> dict[str, Any]:
        return await self._request("GET", "system/")

    async def get_lan_hosts(self) -> list[dict[str, Any]]:
        return await self._request("GET", "lan/browser/pub/") or []

    async def get_wifi_config(self) -> dict[str, Any]:
        return await self._request("GET", "wifi/config/")

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
        aps_by_id = {ap.get("id"): ap.get("status") or {} for ap in aps or []}
        radios = []
        for bss in bss_list or []:
            status = bss.get("status") or {}
            params = (
                bss.get("shared_bss_params")
                if bss.get("use_shared_params")
                else bss.get("bss_params")
            ) or {}
            ap = aps_by_id.get(bss.get("phy_id"), {})
            radios.append(
                {
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
        return await self._request("GET", "wifi/custom_key/") or []

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
        return await self._request(
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

    async def delete_guest_key(self, key_id: int) -> None:
        _LOGGER.info("Deleting guest Wi-Fi access %s", key_id)
        await self._request("DELETE", f"wifi/custom_key/{key_id}")

    async def reboot(self) -> None:
        _LOGGER.warning("Rebooting the box")
        await self._request("POST", "system/reboot/")
