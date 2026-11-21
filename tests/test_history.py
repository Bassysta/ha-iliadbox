"""Persistent new-device baseline and bounded, secret-free event timeline."""

from copy import deepcopy

from custom_components.iliadbox.history import MAX_EVENTS, NetworkHistory


async def test_first_sample_is_baseline(coordinator):
    assert coordinator.history.events == []
    assert all(
        device["status"] == "known" for device in coordinator.history.data["devices"].values()
    )


async def test_new_device_once_and_recognition_survives_restart(
    coordinator, client, host, hass, entry
):
    new = deepcopy(host)
    new["l2ident"]["id"] = "aa:bb:cc:dd:ee:02"
    new["primary_name"] = "New phone"
    client.get_lan_hosts.return_value.append(new)
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert len([e for e in coordinator.history.events if e["type"] == "new_device"]) == 1
    coordinator.history.set_device_status(new["l2ident"]["id"], "known")
    await coordinator.history.async_save()
    restored = NetworkHistory(hass, entry)
    await restored.async_load()
    restored.observe(coordinator.data, coordinator.data["hosts"])
    assert restored.data["devices"][new["l2ident"]["id"]]["status"] == "known"
    assert len([e for e in restored.events if e["type"] == "new_device"]) == 1
    await restored.async_save()


async def test_ignored_host_does_not_generate_presence_events(coordinator, client, host):
    coordinator.history.set_device_status(host["l2ident"]["id"], "ignored")
    client.get_lan_hosts.return_value[0]["active"] = False
    await coordinator.async_refresh()
    assert coordinator.history.events == []


async def test_wan_duration_and_no_duplicate_events(coordinator, client, freezer):
    client.get_connection.return_value = {"state": "down", "ipv4": "198.51.100.1"}
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    freezer.tick(120)
    client.get_connection.return_value = {"state": "up", "ipv4": "198.51.100.2"}
    await coordinator.async_refresh()
    events = coordinator.history.events
    assert len([e for e in events if e["type"] == "wan_changed"]) == 2
    assert (
        next(e for e in events if e["type"] == "wan_changed" and e["current"] == "up")[
            "duration_seconds"
        ]
        == 120
    )
    assert any(e["type"] == "public_ip_changed" for e in events)


async def test_history_retention_clear_and_secrets(coordinator, freezer):
    for _ in range(MAX_EVENTS + 20):
        coordinator.history._emit("router_restarted")
    assert len(coordinator.history.events) == MAX_EVENTS
    assert "synthetic-password" not in repr(coordinator.history.data)
    assert "synthetic-token" not in repr(coordinator.history.data)
    freezer.tick(8 * 86400)
    assert coordinator.history.events == []
    coordinator.history._emit("router_restarted")
    coordinator.history.clear()
    assert coordinator.history.data["devices"]
    assert coordinator.history.events == []


async def test_two_boxes_have_isolated_storage(hass, entry, coordinator):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    other = MockConfigEntry(domain="iliadbox", unique_id="box-2", data=entry.data)
    other.add_to_hass(hass)
    history = NetworkHistory(hass, other)
    await history.async_load()
    assert history.data["devices"] == {}
    assert history.store.key != coordinator.history.store.key


async def test_opt_in_notification_and_event_once(hass, entry, coordinator, client, host):
    from unittest.mock import patch

    hass.config_entries.async_update_entry(entry, options={"notify_new_devices": True})
    events = []
    unsubscribe = hass.bus.async_listen(
        "iliadbox_new_device", lambda event: events.append(event.data)
    )
    newcomer = deepcopy(host)
    newcomer["l2ident"]["id"] = "aa:bb:cc:dd:ee:03"
    client.get_lan_hosts.return_value.append(newcomer)
    with patch("custom_components.iliadbox.history.persistent_notification.async_create") as notify:
        await coordinator.async_refresh()
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        notify.assert_called_once()
    assert len(events) == 1 and events[0]["entry_id"] == entry.entry_id
    unsubscribe()
