"""Fixtures using the actual Home Assistant test framework; no router needed."""

from copy import deepcopy
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.iliadbox.const import DOMAIN

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    with patch("homeassistant.components.http.HomeAssistantHTTP.start", new_callable=AsyncMock):
        yield


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="box-1",
        title="Test box",
        data={
            "host": "192.0.2.1",
            "port": 80,
            "use_ssl": False,
            "verify_ssl": False,
            "app_token": "synthetic-token",
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def host():
    return {
        "l2ident": {"type": "mac_address", "id": "aa:bb:cc:dd:ee:01"},
        "primary_name": "Test phone",
        "active": True,
        "last_activity": time.time(),
        "l3connectivities": [{"af": "ipv4", "active": True, "addr": "192.0.2.20"}],
    }


@pytest.fixture
def client(host):
    client = Mock()
    client.host = "192.0.2.1"
    client.configuration_url = "http://192.0.2.1"
    client.permissions = {"settings"}
    client.permissions_checked_at = time.monotonic()
    client.info = {
        "uid": "box-1",
        "device_name": "Test box",
        "box_model_name": "Iliadbox",
        "api_version": "16.1",
        "api_base_url": "/api/",
    }
    client.discover = AsyncMock(return_value=client.info)
    client.open_session = AsyncMock()
    client.request_authorization = AsyncMock(return_value=("synthetic-token", 1))
    client.authorization_status = AsyncMock(return_value="granted")
    client.get_connection = AsyncMock(
        return_value={"state": "up", "ipv4": "198.51.100.1", "rate_down": 123}
    )
    client.get_system = AsyncMock(
        return_value={"uptime_val": 3600, "mac": "aa:bb:cc:dd:ee:ff", "firmware_version": "4.12.4"}
    )
    client.get_lan_hosts = AsyncMock(return_value=[deepcopy(host)])
    client.get_wifi_config = AsyncMock(return_value={"enabled": True})
    client.get_guest_keys = AsyncMock(
        return_value=[
            {
                "id": 1,
                "remaining": 3600,
                "params": {
                    "key": "synthetic-password",
                    "description": "Test",
                    "access_type": "net_only",
                },
            }
        ]
    )
    client.get_wifi_radios = AsyncMock(
        return_value=[
            {
                "id": 1,
                "phy_id": 0,
                "band": "5G",
                "clients": 2,
                "guest_ssid": "test-guest",
                "ssid": "test",
                "state": "active",
            }
        ]
    )
    client.create_guest_key = AsyncMock(return_value={"id": 2, "remaining": 3600})
    client.delete_guest_key = AsyncMock()
    client.set_wifi_enabled = AsyncMock()
    client.reboot = AsyncMock()
    return client


@pytest.fixture
async def coordinator(hass, entry, client):
    from custom_components.iliadbox.coordinator import IliadboxCoordinator

    coordinator = IliadboxCoordinator(hass, entry, client)
    entry.runtime_data = coordinator
    await coordinator.history.async_load()
    await coordinator.async_refresh()
    yield coordinator
    await coordinator.async_shutdown()
    await coordinator.history.async_save()
