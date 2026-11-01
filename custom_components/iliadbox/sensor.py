"""Sensors for the Iliadbox."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import IliadboxConfigEntry, IliadboxCoordinator
from .entity import IliadboxEntity


@dataclass(frozen=True, kw_only=True)
class IliadboxSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[IliadboxSensorDescription, ...] = (
    IliadboxSensorDescription(
        key="rate_down",
        translation_key="rate_down",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        value_fn=lambda d: d["connection"].get("rate_down"),
    ),
    IliadboxSensorDescription(
        key="rate_up",
        translation_key="rate_up",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        value_fn=lambda d: d["connection"].get("rate_up"),
    ),
    IliadboxSensorDescription(
        key="bandwidth_down",
        translation_key="bandwidth_down",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        value_fn=lambda d: d["connection"].get("bandwidth_down"),
    ),
    IliadboxSensorDescription(
        key="bandwidth_up",
        translation_key="bandwidth_up",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        value_fn=lambda d: d["connection"].get("bandwidth_up"),
    ),
    IliadboxSensorDescription(
        key="bytes_down",
        translation_key="bytes_down",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=lambda d: d["connection"].get("bytes_down"),
    ),
    IliadboxSensorDescription(
        key="bytes_up",
        translation_key="bytes_up",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=lambda d: d["connection"].get("bytes_up"),
    ),
    IliadboxSensorDescription(
        key="ipv4",
        translation_key="ipv4",
        value_fn=lambda d: d["connection"].get("ipv4"),
    ),
    IliadboxSensorDescription(
        key="ipv6",
        translation_key="ipv6",
        entity_registry_enabled_default=False,
        value_fn=lambda d: d["connection"].get("ipv6"),
    ),
    IliadboxSensorDescription(
        key="media",
        translation_key="media",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["connection"].get("media"),
    ),
    IliadboxSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["system"].get("uptime_val"),
    ),
)


def _hw_sensors(system: dict[str, Any]) -> list[dict[str, Any]]:
    """Temperature sensors: list form (API v8+) or legacy temp_* keys."""
    if isinstance(system.get("sensors"), list):
        return system["sensors"]
    return [
        {"id": k, "name": k, "value": v}
        for k, v in system.items()
        if k.startswith("temp_")
    ]


def _english_name(sensor_id: str) -> str:
    """The box localizes sensor names: derive English ones from the ids."""
    if sensor_id.startswith("temp_"):
        return f"Temperature {sensor_id[5:].upper()}"
    if match := re.match(r"fan(\d+)", sensor_id):
        return f"Fan {int(match.group(1)) + 1}"
    return sensor_id


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        IliadboxSensor(coordinator, desc) for desc in SENSORS
    ]
    entities.extend(
        IliadboxTemperatureSensor(coordinator, s["id"], _english_name(s["id"]))
        for s in _hw_sensors(coordinator.data["system"])
    )
    entities.extend(
        IliadboxFanSensor(coordinator, f["id"], _english_name(f["id"]))
        for f in coordinator.data["system"].get("fans", [])
    )
    async_add_entities(entities)


class IliadboxSensor(IliadboxEntity, SensorEntity):
    entity_description: IliadboxSensorDescription

    def __init__(
        self, coordinator: IliadboxCoordinator, description: IliadboxSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)


class IliadboxTemperatureSensor(IliadboxEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: IliadboxCoordinator, sensor_id: str, name: str) -> None:
        super().__init__(coordinator, sensor_id)
        self._sensor_id = sensor_id
        self._attr_name = name

    @property
    def native_value(self) -> Any:
        for s in _hw_sensors(self.coordinator.data["system"]):
            if s["id"] == self._sensor_id:
                return s.get("value")
        return None


class IliadboxFanSensor(IliadboxEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = REVOLUTIONS_PER_MINUTE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:fan"

    def __init__(self, coordinator: IliadboxCoordinator, fan_id: str, name: str) -> None:
        super().__init__(coordinator, fan_id)
        self._fan_id = fan_id
        self._attr_name = name

    @property
    def native_value(self) -> Any:
        for f in self.coordinator.data["system"].get("fans", []):
            if f["id"] == self._fan_id:
                return f.get("value")
        return None
