"""Base entity for the Iliadbox."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import IliadboxCoordinator


class IliadboxEntity(CoordinatorEntity[IliadboxCoordinator]):
    """Entity attached to the box device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IliadboxCoordinator, key: str) -> None:
        super().__init__(coordinator)
        base = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{base}_{key}"
        self._attr_device_info = coordinator.device_info
