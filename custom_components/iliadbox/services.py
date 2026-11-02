"""Actions (services) of the Iliadbox integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import IliadboxError
from .const import DOMAIN
from .coordinator import IliadboxCoordinator
from .guest import (
    ACCESS_TYPES,
    DEFAULT_ACCESS_TYPE,
    DEFAULT_HOURS,
    DEFAULT_MAX_DEVICES,
    MAX_HOURS,
    async_create_guest,
    async_delete_guest,
    default_description,
    generate_password,
)

_LOGGER = logging.getLogger(__name__)

ATTR_ENTRY = "config_entry_id"

CREATE_GUEST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Optional("description"): cv.string,
        vol.Optional("password"): cv.string,
        vol.Optional("duration_hours", default=DEFAULT_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_HOURS)
        ),
        vol.Optional("max_devices", default=DEFAULT_MAX_DEVICES): vol.All(
            vol.Coerce(int), vol.Range(min=0)
        ),
        vol.Optional("access_type", default=DEFAULT_ACCESS_TYPE): vol.In(ACCESS_TYPES),
    }
)

DELETE_GUEST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY): cv.string,
        vol.Required("access_id"): vol.Coerce(int),
    }
)


def _coordinator(hass: HomeAssistant, entry_id: str | None) -> IliadboxCoordinator:
    loaded = [
        e for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    if entry_id:
        loaded = [e for e in loaded if e.entry_id == entry_id]
    if not loaded:
        raise ServiceValidationError("No loaded Iliadbox found")
    if len(loaded) > 1:
        raise ServiceValidationError("Several Iliadbox configured: set config_entry_id")
    return loaded[0].runtime_data


def async_setup_services(hass: HomeAssistant) -> None:
    async def create_guest(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call.data.get(ATTR_ENTRY))
        try:
            return await async_create_guest(
                hass,
                coordinator,
                call.data.get("description") or default_description(coordinator),
                call.data.get("password") or generate_password(),
                call.data["duration_hours"],
                call.data["max_devices"],
                call.data["access_type"],
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except IliadboxError as err:
            _LOGGER.error("Cannot create guest Wi-Fi: %s", err)
            raise HomeAssistantError(f"Cannot create guest Wi-Fi: {err}") from err

    async def delete_guest(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call.data.get(ATTR_ENTRY))
        try:
            await async_delete_guest(hass, coordinator, call.data["access_id"])
        except IliadboxError as err:
            _LOGGER.error("Cannot delete guest Wi-Fi access: %s", err)
            raise HomeAssistantError(f"Cannot delete guest Wi-Fi access: {err}") from err

    hass.services.async_register(
        DOMAIN,
        "create_guest_wifi",
        create_guest,
        schema=CREATE_GUEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "delete_guest_wifi", delete_guest, schema=DELETE_GUEST_SCHEMA
    )
