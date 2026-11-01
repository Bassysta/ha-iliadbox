"""LAN device trackers for the Iliadbox: one HA device per host seen by the box."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import IliadboxConfigEntry, IliadboxCoordinator

_LOGGER = logging.getLogger(__name__)


@callback
def _enable_trackers_disabled_by_integration(hass: HomeAssistant, entry: IliadboxConfigEntry) -> None:
    """Before 0.6.0 trackers of unknown devices were created disabled: enable them.

    Trackers disabled by the user are left alone.
    """
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            reg_entry.domain == "device_tracker"
            and reg_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        ):
            registry.async_update_entity(reg_entry.entity_id, disabled_by=None)
            _LOGGER.info("Enabled tracker %s", reg_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    _enable_trackers_disabled_by_integration(hass, entry)
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
    """A host seen by the box on the LAN, with its own device."""

    _attr_has_entity_name = True
    _attr_name = None  # the entity takes the device name
    # ScannerEntity defaults to disabled; every LAN device is wanted for automations
    _attr_entity_registry_enabled_default = True

    def __init__(self, coordinator: IliadboxCoordinator, mac: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        box_id = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{box_id}_{mac}"
        host = self._host
        # default_* so a device already created by another integration
        # (same MAC) keeps its own name and manufacturer
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, mac)},
            default_name=host.get("primary_name") or mac,
            default_manufacturer=host.get("vendor_name") or None,
            default_model=host.get("host_type") or None,
            via_device=(DOMAIN, box_id),
        )

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
