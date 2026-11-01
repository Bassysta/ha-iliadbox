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
        self._root = f"{scheme}://{host}:{port}"
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
        granted = [k for k, v in (result.get("permissions") or {}).items() if v]
        _LOGGER.info("Session opened, permissions: %s", ", ".join(sorted(granted)) or "none")
        if "settings" not in granted:
            _LOGGER.info(
                "The app lacks the 'settings' permission: Wi-Fi switch and reboot will fail"
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
        if code in ("invalid_token", "pending_token", "denied_from_external_ip"):
            raise IliadboxAuthError(data.get("msg", code))
        raise IliadboxError(f"{path}: {data.get('msg', code)} ({code})")

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
