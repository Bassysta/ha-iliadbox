"""Exercise actual WebSocket decorators and subscription lifecycle."""

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.iliadbox.panel import (
    ws_clear_history,
    ws_create_guest,
    ws_delete_guest,
    ws_device_status,
    ws_get_data,
    ws_guest_qr,
    ws_reboot,
    ws_set_wifi,
    ws_subscribe,
)


def register(hass, entry):
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    for command in (
        ws_get_data,
        ws_subscribe,
        ws_device_status,
        ws_guest_qr,
        ws_create_guest,
        ws_delete_guest,
        ws_set_wifi,
        ws_reboot,
        ws_clear_history,
    ):
        websocket_api.async_register_command(hass, command)


async def test_subscription_and_explicit_qr(hass, entry, coordinator, hass_ws_client):
    ws = await hass_ws_client(hass)
    register(hass, entry)
    await ws.send_json({"id": 1, "type": "iliadbox/subscribe"})
    assert (await ws.receive_json())["success"]
    snapshot = await ws.receive_json()
    assert "synthetic-password" not in str(snapshot)
    async_dispatcher_send(hass, "iliadbox_updated")
    assert (await ws.receive_json())["type"] == "event"
    await ws.send_json(
        {"id": 2, "type": "iliadbox/guest_qr", "entry_id": entry.entry_id, "access_id": 1}
    )
    result = await ws.receive_json()
    assert result["result"]["password"] == "synthetic-password"
    assert "svg" in result["result"]["qr_svg"]
    await ws.send_json({"id": 3, "type": "unsubscribe_events", "subscription": 1})
    assert (await ws.receive_json())["success"]


async def test_non_admin_cannot_get_credentials_or_write(
    hass, entry, coordinator, client, hass_ws_client, hass_read_only_access_token
):
    ws = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    register(hass, entry)
    messages = [
        {"type": "iliadbox/guest_qr", "access_id": 1},
        {"type": "iliadbox/delete_guest", "access_id": 1},
        {"type": "iliadbox/reboot"},
        {"type": "iliadbox/set_wifi", "enabled": False},
        {"type": "iliadbox/device_status", "mac": "aa:bb:cc:dd:ee:01", "status": "known"},
        {"type": "iliadbox/clear_history"},
    ]
    for number, message in enumerate(messages, 1):
        await ws.send_json({"id": number, "entry_id": entry.entry_id, **message})
        assert not (await ws.receive_json())["success"]
    client.delete_guest_key.assert_not_awaited()
    client.reboot.assert_not_awaited()


async def test_read_only_blocks_admin_write(hass, entry, coordinator, client, hass_ws_client):
    ws = await hass_ws_client(hass)
    register(hass, entry)
    hass.config_entries.async_update_entry(entry, options={"read_only": True})
    await ws.send_json({"id": 1, "type": "iliadbox/reboot", "entry_id": entry.entry_id})
    assert not (await ws.receive_json())["success"]
    client.reboot.assert_not_awaited()
