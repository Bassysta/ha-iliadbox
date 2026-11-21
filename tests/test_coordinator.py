"""Recoverable failures, stable identities and entity lifecycle regressions."""

from copy import deepcopy
from unittest.mock import Mock

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.iliadbox.api import (
    IliadboxAuthError,
    IliadboxError,
    IliadboxUnsupportedError,
)
from custom_components.iliadbox.const import CONF_READ_ONLY
from custom_components.iliadbox.sensor import IliadboxGuestAccessSensor


@pytest.mark.parametrize("failed,healthy", [("guest", "radios"), ("radios", "guest")])
async def test_optional_failures_keep_cache_and_other_source(coordinator, client, failed, healthy):
    previous = deepcopy(coordinator.data)
    method = client.get_guest_keys if failed == "guest" else client.get_wifi_radios
    method.side_effect = IliadboxError("temporary")
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert (
        coordinator.data["guest"]["keys"] == previous["guest"]["keys"]
        if failed == "guest"
        else coordinator.data["radios"] == previous["radios"]
    )
    assert coordinator.data["freshness"][failed] is False
    assert coordinator.data["freshness"][healthy] is True
    assert not any(e["type"] == "guest_removed" for e in coordinator.history.events)
    method.side_effect = None
    await coordinator.async_refresh()
    assert coordinator.data["freshness"][failed] is True


async def test_guest_sensor_not_removed_on_failed_read(coordinator, client):
    sensor = IliadboxGuestAccessSensor(coordinator, 1, {1})
    sensor.async_write_ha_state = Mock()
    client.get_guest_keys.side_effect = IliadboxError("temporary")
    await coordinator.async_refresh()
    sensor._handle_coordinator_update()
    assert not sensor.available
    assert sensor._tracked == {1}


async def test_guest_expiry_is_fixed_in_cache(coordinator, freezer):
    sensor = IliadboxGuestAccessSensor(coordinator, 1, {1})
    expiry = sensor.native_value
    freezer.tick(300)
    assert sensor.native_value == expiry


async def test_same_band_bss_are_preserved(coordinator, client):
    client.get_wifi_radios.return_value = [
        {"id": 1, "band": "5G", "clients": 2, "channel": 36},
        {"id": 2, "band": "5G", "clients": 3, "channel": 40},
    ]
    await coordinator.async_refresh()
    assert coordinator.data["radios"]["5G"]["clients"] == 5
    assert coordinator.data["radios"]["5G"]["channel"] is None
    assert len(coordinator.data["radio_details"]) == 2


async def test_optional_unsupported_not_polled_repeatedly(coordinator, client):
    client.get_guest_keys.side_effect = IliadboxUnsupportedError("nodev")
    await coordinator.async_refresh()
    count = client.get_guest_keys.call_count
    await coordinator.async_refresh()
    assert client.get_guest_keys.call_count == count
    assert not coordinator.data["freshness"]["guest"]


async def test_optional_auth_failure_propagates(coordinator, client):
    client.get_guest_keys.side_effect = IliadboxAuthError("revoked")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_outage_is_not_everybody_leaving(coordinator, client):
    client.get_connection.side_effect = IliadboxError("offline")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert [e["type"] for e in coordinator.history.events] == ["router_unavailable"]
    client.get_connection.side_effect = None
    await coordinator.async_refresh()
    assert [e["type"] for e in coordinator.history.events] == [
        "router_available",
        "router_unavailable",
    ]


async def test_read_only_never_probes_permission(coordinator, client, hass, entry, freezer):
    hass.config_entries.async_update_entry(entry, options={CONF_READ_ONLY: True})
    client.permissions = set()
    client.permissions_checked_at = 0
    await coordinator.async_refresh()
    client.open_session.assert_not_awaited()


async def test_permission_probe_throttled(coordinator, client):
    client.permissions = set()
    await coordinator.async_refresh()
    client.open_session.assert_not_awaited()


async def test_hosts_return_without_duplicate_entities(coordinator, entry):
    from custom_components.iliadbox.entity import add_entities_for_new_hosts

    add = Mock()
    factory = Mock(return_value=[object()])
    add_entities_for_new_hosts(entry, factory, add)
    saved = coordinator.data["hosts"]
    coordinator.data["hosts"] = {}
    coordinator.async_update_listeners()
    coordinator.data["hosts"] = saved
    coordinator.async_update_listeners()
    assert factory.call_count == 1
