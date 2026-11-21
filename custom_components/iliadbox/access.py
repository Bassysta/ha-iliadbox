"""Apply the same write policy to WebSocket, services and entity actions."""

from __future__ import annotations

from typing import Any

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, Unauthorized

from .const import CONF_READ_ONLY, DOMAIN


async def async_require_admin(hass: HomeAssistant, context: Context | None) -> None:
    """Allow internal automations; require admin for calls attributed to a user."""
    if context and context.user_id:
        user = await hass.auth.async_get_user(context.user_id)
        if user is None or not user.is_admin:
            raise Unauthorized()


async def async_check_write(hass: HomeAssistant, coordinator: Any, context: Context | None) -> None:
    await async_require_admin(hass, context)
    if coordinator.config_entry.options.get(CONF_READ_ONLY, False):
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="read_only")
