"""LAN IP sensors must not expose inactive addresses as current values."""

from unittest.mock import patch

from homeassistant.const import STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er


async def test_host_ip_tracks_active_address_and_reconnection(hass, entry, client):
    """Preserve the entity across address changes and offline/online transitions."""
    with patch("custom_components.iliadbox.IliadboxClient", return_value=client):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id("sensor", "iliadbox", "box-1_aa:bb:cc:dd:ee:01_ip")
        assert entity_id is not None
        original = registry.async_get(entity_id)
        assert hass.states.get(entity_id).state == "192.0.2.20"

        host = client.get_lan_hosts.return_value[0]
        host["l3connectivities"] = [
            {"af": "ipv4", "addr": "192.0.2.20", "active": False},
            {"af": "ipv4", "addr": "192.0.2.30", "active": True},
        ]
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "192.0.2.30"

        host["active"] = False
        host["l3connectivities"][1]["active"] = False
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNKNOWN

        # An active IPv6 address must not revive a historical IPv4 address.
        host["active"] = True
        host["l3connectivities"].append({"af": "ipv6", "addr": "2001:db8::1", "active": True})
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNKNOWN

        for connectivities in ([], None):
            host["l3connectivities"] = connectivities
            await entry.runtime_data.async_refresh()
            await hass.async_block_till_done()
            assert hass.states.get(entity_id).state == STATE_UNKNOWN

        host.pop("l3connectivities")
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNKNOWN

        host["l3connectivities"] = [{"af": "ipv4", "addr": "192.0.2.30", "active": True}]
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "192.0.2.30"
        assert registry.async_get(entity_id).id == original.id
        assert await hass.config_entries.async_unload(entry.entry_id)
