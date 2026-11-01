"""Binary sensors for the Iliadbox."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IliadboxConfigEntry
from .entity import IliadboxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([IliadboxWanConnected(entry.runtime_data, "wan_connected")])


class IliadboxWanConnected(IliadboxEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "wan_connected"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data["connection"].get("state") == "up"
