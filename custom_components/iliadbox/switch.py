"""Wi-Fi switch for the Iliadbox."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import IliadboxError
from .coordinator import IliadboxConfigEntry
from .entity import IliadboxEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([IliadboxWifiSwitch(entry.runtime_data, "wifi")])


class IliadboxWifiSwitch(IliadboxEntity, SwitchEntity):
    """Needs the 'settings' permission on the app."""

    _attr_translation_key = "wifi"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["wifi"].get("enabled"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_wifi_enabled(enabled)
        except IliadboxError as err:
            _LOGGER.error("Cannot turn Wi-Fi %s: %s", "on" if enabled else "off", err)
            raise HomeAssistantError(f"Cannot change Wi-Fi state: {err}") from err
        await self.coordinator.async_request_refresh()
