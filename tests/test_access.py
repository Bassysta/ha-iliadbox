"""Authorization is enforced at every write boundary, not just the panel."""

from unittest.mock import patch

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized
import pytest

from custom_components.iliadbox.access import async_check_write
from custom_components.iliadbox.guest import async_create_guest, async_delete_guest
from custom_components.iliadbox.image import IliadboxGuestQrImage
from custom_components.iliadbox.panel import _box_data
from custom_components.iliadbox.services import async_setup_services


async def test_user_and_automation_policy(
    hass, coordinator, hass_admin_user, hass_read_only_user, entry
):
    await async_check_write(hass, coordinator, Context(user_id=hass_admin_user.id))
    await async_check_write(hass, coordinator, Context())
    with pytest.raises(Unauthorized):
        await async_check_write(hass, coordinator, Context(user_id=hass_read_only_user.id))
    with pytest.raises(Unauthorized):
        await async_check_write(hass, coordinator, Context(user_id="missing-user"))
    hass.config_entries.async_update_entry(entry, options={"read_only": True})
    with pytest.raises(HomeAssistantError):
        await async_check_write(hass, coordinator, Context())


async def test_service_denies_non_admin(hass, entry, coordinator, client, hass_read_only_user):
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    async_setup_services(hass)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            "iliadbox",
            "create_guest_wifi",
            {},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    client.create_guest_key.assert_not_awaited()


async def test_notifications_have_no_password_and_unique_ids(hass, coordinator, client, entry):
    with (
        patch.object(persistent_notification, "async_create") as create,
        patch.object(persistent_notification, "async_dismiss") as dismiss,
    ):
        await async_create_guest(hass, coordinator, "test", "synthetic-password", 24, 0, "net_only")
        first = create.call_args
        other = dict(entry.data)
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.iliadbox.coordinator import IliadboxCoordinator

        second_entry = MockConfigEntry(domain="iliadbox", unique_id="box-2", data=other)
        second_entry.add_to_hass(hass)
        second = IliadboxCoordinator(hass, second_entry, client)
        second.data = coordinator.data
        second.async_request_refresh = coordinator.async_request_refresh
        await async_create_guest(hass, second, "test", "synthetic-password", 24, 0, "net_only")
        assert first.kwargs["notification_id"] != create.call_args.kwargs["notification_id"]
        assert "synthetic-password" not in repr(create.call_args_list)
        await async_delete_guest(hass, coordinator, 2)
        assert dismiss.call_args.args[1] == first.kwargs["notification_id"]
        await second.async_shutdown()


async def test_qr_requires_explicit_opt_in_even_existing_entity(hass, entry, coordinator):
    image = IliadboxGuestQrImage(hass, coordinator)
    image.hass = hass
    assert not image.available
    assert await image.async_image() is None
    hass.config_entries.async_update_entry(entry, options={"share_guest_qr": True})
    image._update_shown()
    assert image.available
    assert (await image.async_image()).startswith(b"\x89PNG")
    coordinator.data["freshness"]["guest"] = False
    assert await image.async_image() is None


@pytest.mark.parametrize("admin", [False, True])
async def test_snapshots_never_contain_password(hass, entry, coordinator, admin):
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    snapshot = _box_data(hass, admin)
    assert "synthetic-password" not in repr(snapshot)
    assert "synthetic-token" not in repr(snapshot)
    if not admin:
        assert snapshot[0]["devices"] == {} and snapshot[0]["events"] == []


@pytest.mark.parametrize("platform", ["button", "switch"])
async def test_entity_actions_deny_non_admin(
    hass, coordinator, hass_read_only_user, client, platform
):
    from custom_components.iliadbox.button import IliadboxRebootButton
    from custom_components.iliadbox.switch import IliadboxWifiSwitch

    entity = (
        IliadboxRebootButton(coordinator, "reboot")
        if platform == "button"
        else IliadboxWifiSwitch(coordinator, "wifi")
    )
    entity.hass = hass
    entity.async_set_context(Context(user_id=hass_read_only_user.id))
    with pytest.raises(Unauthorized):
        await (entity.async_press() if platform == "button" else entity.async_turn_off())
    client.reboot.assert_not_awaited()
    client.set_wifi_enabled.assert_not_awaited()


async def test_snapshot_drops_unexpected_sensitive_fields(hass, entry, coordinator):
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    for source in ("system", "wifi", "connection"):
        coordinator.data[source]["unexpected_password"] = "DO-NOT-EXPOSE"
    next(iter(coordinator.data["hosts"].values()))["credentials"] = "DO-NOT-EXPOSE"
    assert "DO-NOT-EXPOSE" not in repr(_box_data(hass, True))
