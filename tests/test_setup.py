"""Load real platforms, register the panel and preserve entity customizations."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er


async def test_setup_filter_return_unload(hass, entry, client, host):
    with patch("custom_components.iliadbox.IliadboxClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        coordinator = entry.runtime_data
        registry = er.async_get(hass)
        tracker = next(
            e.entity_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.domain == "device_tracker"
        )
        assert tracker
        registry.async_update_entity(tracker, name="Personalized phone")
        original = registry.async_get(tracker)
        client.get_lan_hosts.return_value[0].update(active=False, last_activity=1)
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert registry.async_get(tracker).name == "Personalized phone"
        assert dr.async_get(hass).async_get(original.device_id)
        client.get_lan_hosts.return_value[0]["active"] = True
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert registry.async_get(tracker).id == original.id
        assert hass.states.get(tracker).state == "home"
        # Dynamic radio creation after setup; original entity IDs are retained.
        client.get_wifi_radios.return_value.append(
            {"id": 2, "phy_id": 1, "band": "6G", "clients": 1}
        )
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert registry.async_get_entity_id("sensor", "iliadbox", "box-1_radio_6g_clients")
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED


async def test_tracker_links_device_before_sensor_platforms_load(hass, entry, client):
    with (
        patch("custom_components.iliadbox.IliadboxClient", return_value=client),
        patch("custom_components.iliadbox.PLATFORMS", [Platform.DEVICE_TRACKER]),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        tracker = next(
            e
            for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
            if e.domain == "device_tracker"
        )
        assert tracker.unique_id == "aa:bb:cc:dd:ee:01"
        assert tracker.disabled_by is None
        assert dr.async_get(hass).async_get(tracker.device_id)
        assert hass.states.get(tracker.entity_id).state == "home"
        assert await hass.config_entries.async_unload(entry.entry_id)
