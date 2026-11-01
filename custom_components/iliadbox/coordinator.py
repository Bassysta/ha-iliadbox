"""Data update coordinator for the Iliadbox."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IliadboxAuthError, IliadboxClient, IliadboxError
from .const import CONF_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type IliadboxConfigEntry = ConfigEntry[IliadboxCoordinator]


class IliadboxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls connection, system, LAN hosts and Wi-Fi state."""

    config_entry: IliadboxConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IliadboxConfigEntry, client: IliadboxClient
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.hidden_hosts = 0
        _LOGGER.debug("Polling the box every %s seconds", interval)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            connection, system, hosts, wifi = await asyncio.gather(
                self.client.get_connection(),
                self.client.get_system(),
                self.client.get_lan_hosts(),
                self.client.get_wifi_config(),
            )
        except IliadboxAuthError as err:
            _LOGGER.error("Box rejected the app token: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        except IliadboxError as err:
            # DataUpdateCoordinator logs this once and logs again on recovery
            raise UpdateFailed(str(err)) from err

        # Wi-Fi radios and guest accesses are optional: a failure here must not
        # mark the box unavailable
        try:
            guest_keys, radios = await asyncio.gather(
                self.client.get_guest_keys(), self.client.get_wifi_radios()
            )
        except IliadboxError as err:
            _LOGGER.debug("Wi-Fi radio or guest data unavailable: %s", err)
            guest_keys, radios = [], []
        guest_ssid = next((r["guest_ssid"] for r in radios if r.get("guest_ssid")), None)

        connection = connection or {}
        # The box remembers every device ever seen: keep the connected ones and
        # those active within max_age_days (0 = keep all)
        max_age = self.config_entry.options.get(CONF_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS)
        oldest = time.time() - max_age * 86400
        hosts_by_mac = {
            h["l2ident"]["id"].lower(): h
            for h in hosts
            if h.get("l2ident", {}).get("type") == "mac_address"
            and (not max_age or h.get("active") or (h.get("last_activity") or 0) >= oldest)
        }
        self.hidden_hosts = len(hosts) - len(hosts_by_mac)
        self._log_changes(connection, wifi or {}, hosts_by_mac)
        _LOGGER.debug(
            "Update done: WAN %s, %d/%d hosts active (%d older than %s days hidden), "
            "Wi-Fi %s, %d guest accesses",
            connection.get("state"),
            sum(1 for h in hosts_by_mac.values() if h.get("active")),
            len(hosts_by_mac),
            self.hidden_hosts,
            max_age or "∞",
            "on" if (wifi or {}).get("enabled") else "off",
            len(guest_keys),
        )
        return {
            "connection": connection,
            "system": system or {},
            "hosts": hosts_by_mac,
            "wifi": wifi or {},
            "guest": {"ssid": guest_ssid, "keys": guest_keys},
            "radios": {r["band"]: r for r in radios if r.get("band")},
        }

    def _log_changes(
        self,
        connection: dict[str, Any],
        wifi: dict[str, Any],
        hosts: dict[str, dict[str, Any]],
    ) -> None:
        """Log WAN, Wi-Fi and host presence transitions at info level."""
        if not self.data:
            return
        old_state = self.data["connection"].get("state")
        if old_state != connection.get("state"):
            _LOGGER.info("WAN connection changed: %s -> %s", old_state, connection.get("state"))
        if self.data["wifi"].get("enabled") != wifi.get("enabled"):
            _LOGGER.info("Wi-Fi turned %s", "on" if wifi.get("enabled") else "off")
        for mac, host in hosts.items():
            old = self.data["hosts"].get(mac)
            if old is None or bool(old.get("active")) != bool(host.get("active")):
                _LOGGER.info(
                    "Device %s (%s) %s",
                    host.get("primary_name") or mac,
                    mac,
                    "connected" if host.get("active") else "disconnected",
                )

    @property
    def device_info(self) -> DeviceInfo:
        system = (self.data or {}).get("system", {})
        info = self.client.info
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.unique_id or self.config_entry.entry_id)},
            manufacturer="Iliad",
            model=info.get("box_model_name") or info.get("box_model") or "Iliadbox",
            name=self.config_entry.title,
            sw_version=system.get("firmware_version"),
            serial_number=system.get("serial"),
        )
