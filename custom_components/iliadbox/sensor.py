"""Sensors for the Iliadbox: box, Wi-Fi radios, guest accesses and LAN devices."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import IliadboxConfigEntry, IliadboxCoordinator
from .entity import IliadboxEntity, IliadboxHostEntity, add_entities_for_new_hosts


def _ts(value: int | None) -> datetime | None:
    return dt_util.utc_from_timestamp(value) if value else None


def _port_range(value: list[int] | None) -> str | None:
    return f"{value[0]}-{value[1]}" if value and len(value) == 2 else None


@dataclass(frozen=True, kw_only=True)
class IliadboxSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


# Keys are part of the unique IDs: never rename them
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
    IliadboxSensorDescription(
        key="connection_state",
        translation_key="connection_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["connection"].get("state"),
    ),
    IliadboxSensorDescription(
        key="connection_type",
        translation_key="connection_type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["connection"].get("type"),
    ),
    IliadboxSensorDescription(
        key="ipv4_port_range",
        translation_key="ipv4_port_range",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _port_range(d["connection"].get("ipv4_port_range")),
    ),
    IliadboxSensorDescription(
        key="firmware",
        translation_key="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["system"].get("firmware_version"),
    ),
    IliadboxSensorDescription(
        key="serial",
        translation_key="serial",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d["system"].get("serial"),
    ),
    IliadboxSensorDescription(
        key="mac",
        translation_key="mac",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d["system"].get("mac"),
    ),
    IliadboxSensorDescription(
        key="board",
        translation_key="board",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d["system"].get("board_name"),
    ),
    IliadboxSensorDescription(
        key="disk_status",
        translation_key="disk_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d["system"].get("disk_status"),
    ),
    IliadboxSensorDescription(
        key="wifi_mac_filter",
        translation_key="wifi_mac_filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d["wifi"].get("mac_filter_state"),
    ),
    IliadboxSensorDescription(
        key="guest_ssid",
        translation_key="guest_ssid",
        value_fn=lambda d: d["guest"]["ssid"],
    ),
    IliadboxSensorDescription(
        key="connected_devices",
        translation_key="connected_devices",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: sum(1 for h in d["hosts"].values() if h.get("active")),
    ),
    IliadboxSensorDescription(
        key="known_devices",
        translation_key="known_devices",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: len(d["hosts"]),
    ),
    IliadboxSensorDescription(
        key="wifi_clients",
        translation_key="wifi_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (
            sum(r.get("clients") or 0 for r in d["radios"].values()) if d["radios"] else None
        ),
    ),
)


# Radio sensors: one set per band reported by the box ("2G4", "5G", ...)
BAND_LABELS = {"2G4": "2.4 GHz", "5G": "5 GHz", "6G": "6 GHz", "60G": "60 GHz"}


@dataclass(frozen=True, kw_only=True)
class IliadboxRadioSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


RADIO_SENSORS: tuple[IliadboxRadioSensorDescription, ...] = (
    IliadboxRadioSensorDescription(
        key="clients",
        translation_key="radio_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r.get("clients"),
    ),
    IliadboxRadioSensorDescription(
        key="ssid",
        translation_key="radio_ssid",
        value_fn=lambda r: r.get("ssid"),
    ),
    IliadboxRadioSensorDescription(
        key="channel",
        translation_key="radio_channel",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda r: r.get("channel"),
    ),
    IliadboxRadioSensorDescription(
        key="channel_width",
        translation_key="radio_channel_width",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        value_fn=lambda r: int(r["channel_width"]) if r.get("channel_width") else None,
    ),
    IliadboxRadioSensorDescription(
        key="encryption",
        translation_key="radio_encryption",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda r: r.get("encryption"),
    ),
)


# LAN host sensors. Wi-Fi fields exist only while the host is connected.
HOST_BANDS = {"2d4g": "2.4 GHz", "5g": "5 GHz", "6g": "6 GHz"}


def _ap(host: dict[str, Any]) -> dict[str, Any]:
    return host.get("access_point") or {}


def _wifi(host: dict[str, Any]) -> dict[str, Any]:
    return _ap(host).get("wifi_information") or {}


def _host_ip(host: dict[str, Any]) -> str | None:
    l3 = host.get("l3connectivities") or []
    for item in l3:
        if item.get("af") == "ipv4" and item.get("active"):
            return item.get("addr")
    return next((i.get("addr") for i in l3 if i.get("af") == "ipv4"), None)


@dataclass(frozen=True, kw_only=True)
class IliadboxHostSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


HOST_SENSORS: tuple[IliadboxHostSensorDescription, ...] = (
    IliadboxHostSensorDescription(
        key="ip",
        translation_key="host_ip",
        value_fn=_host_ip,
    ),
    IliadboxHostSensorDescription(
        key="link",
        translation_key="host_link",
        value_fn=lambda h: _ap(h).get("connectivity_type") if h.get("active") else None,
    ),
    IliadboxHostSensorDescription(
        key="wifi_signal",
        translation_key="host_wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        value_fn=lambda h: _wifi(h).get("signal"),
    ),
    IliadboxHostSensorDescription(
        key="wifi_band",
        translation_key="host_wifi_band",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda h: HOST_BANDS.get(_wifi(h).get("band"), _wifi(h).get("band")),
    ),
    IliadboxHostSensorDescription(
        key="wifi_ssid",
        translation_key="host_wifi_ssid",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda h: _wifi(h).get("ssid"),
    ),
    IliadboxHostSensorDescription(
        key="wifi_standard",
        translation_key="host_wifi_standard",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda h: f"802.11{_wifi(h)['standard']}" if _wifi(h).get("standard") else None,
    ),
    # The box reports traffic from its own side: tx = towards the device
    IliadboxHostSensorDescription(
        key="rate_down",
        translation_key="host_rate_down",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        value_fn=lambda h: _ap(h).get("tx_rate"),
    ),
    IliadboxHostSensorDescription(
        key="rate_up",
        translation_key="host_rate_up",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        value_fn=lambda h: _ap(h).get("rx_rate"),
    ),
    IliadboxHostSensorDescription(
        key="bytes_down",
        translation_key="host_bytes_down",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_registry_enabled_default=False,
        value_fn=lambda h: _ap(h).get("tx_bytes"),
    ),
    IliadboxHostSensorDescription(
        key="bytes_up",
        translation_key="host_bytes_up",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        entity_registry_enabled_default=False,
        value_fn=lambda h: _ap(h).get("rx_bytes"),
    ),
    # Changes on every poll while the device is online: disabled by default
    IliadboxHostSensorDescription(
        key="last_activity",
        translation_key="host_last_activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=lambda h: _ts(h.get("last_activity")),
    ),
    IliadboxHostSensorDescription(
        key="first_activity",
        translation_key="host_first_activity",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda h: _ts(h.get("first_activity")),
    ),
)


def _english_name(sensor_id: str) -> str:
    """The box localizes sensor names: derive English ones from the ids."""
    if sensor_id.startswith("temp_"):
        return f"Temperature {sensor_id[5:].upper()}"
    if match := re.match(r"fan(\d+)", sensor_id):
        return f"Fan {int(match.group(1)) + 1}"
    return sensor_id


def _hw_sensors(system: dict[str, Any]) -> list[dict[str, Any]]:
    """Temperature sensors: list form (API v8+) or legacy temp_* keys."""
    if isinstance(system.get("sensors"), list):
        return system["sensors"]
    return [
        {"id": k, "name": k, "value": v}
        for k, v in system.items()
        if k.startswith("temp_")
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data
    entities: list[SensorEntity] = [IliadboxSensor(coordinator, desc) for desc in SENSORS]
    entities.extend(
        IliadboxTemperatureSensor(coordinator, s["id"], _english_name(s["id"]))
        for s in _hw_sensors(data["system"])
    )
    entities.extend(
        IliadboxFanSensor(coordinator, f["id"], _english_name(f["id"]))
        for f in data["system"].get("fans", [])
    )
    entities.extend(
        IliadboxRadioSensor(coordinator, band, desc)
        for band in data["radios"]
        for desc in RADIO_SENSORS
    )
    entities.append(IliadboxGuestSensor(coordinator, "guest_wifi"))
    async_add_entities(entities)

    add_entities_for_new_hosts(
        entry,
        lambda mac, active: [
            IliadboxHostSensor(
                coordinator, mac, desc, desc.entity_registry_enabled_default and active
            )
            for desc in HOST_SENSORS
        ],
        async_add_entities,
    )

    # One sensor per guest access, added and removed with the accesses
    guest_ids: set[int] = set()

    @callback
    def _add_guest_accesses() -> None:
        new = [k["id"] for k in coordinator.data["guest"]["keys"] if k["id"] not in guest_ids]
        if new:
            guest_ids.update(new)
            async_add_entities(IliadboxGuestAccessSensor(coordinator, i, guest_ids) for i in new)

    _add_guest_accesses()
    entry.async_on_unload(coordinator.async_add_listener(_add_guest_accesses))


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


class IliadboxRadioSensor(IliadboxEntity, SensorEntity):
    entity_description: IliadboxRadioSensorDescription

    def __init__(
        self,
        coordinator: IliadboxCoordinator,
        band: str,
        description: IliadboxRadioSensorDescription,
    ) -> None:
        super().__init__(coordinator, f"radio_{band.lower()}_{description.key}")
        self.entity_description = description
        self._band = band
        self._attr_translation_placeholders = {"band": BAND_LABELS.get(band, band)}

    @property
    def available(self) -> bool:
        return super().available and self._band in self.coordinator.data["radios"]

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data["radios"].get(self._band, {}))


class IliadboxHostSensor(IliadboxHostEntity, SensorEntity):
    entity_description: IliadboxHostSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.host)


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


class IliadboxGuestSensor(IliadboxEntity, SensorEntity):
    """Number of active guest Wi-Fi accesses.

    Attributes never contain passwords: entity states are visible to every
    user and stored in history. Admins get passwords from the panel or card.
    """

    _attr_translation_key = "guest_wifi"
    _attr_icon = "mdi:wifi-star"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"accesses"})

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["guest"]["keys"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        guest = self.coordinator.data["guest"]
        return {
            "ssid": guest["ssid"],
            "accesses": [
                {
                    "id": k["id"],
                    "description": k["params"].get("description"),
                    "access_type": k["params"].get("access_type"),
                    "max_devices": k["params"].get("max_use_count") or "unlimited",
                    "remaining_seconds": k.get("remaining"),
                }
                for k in guest["keys"]
            ],
        }


class IliadboxGuestAccessSensor(IliadboxEntity, SensorEntity):
    """Expiry of one guest access; removed when the access disappears. No password."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:wifi-lock-open"
    _unrecorded_attributes = frozenset({"remaining_seconds"})

    def __init__(self, coordinator: IliadboxCoordinator, access_id: int, tracked: set[int]) -> None:
        super().__init__(coordinator, f"guest_access_{access_id}")
        self._access_id = access_id
        self._tracked = tracked
        params = (self._access or {}).get("params", {})
        self._attr_name = f"Guest access {params.get('description') or access_id}"

    @property
    def _access(self) -> dict[str, Any] | None:
        return next(
            (k for k in self.coordinator.data["guest"]["keys"] if k["id"] == self._access_id), None
        )

    @property
    def native_value(self) -> datetime | None:
        access = self._access
        if not access or access.get("remaining") is None:
            return None
        # Rounded to the minute so the state does not change on every poll
        expires = dt_util.utcnow() + timedelta(seconds=access["remaining"])
        return expires.replace(second=0, microsecond=0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        params = (self._access or {}).get("params", {})
        return {
            "access_id": self._access_id,
            "description": params.get("description"),
            "access_type": params.get("access_type"),
            "max_devices": params.get("max_use_count") or "unlimited",
            "remaining_seconds": (self._access or {}).get("remaining"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._access is None:
            # Access revoked or expired: drop the entity, allow the id to come back
            self._tracked.discard(self._access_id)
            er.async_get(self.hass).async_remove(self.entity_id)
            return
        super()._handle_coordinator_update()
