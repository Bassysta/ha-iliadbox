"""Buttons for the Iliadbox: reboot and quick guest Wi-Fi."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import IliadboxError
from .coordinator import IliadboxConfigEntry
from .entity import IliadboxEntity
from .guest import (
    DEFAULT_ACCESS_TYPE,
    DEFAULT_HOURS,
    DEFAULT_MAX_DEVICES,
    async_create_guest,
    default_description,
    generate_password,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            IliadboxRebootButton(entry.runtime_data, "reboot"),
            IliadboxGuestButton(entry.runtime_data, "create_guest_wifi"),
        ]
    )


class IliadboxRebootButton(IliadboxEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.reboot()
        except IliadboxError as err:
            _LOGGER.error("Cannot reboot the box: %s", err)
            raise HomeAssistantError(f"Cannot reboot the box: {err}") from err


class IliadboxGuestButton(IliadboxEntity, ButtonEntity):
    """Guest access with defaults (24 h, internet only, unlimited devices).

    The password is shown in a persistent notification.
    """

    _attr_translation_key = "create_guest_wifi"
    _attr_icon = "mdi:wifi-plus"

    async def async_press(self) -> None:
        try:
            await async_create_guest(
                self.hass,
                self.coordinator,
                default_description(self.coordinator),
                generate_password(),
                DEFAULT_HOURS,
                DEFAULT_MAX_DEVICES,
                DEFAULT_ACCESS_TYPE,
            )
        except IliadboxError as err:
            _LOGGER.error("Cannot create guest Wi-Fi: %s", err)
            raise HomeAssistantError(f"Cannot create guest Wi-Fi: {err}") from err
