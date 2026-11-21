"""Actual HA config and options flows, including wrong-router reauth."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView

from custom_components.iliadbox.api import IliadboxConnectionError

INPUT = {"host": "192.0.2.1", "port": 80, "use_ssl": False, "verify_ssl": False}


async def test_config_flow(hass, client):
    with (
        patch("custom_components.iliadbox.config_flow.IliadboxClient", return_value=client),
        patch("homeassistant.config_entries.ConfigEntries.async_setup", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            "iliadbox", context={"source": SOURCE_USER}, data=INPUT
        )
        assert result["step_id"] == "link"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()


async def test_reauth_rejects_other_box(hass, entry, client):
    client.info["uid"] = "box-other"
    with patch("custom_components.iliadbox.config_flow.IliadboxClient", return_value=client):
        result = await hass.config_entries.flow.async_init(
            "iliadbox",
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
        assert result["type"] is FlowResultType.ABORT and result["reason"] == "wrong_box"
        client.request_authorization.assert_not_awaited()


async def test_reconfigure_transport_error_not_invalid_auth(hass, entry, client):
    client.open_session.side_effect = IliadboxConnectionError("timeout")
    with patch("custom_components.iliadbox.config_flow.IliadboxClient", return_value=client):
        result = await hass.config_entries.flow.async_init(
            "iliadbox",
            context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
            data=INPUT,
        )
        assert result["errors"] == {"base": "cannot_connect"}


async def test_options_on_minimum_ha(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **INPUT,
            "scan_interval": 60,
            "max_age_days": 30,
            "log_level": "info",
            "read_only": True,
            "share_guest_qr": False,
            "notify_new_devices": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["notify_new_devices"] is True


async def test_forms_can_be_serialized_for_frontend(hass, entry):
    """A flow that works internally must also be renderable by HA's frontend."""
    results = [
        await hass.config_entries.flow.async_init("iliadbox", context={"source": SOURCE_USER}),
        await hass.config_entries.options.async_init(entry.entry_id),
    ]
    for result in results:
        schema = FlowManagerIndexView(hass.config_entries.flow)._prepare_result_json(result)[
            "data_schema"
        ]
        assert next(field for field in schema if field["name"] == "host")["type"] == "string"


async def test_options_reject_invalid_host_without_changing_entry(hass, entry):
    original_data = dict(entry.data)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **INPUT,
            "host": "http://example.com/path",
            "scan_interval": 60,
            "max_age_days": 30,
            "log_level": "info",
        },
    )
    assert result["errors"] == {"base": "cannot_connect"}
    assert dict(entry.data) == original_data
