"""Base entities for the Iliadbox: the box itself and the LAN devices it sees."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import IliadboxConfigEntry, IliadboxCoordinator


class IliadboxEntity(CoordinatorEntity[IliadboxCoordinator]):
    """Entity attached to the box device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IliadboxCoordinator, key: str) -> None:
        super().__init__(coordinator)
        base = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{base}_{key}"
        self._attr_device_info = coordinator.device_info


def box_id(coordinator: IliadboxCoordinator) -> str:
    return coordinator.config_entry.unique_id or coordinator.config_entry.entry_id


def host_display_name(host: dict[str, Any], mac: str) -> str:
    """Best name for a LAN host.

    Most hosts remembered by the box have no name: fall back to the names the
    device announced (DHCP, mDNS), then to vendor + end of the MAC, which is
    still unique and readable. The bare MAC is the last resort.
    """
    if host.get("primary_name"):
        return host["primary_name"]
    for item in host.get("names") or []:
        if item.get("name"):
            return item["name"]
    dhcp = ((host.get("info") or {}).get("dhcp") or {}).get("Host Name")
    if dhcp:
        return dhcp
    if host.get("vendor_name"):
        return f"{host['vendor_name'].split(',')[0].strip()} {mac[-5:].upper()}"
    return mac.upper()


def host_device_info(coordinator: IliadboxCoordinator, mac: str) -> DeviceInfo:
    """Device of a LAN host, matched by MAC.

    default_* so a device already created by another integration with the same
    MAC keeps its own name and manufacturer.
    """
    host = coordinator.data["hosts"].get(mac, {})
    return DeviceInfo(
        connections={(CONNECTION_NETWORK_MAC, mac)},
        default_name=host_display_name(host, mac),
        default_manufacturer=host.get("vendor_name") or None,
        default_model=host.get("host_type") or None,
        via_device=(DOMAIN, box_id(coordinator)),
    )


class IliadboxHostEntity(CoordinatorEntity[IliadboxCoordinator]):
    """Entity attached to the device of a LAN host."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: IliadboxCoordinator,
        mac: str,
        description: EntityDescription,
        enabled: bool,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._mac = mac
        self._attr_unique_id = f"{box_id(coordinator)}_{mac}_{description.key}"
        self._attr_device_info = host_device_info(coordinator, mac)
        self._attr_entity_registry_enabled_default = enabled

    @property
    def host(self) -> dict[str, Any]:
        return self.coordinator.data["hosts"].get(self._mac, {})

    @property
    def available(self) -> bool:
        return super().available and self._mac in self.coordinator.data["hosts"]


def add_entities_for_new_hosts(
    entry: IliadboxConfigEntry,
    factory: Callable[[str, bool], list[Any]],
    async_add_entities: Callable[[list[Any]], None],
) -> None:
    """Call factory(mac, active) for every host not seen yet, now and on each update."""
    coordinator = entry.runtime_data
    seen: set[str] = set()

    @callback
    def _add_new() -> None:
        hosts = coordinator.data["hosts"]
        # Hosts hidden by max_age_days had their device removed: forget them so
        # their entities are created again if they come back
        seen.intersection_update(hosts)
        entities: list[Any] = []
        for mac, host in hosts.items():
            if mac not in seen:
                seen.add(mac)
                entities.extend(factory(mac, bool(host.get("active"))))
        if entities:
            async_add_entities(entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
