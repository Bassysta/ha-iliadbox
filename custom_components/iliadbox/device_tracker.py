"""LAN device trackers for the Iliadbox."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import IliadboxConfigEntry, IliadboxCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    tracked: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [mac for mac in coordinator.data["hosts"] if mac not in tracked]
        if new:
            _LOGGER.debug("Adding %d device trackers", len(new))
            tracked.update(new)
            async_add_entities(IliadboxTracker(coordinator, mac) for mac in new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class IliadboxTracker(CoordinatorEntity[IliadboxCoordinator], ScannerEntity):
    """A host seen by the box on the LAN."""

    def __init__(self, coordinator: IliadboxCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{mac}"
        host = self._host
        self._attr_name = host.get("primary_name") or mac

    @property
    def _host(self) -> dict[str, Any]:
        return self.coordinator.data["hosts"].get(self._mac, {})

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def hostname(self) -> str | None:
        return self._host.get("primary_name")

    @property
    def ip_address(self) -> str | None:
        for l3 in self._host.get("l3connectivities", []):
            if l3.get("af") == "ipv4" and l3.get("active"):
                return l3.get("addr")
        return None

    @property
    def is_connected(self) -> bool:
        return bool(self._host.get("active"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        host = self._host
        last = host.get("last_activity")
        return {
            "vendor": host.get("vendor_name"),
            "host_type": host.get("host_type"),
            "last_activity": dt_util.utc_from_timestamp(last).isoformat() if last else None,
        }
