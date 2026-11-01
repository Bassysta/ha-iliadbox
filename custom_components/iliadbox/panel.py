"""Sidebar panel and websocket API for the Iliadbox."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback

from .api import IliadboxError
from .const import APP_VERSION, DOMAIN
from .coordinator import IliadboxCoordinator
from .guest import access_qr_svg, async_create_guest, async_delete_guest, wifi_qr

_LOGGER = logging.getLogger(__name__)

STATIC_URL = "/iliadbox_static"
PANEL_PATH = "iliadbox"
DATA_STATIC = f"{DOMAIN}_static"
DATA_PANEL = f"{DOMAIN}_panel"


def _coordinators(hass: HomeAssistant) -> dict[str, IliadboxCoordinator]:
    return {
        entry.entry_id: entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    }


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register static files, websocket commands and the sidebar panel once."""
    if not hass.data.get(DATA_STATIC):
        # Static paths cannot be unregistered: keep them for the whole HA run
        root = Path(__file__).parent
        await hass.http.async_register_static_paths(
            [
                StaticPathConfig(STATIC_URL, str(root / "frontend"), False),
                # The integration icon, shown on the panel box cards
                StaticPathConfig(f"{STATIC_URL}/brand", str(root / "brand"), True),
            ]
        )
        websocket_api.async_register_command(hass, ws_get_data)
        websocket_api.async_register_command(hass, ws_set_wifi)
        websocket_api.async_register_command(hass, ws_reboot)
        websocket_api.async_register_command(hass, ws_create_guest)
        websocket_api.async_register_command(hass, ws_delete_guest)
        websocket_api.async_register_command(hass, ws_guest_qr)
        # Dashboard card, loaded on every dashboard
        frontend.add_extra_js_url(hass, f"{STATIC_URL}/iliadbox-guest-card.js?v={APP_VERSION}")
        hass.data[DATA_STATIC] = True
        _LOGGER.debug("Guest Wi-Fi card registered")

    if hass.data.get(DATA_PANEL):
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name="iliadbox-panel",
        sidebar_title="Iliadbox",
        sidebar_icon="mdi:router-wireless",
        module_url=f"{STATIC_URL}/iliadbox-panel.js?v={APP_VERSION}",
        require_admin=False,
    )
    hass.data[DATA_PANEL] = True
    _LOGGER.debug("Sidebar panel registered at /%s", PANEL_PATH)


@callback
def async_unregister_panel(hass: HomeAssistant) -> None:
    if hass.data.pop(DATA_PANEL, False):
        frontend.async_remove_panel(hass, PANEL_PATH)
        _LOGGER.debug("Sidebar panel removed")


@websocket_api.websocket_command({vol.Required("type"): "iliadbox/data"})
@callback
def ws_get_data(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    boxes = []
    is_admin = connection.user.is_admin
    coordinators = _coordinators(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id not in coordinators:
            # Configured but not running (box unreachable, authorization lost...)
            boxes.append(
                {
                    "entry_id": entry.entry_id,
                    "title": entry.title,
                    "host": entry.data.get(CONF_HOST),
                    "loaded": False,
                    "state": entry.state.value,
                    "reason": entry.reason,
                }
            )
    for entry_id, coordinator in coordinators.items():
        data = coordinator.data or {}
        guest = data.get("guest", {"ssid": None, "keys": []})
        keys = guest["keys"]
        if not is_admin:
            # Guest passwords are only shown to admins
            keys = [
                {**k, "params": {p: v for p, v in k["params"].items() if p != "key"}}
                for k in keys
            ]
        boxes.append(
            {
                "entry_id": entry_id,
                "title": coordinator.config_entry.title,
                "host": coordinator.config_entry.data.get(CONF_HOST),
                "loaded": True,
                "model": coordinator.client.info.get("box_model_name"),
                "api_version": coordinator.client.info.get("api_version"),
                "available": coordinator.last_update_success,
                "connection": data.get("connection", {}),
                "system": data.get("system", {}),
                "wifi": data.get("wifi", {}),
                "radios": list(data.get("radios", {}).values()),
                "hosts": list(data.get("hosts", {}).values()),
                "guest": {"ssid": guest["ssid"], "keys": keys},
            }
        )
    boxes.sort(key=lambda b: (b["title"] or "").lower())
    connection.send_result(msg["id"], boxes)


async def _run(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    action: str,
) -> None:
    coordinator = _coordinators(hass).get(msg["entry_id"])
    if coordinator is None:
        _LOGGER.error("Panel action %s for unknown entry %s", action, msg["entry_id"])
        connection.send_error(msg["id"], "not_found", "Box not found")
        return
    _LOGGER.info("Panel action %s requested by user %s", action, connection.user.name)
    try:
        if action == "wifi":
            await coordinator.client.set_wifi_enabled(msg["enabled"])
        else:
            await coordinator.client.reboot()
    except IliadboxError as err:
        _LOGGER.error("Panel action %s failed: %s", action, err)
        connection.send_error(msg["id"], "box_error", str(err))
        return
    connection.send_result(msg["id"])
    if action == "wifi":
        await coordinator.async_request_refresh()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iliadbox/set_wifi",
        vol.Required("entry_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_wifi(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    await _run(hass, connection, msg, "wifi")


@websocket_api.websocket_command(
    {vol.Required("type"): "iliadbox/reboot", vol.Required("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_reboot(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    await _run(hass, connection, msg, "reboot")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iliadbox/create_guest",
        vol.Required("entry_id"): str,
        vol.Required("description"): str,
        vol.Required("password"): str,
        vol.Required("duration_hours"): int,
        vol.Required("max_devices"): int,
        vol.Required("access_type"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_create_guest(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coordinator = _coordinators(hass).get(msg["entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "Box not found")
        return
    _LOGGER.info("Guest Wi-Fi creation requested from panel by %s", connection.user.name)
    try:
        details = await async_create_guest(
            hass,
            coordinator,
            msg["description"],
            msg["password"],
            msg["duration_hours"],
            msg["max_devices"],
            msg["access_type"],
        )
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    except IliadboxError as err:
        _LOGGER.error("Guest Wi-Fi creation from panel failed: %s", err)
        connection.send_error(msg["id"], "box_error", str(err))
        return
    if details["ssid"]:
        details["qr_svg"] = wifi_qr(details["ssid"], details["password"]).decode()
    connection.send_result(msg["id"], details)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iliadbox/guest_qr",
        vol.Required("entry_id"): str,
        vol.Required("access_id"): int,
    }
)
@websocket_api.require_admin
@callback
def ws_guest_qr(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """QR code (SVG) of an existing guest access. Admins only: it holds the password."""
    coordinator = _coordinators(hass).get(msg["entry_id"])
    access = coordinator and next(
        (k for k in coordinator.data["guest"]["keys"] if k["id"] == msg["access_id"]), None
    )
    svg = access and access_qr_svg(coordinator, access)
    if not svg:
        connection.send_error(msg["id"], "not_found", "Guest access not found")
        return
    connection.send_result(msg["id"], {"qr_svg": svg})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iliadbox/delete_guest",
        vol.Required("entry_id"): str,
        vol.Required("access_id"): int,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete_guest(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coordinator = _coordinators(hass).get(msg["entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "Box not found")
        return
    try:
        await async_delete_guest(hass, coordinator, msg["access_id"])
    except IliadboxError as err:
        _LOGGER.error("Guest Wi-Fi deletion from panel failed: %s", err)
        connection.send_error(msg["id"], "box_error", str(err))
        return
    connection.send_result(msg["id"])
