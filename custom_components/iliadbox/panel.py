"""Sidebar panel and websocket API for the Iliadbox."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import time
from typing import Any

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
import voluptuous as vol

from .access import async_check_write
from .api import IliadboxError
from .const import APP_VERSION, CONF_READ_ONLY, DOMAIN
from .coordinator import IliadboxCoordinator
from .guest import (
    access_qr_svg,
    async_create_guest,
    async_delete_guest,
    default_description,
    wifi_qr,
)

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
    lock = hass.data.setdefault(f"{DOMAIN}_panel_lock", asyncio.Lock())
    async with lock:
        await _async_register_panel(hass)


async def _async_register_panel(hass: HomeAssistant) -> None:
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
        websocket_api.async_register_command(hass, ws_subscribe)
        websocket_api.async_register_command(hass, ws_device_status)
        websocket_api.async_register_command(hass, ws_clear_history)
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
    connection.send_result(msg["id"], _box_data(hass, connection.user.is_admin))


def _box_data(hass: HomeAssistant, is_admin: bool) -> list[dict[str, Any]]:
    boxes = []
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
        # Credentials are returned only by an explicit admin request, never in
        # background snapshots, including snapshots sent to administrators.
        keys = [
            {
                "id": k["id"],
                "remaining": k.get("remaining"),
                "expires_at": k.get("expires_at"),
                "params": {
                    p: k.get("params", {}).get(p)
                    for p in ("description", "access_type", "max_use_count")
                },
            }
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
                "can_modify": "settings" in coordinator.client.permissions
                and not coordinator.config_entry.options.get(CONF_READ_ONLY, False),
                "read_only": coordinator.config_entry.options.get(CONF_READ_ONLY, False),
                "configuration_url": coordinator.client.configuration_url,
                "freshness": data.get("freshness", {}),
                "events": coordinator.history.events if is_admin else [],
                "devices": coordinator.history.data["devices"] if is_admin else {},
                "available": coordinator.last_update_success,
                "connection": {
                    key: data.get("connection", {}).get(key)
                    for key in (
                        "state",
                        "rate_down",
                        "rate_up",
                        "bytes_down",
                        "bytes_up",
                        "bandwidth_down",
                        "bandwidth_up",
                        "ipv4",
                        "ipv6",
                        "media",
                        "type",
                    )
                },
                "system": {
                    **{
                        key: data.get("system", {}).get(key)
                        for key in ("uptime_val", "firmware_version")
                    },
                    **{
                        key: [
                            {"id": item.get("id"), "value": item.get("value")}
                            for item in data.get("system", {}).get(key, [])
                        ]
                        for key in ("sensors", "fans")
                    },
                },
                "wifi": {
                    key: data.get("wifi", {}).get(key)
                    for key in ("enabled", "power_saving", "mac_filter_state")
                },
                "radios": data.get("radio_details", []),
                "hosts": [
                    {
                        **{
                            key: host.get(key)
                            for key in (
                                "primary_name",
                                "default_name",
                                "vendor_name",
                                "active",
                                "last_activity",
                            )
                        },
                        "l2ident": {
                            key: host.get("l2ident", {}).get(key) for key in ("type", "id")
                        },
                        "l3connectivities": [
                            {key: item.get(key) for key in ("af", "addr", "active")}
                            for item in host.get("l3connectivities") or []
                        ],
                    }
                    for host in data.get("hosts", {}).values()
                ],
                "guest": {
                    "ssid": guest["ssid"],
                    "keys": keys,
                    "default_name": default_description(coordinator),
                },
            }
        )
    boxes.sort(key=lambda b: (b["title"] or "").lower())
    return boxes


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
        await async_check_write(hass, coordinator, Context(user_id=connection.user.id))
        if action == "wifi":
            await coordinator.client.set_wifi_enabled(msg["enabled"])
        else:
            await coordinator.client.reboot()
    except (IliadboxError, HomeAssistantError) as err:
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
        await async_check_write(hass, coordinator, Context(user_id=connection.user.id))
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
    except (IliadboxError, HomeAssistantError) as err:
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
    if (
        coordinator is None
        or not coordinator.last_update_success
        or not all(coordinator.data["freshness"].values())
    ):
        connection.send_error(msg["id"], "unavailable", "Guest data is unavailable")
        return
    access = next(
        (
            k
            for k in coordinator.data["guest"]["keys"]
            if k["id"] == msg["access_id"]
            and (k.get("expires_at") is None or k["expires_at"] > time.time())
        ),
        None,
    )
    svg = access and access_qr_svg(coordinator, access)
    if not svg:
        connection.send_error(msg["id"], "not_found", "Guest access not found")
        return
    connection.send_result(
        msg["id"],
        {
            "qr_svg": svg,
            "password": access["params"]["key"],
            "ssid": coordinator.data["guest"]["ssid"],
        },
    )


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
        await async_check_write(hass, coordinator, Context(user_id=connection.user.id))
        await async_delete_guest(hass, coordinator, msg["access_id"])
    except (IliadboxError, HomeAssistantError) as err:
        _LOGGER.error("Guest Wi-Fi deletion from panel failed: %s", err)
        connection.send_error(msg["id"], "box_error", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command({vol.Required("type"): "iliadbox/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Push cached snapshots; no additional router polling per browser tab."""

    @callback
    def send(*args: Any) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], _box_data(hass, connection.user.is_admin))
        )

    removers = [
        async_dispatcher_connect(hass, f"{DOMAIN}_updated", send),
        async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, send),
    ]
    connection.subscriptions[msg["id"]] = lambda: [remove() for remove in removers]
    connection.send_result(msg["id"])
    send()


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iliadbox/device_status",
        vol.Required("entry_id"): str,
        vol.Required("mac"): str,
        vol.Required("status"): vol.In(["known", "ignored"]),
    }
)
@websocket_api.require_admin
@callback
def ws_device_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coordinator = _coordinators(hass).get(msg["entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "Box not found")
        return
    try:
        coordinator.history.set_device_status(msg["mac"].lower(), msg["status"])
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    connection.send_result(msg["id"])
    async_dispatcher_send(hass, f"{DOMAIN}_updated")


@websocket_api.websocket_command(
    {vol.Required("type"): "iliadbox/clear_history", vol.Required("entry_id"): str}
)
@websocket_api.require_admin
@callback
def ws_clear_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    coordinator = _coordinators(hass).get(msg["entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "Box not found")
        return
    coordinator.history.clear()
    connection.send_result(msg["id"])
    async_dispatcher_send(hass, f"{DOMAIN}_updated")
