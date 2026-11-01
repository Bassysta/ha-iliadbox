"""Data update coordinator for the Iliadbox."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IliadboxAuthError, IliadboxClient, IliadboxError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type IliadboxConfigEntry = ConfigEntry[IliadboxCoordinator]


class IliadboxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls connection, system, LAN hosts and Wi-Fi state."""

    config_entry: IliadboxConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IliadboxConfigEntry, client: IliadboxClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

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

        # Guest Wi-Fi is optional: a failure here must not mark the box unavailable
        try:
            guest_keys, guest_ssid = await asyncio.gather(
                self.client.get_guest_keys(), self.client.get_guest_ssid()
            )
        except IliadboxError as err:
            _LOGGER.debug("Guest Wi-Fi data unavailable: %s", err)
            guest_keys, guest_ssid = [], None

        connection = connection or {}
        hosts_by_mac = {
            h["l2ident"]["id"].lower(): h
            for h in hosts
            if h.get("l2ident", {}).get("type") == "mac_address"
        }
        self._log_changes(connection, wifi or {}, hosts_by_mac)
        _LOGGER.debug(
            "Update done: WAN %s, %d/%d hosts active, Wi-Fi %s, %d guest accesses",
            connection.get("state"),
            sum(1 for h in hosts_by_mac.values() if h.get("active")),
            len(hosts_by_mac),
            "on" if (wifi or {}).get("enabled") else "off",
            len(guest_keys),
        )
        return {
            "connection": connection,
            "system": system or {},
            "hosts": hosts_by_mac,
            "wifi": wifi or {},
            "guest": {"ssid": guest_ssid, "keys": guest_keys},
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
