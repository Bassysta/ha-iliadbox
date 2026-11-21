"""HTTP contract, auth classification, retry and concurrency regression tests."""

import asyncio
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from custom_components.iliadbox.api import (
    IliadboxAuthError,
    IliadboxClient,
    IliadboxConnectionError,
    IliadboxError,
    IliadboxSSLError,
    normalize_host,
)


class Response:
    def __init__(self, data, status=200, wait=None):
        self.data, self.status, self.wait = data, status, wait

    async def __aenter__(self):
        if self.wait:
            await self.wait.wait()
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, **kwargs):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientError(f"HTTP {self.status}")


def make_client():
    client = IliadboxClient(Mock(), "192.0.2.1", 80, app_token="synthetic-token")
    client._base_url = "http://192.0.2.1/api/v16/"
    client._session_token = "old-session"
    return client


@pytest.mark.parametrize(
    "error",
    [
        IliadboxConnectionError("timeout"),
        IliadboxSSLError("TLS"),
        IliadboxError("busy"),
        IliadboxAuthError("revoked"),
    ],
)
async def test_login_preserves_error_type(error):
    client = make_client()
    client._request = AsyncMock(side_effect=[{"challenge": "test"}, error])
    with pytest.raises(type(error)) as raised:
        await client.open_session()
    assert type(raised.value) is type(error)


@pytest.mark.parametrize("body", [[], None, "bad", {}, {"success": "yes"}])
async def test_bad_response(body):
    client = make_client()
    client._session.request.return_value = Response(body)
    with pytest.raises(IliadboxError):
        await client.get_system()


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_http_errors_remain_recoverable(status):
    client = make_client()
    client._session.request.return_value = Response("unavailable", status)
    with pytest.raises(IliadboxConnectionError):
        await client.open_session()


@pytest.mark.parametrize(
    "info",
    [
        [],
        {},
        {"api_version": "oops", "api_base_url": "/api/"},
        {"api_version": "16.1", "api_base_url": "//evil.test/api/"},
    ],
)
async def test_discovery_validates(info):
    client = make_client()
    client._session.get.return_value = Response(info)
    with pytest.raises(IliadboxError):
        await client.discover()


async def test_discovery_ipv6():
    client = IliadboxClient(Mock(), "[2001:db8::1]", 8443, True)
    client._session.get.return_value = Response({"api_version": "16.1", "api_base_url": "/api/"})
    await client.discover()
    assert client.configuration_url == "https://[2001:db8::1]:8443"
    assert client._base_url.endswith("/api/v16/")


@pytest.mark.parametrize(
    "host", ["http://box", "box/path", "user@box", "", "bad host", "bad..host"]
)
def test_host_validation(host):
    with pytest.raises(ValueError):
        normalize_host(host)


async def test_session_retried_once():
    client = make_client()
    client._session.request.side_effect = [
        Response({"success": False, "error_code": "auth_required"}),
        Response({"success": True, "result": {"challenge": "test"}}),
        Response(
            {
                "success": True,
                "result": {"session_token": "new-session", "permissions": {"settings": True}},
            }
        ),
        Response({"success": True, "result": {"state": "up"}}),
    ]
    assert await client.get_connection() == {"state": "up"}
    assert client._session.request.call_count == 4


async def test_late_expiry_does_not_invalidate_new_session():
    client = make_client()
    release = asyncio.Event()
    started = asyncio.Event()

    def request(method, url, **kwargs):
        if kwargs["headers"].get("X-Fbx-App-Auth") == "old-session":
            started.set()
            return Response({"success": False, "error_code": "auth_required"}, wait=release)
        return Response({"success": True, "result": {"state": "up"}})

    client._session.request.side_effect = request
    task = asyncio.create_task(client.get_connection())
    await started.wait()
    client._session_token = "new-session"
    client._open_session = AsyncMock()
    release.set()
    assert await task == {"state": "up"}
    client._open_session.assert_not_awaited()


async def test_no_blind_retry_after_write_timeout():
    client = make_client()
    client._session.request.side_effect = TimeoutError
    with pytest.raises(IliadboxConnectionError):
        await client.reboot()
    assert client._session.request.call_count == 1


async def test_radio_summary_has_no_secret():
    client = make_client()
    client._request = AsyncMock(
        side_effect=[
            [
                {
                    "id": 1,
                    "phy_id": 0,
                    "status": {"band": "5G"},
                    "bss_params": {"ssid": "test", "key": "SENSITIVE"},
                }
            ],
            [{"id": 0, "status": {"primary_channel": 36}}],
        ]
    )
    radios = await client.get_wifi_radios()
    assert radios[0]["id"] == 1 and radios[0]["channel"] == 36
    assert "SENSITIVE" not in repr(radios)
