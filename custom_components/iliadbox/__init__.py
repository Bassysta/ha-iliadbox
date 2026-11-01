"""The Iliadbox integration (Freebox OS API)."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import IliadboxAuthError, IliadboxClient, IliadboxError
from .const import (
    CONF_APP_TOKEN,
    CONF_LOG_LEVEL,
    CONF_USE_SSL,
    DEFAULT_LOG_LEVEL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import IliadboxConfigEntry, IliadboxCoordinator
from .panel import async_register_panel, async_unregister_panel
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    return True


def _apply_log_level(entry: IliadboxConfigEntry) -> None:
    """Set the level of the whole integration logger from the entry options."""
    level = entry.options.get(CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL)
    logging.getLogger(__package__).setLevel(level.upper())
    _LOGGER.info("Log level set to %s", level)


async def _async_options_updated(
    hass: HomeAssistant, entry: IliadboxConfigEntry
) -> None:
    _apply_log_level(entry)


async def async_setup_entry(hass: HomeAssistant, entry: IliadboxConfigEntry) -> bool:
    _apply_log_level(entry)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    host = entry.data[CONF_HOST]
    # Entries created before 0.5.0 have no verify_ssl: they never verified
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
    client = IliadboxClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        host,
        entry.data[CONF_PORT],
        entry.data.get(CONF_USE_SSL, False),
        entry.data[CONF_APP_TOKEN],
        verify_ssl,
    )
    try:
        await client.discover()
        await client.open_session()
    except IliadboxAuthError as err:
        _LOGGER.error("Box at %s rejected the app token, re-authorization needed: %s", host, err)
        raise ConfigEntryAuthFailed(str(err)) from err
    except IliadboxError as err:
        _LOGGER.warning("Box at %s not ready, Home Assistant will retry: %s", host, err)
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = IliadboxCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    system = coordinator.data["system"]
    _LOGGER.info(
        "Connected to %s at %s (firmware %s, API %s)",
        client.info.get("box_model_name", "Iliadbox"),
        host,
        system.get("firmware_version"),
        client.info.get("api_version"),
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IliadboxConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    others_loaded = any(
        other.entry_id != entry.entry_id and other.state is ConfigEntryState.LOADED
        for other in hass.config_entries.async_entries(DOMAIN)
    )
    if unloaded and not others_loaded:
        async_unregister_panel(hass)
    _LOGGER.debug("Unloaded entry %s (success=%s)", entry.title, unloaded)
    return unloaded
