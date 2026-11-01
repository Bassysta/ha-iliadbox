"""Config flow for the Iliadbox integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import IliadboxClient, IliadboxConnectionError, IliadboxError, IliadboxSSLError
from .const import (
    CONF_APP_TOKEN,
    CONF_LOG_LEVEL,
    CONF_MAX_AGE_DAYS,
    CONF_USE_SSL,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL_PORT,
    DOMAIN,
    LOG_LEVELS,
    MAX_MAX_AGE_DAYS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class IliadboxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow: host -> confirm on the box -> entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str = DEFAULT_HOST
        self._port: int = DEFAULT_PORT
        self._use_ssl: bool = False
        self._verify_ssl: bool = True
        self._client: IliadboxClient | None = None
        self._app_token: str | None = None
        self._track_id: int | None = None
        self._box_name: str = "Iliadbox"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IliadboxOptionsFlow:
        return IliadboxOptionsFlow()

    def _connection_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._host): str,
                vol.Required(CONF_PORT, default=self._port): int,
                vol.Required(CONF_USE_SSL, default=self._use_ssl): bool,
                vol.Required(CONF_VERIFY_SSL, default=self._verify_ssl): bool,
            }
        )

    async def _async_connect(
        self, user_input: dict[str, Any], app_token: str | None = None
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Read the connection form and reach the box. Returns (box info, errors)."""
        self._host = user_input[CONF_HOST].strip()
        self._port = user_input[CONF_PORT]
        self._use_ssl = user_input[CONF_USE_SSL]
        self._verify_ssl = user_input[CONF_VERIFY_SSL]
        if self._use_ssl and self._port == DEFAULT_PORT:
            _LOGGER.info("HTTPS selected with port %s, using %s", DEFAULT_PORT, DEFAULT_SSL_PORT)
            self._port = DEFAULT_SSL_PORT
        self._client = IliadboxClient(
            async_get_clientsession(self.hass, verify_ssl=self._verify_ssl),
            self._host,
            self._port,
            self._use_ssl,
            app_token,
            self._verify_ssl,
        )
        try:
            return await self._client.discover(), {}
        except IliadboxSSLError as err:
            _LOGGER.error("Certificate of %s rejected: %s", self._host, err)
            return None, {"base": "ssl_error"}
        except IliadboxConnectionError as err:
            _LOGGER.error("Cannot reach box at %s:%s: %s", self._host, self._port, err)
            return None, {"base": "cannot_connect"}

    def _connection_data(self) -> dict[str, Any]:
        return {
            CONF_HOST: self._host,
            CONF_PORT: self._port,
            CONF_USE_SSL: self._use_ssl,
            CONF_VERIFY_SSL: self._verify_ssl,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info, errors = await self._async_connect(user_input)
            if info is not None:
                if self.source != "reauth":
                    await self.async_set_unique_id(info.get("uid") or self._host)
                    self._abort_if_unique_id_configured()
                self._box_name = info.get("device_name") or "Iliadbox"
                return await self.async_step_link()

        return self.async_show_form(
            step_id="user", data_schema=self._connection_schema(), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change address, port or HTTPS settings keeping the current token."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is None:
            self._host = entry.data[CONF_HOST]
            self._port = entry.data[CONF_PORT]
            self._use_ssl = entry.data.get(CONF_USE_SSL, False)
            self._verify_ssl = entry.data.get(CONF_VERIFY_SSL, False)
        else:
            info, errors = await self._async_connect(user_input, entry.data[CONF_APP_TOKEN])
            if info is not None:
                if entry.unique_id and info.get("uid") and info["uid"] != entry.unique_id:
                    _LOGGER.error("Box at %s is not the configured one", self._host)
                    return self.async_abort(reason="wrong_box")
                try:
                    await self._client.open_session()
                except IliadboxConnectionError:
                    errors["base"] = "cannot_connect"
                except IliadboxError as err:
                    # Token not valid on this box: a new authorization is needed
                    _LOGGER.error("Stored token rejected by %s: %s", self._host, err)
                    errors["base"] = "invalid_auth"
                else:
                    _LOGGER.info(
                        "Connection changed to %s:%s (HTTPS %s, certificate check %s)",
                        self._host,
                        self._port,
                        "on" if self._use_ssl else "off",
                        "on" if self._use_ssl and self._verify_ssl else "off",
                    )
                    return self.async_update_reload_and_abort(
                        entry, data={**entry.data, **self._connection_data()}
                    )

        return self.async_show_form(
            step_id="reconfigure", data_schema=self._connection_schema(), errors=errors
        )

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request a token, then wait for the user to accept it on the box."""
        assert self._client is not None
        errors: dict[str, str] = {}

        try:
            if self._track_id is None:
                self._app_token, self._track_id = (
                    await self._client.request_authorization()
                )
            elif user_input is not None:
                status = await self._client.authorization_status(self._track_id)
                _LOGGER.info("Authorization request %s status: %s", self._track_id, status)
                if status == "granted":
                    await self._client.open_session()
                    return self._finish()
                if status == "pending":
                    errors["base"] = "not_confirmed"
                else:
                    # timeout / denied / unknown: start over with a fresh request
                    errors["base"] = "auth_denied" if status == "denied" else "auth_timeout"
                    self._track_id = None
        except IliadboxConnectionError as err:
            _LOGGER.error("Lost connection to the box during authorization: %s", err)
            errors["base"] = "cannot_connect"
        except IliadboxError as err:
            _LOGGER.error("Authorization failed: %s", err)
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="link",
            errors=errors,
            description_placeholders={"host": self._host},
        )

    def _finish(self) -> ConfigFlowResult:
        data = {**self._connection_data(), CONF_APP_TOKEN: self._app_token}
        if self.source == "reauth":
            _LOGGER.info("Re-authorization of %s completed", self._host)
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )
        _LOGGER.info("Box %s at %s configured", self._box_name, self._host)
        return self.async_create_entry(title=self._box_name, data=data)

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Token revoked: ask a new one on the same host."""
        _LOGGER.warning("Starting re-authorization for box at %s", entry_data[CONF_HOST])
        self._host = entry_data[CONF_HOST]
        self._port = entry_data[CONF_PORT]
        self._use_ssl = entry_data.get(CONF_USE_SSL, False)
        self._verify_ssl = entry_data.get(CONF_VERIFY_SSL, False)
        return await self.async_step_user()


class IliadboxOptionsFlow(OptionsFlow):
    """Every setting: connection, polling interval and log level.

    Connection changes are checked against the box with the current token
    before saving. The entry reloads after saving.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        errors: dict[str, str] = {}
        if user_input is not None:
            connection = {
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_PORT: user_input[CONF_PORT],
                CONF_USE_SSL: user_input[CONF_USE_SSL],
                CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL],
            }
            if connection[CONF_USE_SSL] and connection[CONF_PORT] == DEFAULT_PORT:
                connection[CONF_PORT] = DEFAULT_SSL_PORT
            changed = any(entry.data.get(k) != v for k, v in connection.items())
            if changed:
                errors = await self._async_check_connection(connection)
            if not errors:
                if changed:
                    _LOGGER.info(
                        "Connection changed to %s:%s (HTTPS %s, certificate check %s)",
                        connection[CONF_HOST],
                        connection[CONF_PORT],
                        "on" if connection[CONF_USE_SSL] else "off",
                        "on" if connection[CONF_USE_SSL] and connection[CONF_VERIFY_SSL] else "off",
                    )
                    self.hass.config_entries.async_update_entry(
                        entry, data={**entry.data, **connection}
                    )
                return self.async_create_entry(
                    data={
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_MAX_AGE_DAYS: int(user_input[CONF_MAX_AGE_DAYS]),
                        CONF_LOG_LEVEL: user_input[CONF_LOG_LEVEL],
                    }
                )

        current = {**entry.data, **entry.options, **(user_input or {})}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=current[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=current[CONF_PORT]): int,
                    vol.Required(CONF_USE_SSL, default=current.get(CONF_USE_SSL, False)): bool,
                    vol.Required(
                        CONF_VERIFY_SSL, default=current.get(CONF_VERIFY_SSL, False)
                    ): bool,
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=5,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MAX_AGE_DAYS,
                        default=current.get(CONF_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0,
                            max=MAX_MAX_AGE_DAYS,
                            step=1,
                            unit_of_measurement="d",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_LOG_LEVEL, default=current.get(CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=LOG_LEVELS,
                            translation_key=CONF_LOG_LEVEL,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def _async_check_connection(self, connection: dict[str, Any]) -> dict[str, str]:
        """Reach the box with the new settings and the current token."""
        entry = self.config_entry
        verify = connection[CONF_USE_SSL] and connection[CONF_VERIFY_SSL]
        client = IliadboxClient(
            async_get_clientsession(self.hass, verify_ssl=verify),
            connection[CONF_HOST],
            connection[CONF_PORT],
            connection[CONF_USE_SSL],
            entry.data[CONF_APP_TOKEN],
            connection[CONF_VERIFY_SSL],
        )
        try:
            info = await client.discover()
            if entry.unique_id and info.get("uid") and info["uid"] != entry.unique_id:
                _LOGGER.error("Box at %s is not the configured one", connection[CONF_HOST])
                return {"base": "wrong_box"}
            await client.open_session()
        except IliadboxSSLError as err:
            _LOGGER.error("Certificate of %s rejected: %s", connection[CONF_HOST], err)
            return {"base": "ssl_error"}
        except IliadboxConnectionError as err:
            _LOGGER.error("Cannot reach box at %s: %s", connection[CONF_HOST], err)
            return {"base": "cannot_connect"}
        except IliadboxError as err:
            _LOGGER.error("Stored token rejected by %s: %s", connection[CONF_HOST], err)
            return {"base": "invalid_auth"}
        return {}
