"""Binary sensors for the Iliadbox: box, Wi-Fi radios and LAN devices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IliadboxConfigEntry, IliadboxCoordinator
from .entity import IliadboxEntity, IliadboxHostEntity, add_entities_for_new_hosts
from .sensor import BAND_LABELS


@dataclass(frozen=True, kw_only=True)
class IliadboxBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


# Keys are part of the unique IDs: never rename them
BINARY_SENSORS: tuple[IliadboxBinarySensorDescription, ...] = (
    IliadboxBinarySensorDescription(
        key="wan_connected",
        translation_key="wan_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda d: d["connection"].get("state") == "up",
    ),
    IliadboxBinarySensorDescription(
        key="wifi_power_saving",
        translation_key="wifi_power_saving",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["wifi"].get("power_saving"),
    ),
    IliadboxBinarySensorDescription(
        key="box_authenticated",
        translation_key="box_authenticated",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d["system"].get("box_authenticated"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        IliadboxBinarySensor(coordinator, desc) for desc in BINARY_SENSORS
    ]
    entities.extend(IliadboxRadioActive(coordinator, band) for band in coordinator.data["radios"])
    async_add_entities(entities)

    # Always enabled: presence automations need it for every device
    add_entities_for_new_hosts(
        entry,
        lambda mac, active: [IliadboxHostConnected(coordinator, mac, HOST_CONNECTED, True)],
        async_add_entities,
    )


class IliadboxBinarySensor(IliadboxEntity, BinarySensorEntity):
    entity_description: IliadboxBinarySensorDescription

    def __init__(
        self, coordinator: IliadboxCoordinator, description: IliadboxBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


class IliadboxRadioActive(IliadboxEntity, BinarySensorEntity):
    """A Wi-Fi radio (2.4 / 5 GHz) is broadcasting."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_translation_key = "radio_active"

    def __init__(self, coordinator: IliadboxCoordinator, band: str) -> None:
        super().__init__(coordinator, f"radio_{band.lower()}_active")
        self._band = band
        self._attr_translation_placeholders = {"band": BAND_LABELS.get(band, band)}

    @property
    def available(self) -> bool:
        return super().available and self._band in self.coordinator.data["radios"]

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["radios"].get(self._band, {}).get("state") == "active"


HOST_CONNECTED = BinarySensorEntityDescription(
    key="connected",
    translation_key="host_connected",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
)


class IliadboxHostConnected(IliadboxHostEntity, BinarySensorEntity):
    """The box reports the LAN device as connected."""

    @property
    def is_on(self) -> bool:
        return bool(self.host.get("active"))
