"""QR code of the latest guest Wi-Fi access, as an image entity.

The QR code contains the guest password: every Home Assistant user who can
see the entity can read it. Disable the entity if that is not wanted.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_SHARE_GUEST_QR
from .coordinator import IliadboxConfigEntry, IliadboxCoordinator
from .entity import IliadboxEntity
from .guest import wifi_qr


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IliadboxConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([IliadboxGuestQrImage(hass, entry.runtime_data)])


class IliadboxGuestQrImage(IliadboxEntity, ImageEntity):
    """Scan to join the guest network with the most recently created access."""

    _attr_translation_key = "guest_qr"
    _attr_content_type = "image/png"
    _attr_entity_registry_enabled_default = False

    def __init__(self, hass: HomeAssistant, coordinator: IliadboxCoordinator) -> None:
        IliadboxEntity.__init__(self, coordinator, "guest_qr")
        ImageEntity.__init__(self, hass)
        self._shown: tuple[Any, ...] | None = None
        self._update_shown()

    def _latest(self) -> dict[str, Any] | None:
        # Access ids grow with each creation: the highest is the newest
        if not self.coordinator.config_entry.options.get(CONF_SHARE_GUEST_QR, False) or not all(
            self.coordinator.data["freshness"].values()
        ):
            return None
        keys = [
            k
            for k in self.coordinator.data["guest"]["keys"]
            if k.get("expires_at") is None or k["expires_at"] > dt_util.utcnow().timestamp()
        ]
        return max(keys, key=lambda k: k["id"]) if keys else None

    def _update_shown(self) -> None:
        """Bump image_last_updated when the QR content changes, so cards reload it."""
        access = self._latest()
        ssid = self.coordinator.data["guest"]["ssid"]
        shown = (access["id"], ssid, access.get("params", {}).get("key")) if access else None
        if shown != self._shown:
            self._shown = shown
            self._attr_image_last_updated = dt_util.utcnow()

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._shown is not None
            and bool(self._shown[1])
            and bool(self._shown[2])
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        access = self._latest()
        if not access:
            return {}
        params = access.get("params", {})
        return {
            "ssid": self.coordinator.data["guest"]["ssid"],
            "access_id": access["id"],
            "description": params.get("description"),
            "access_type": params.get("access_type"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_shown()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        if not self.available or not self._latest():
            return None
        _, ssid, password = self._shown
        return await self.hass.async_add_executor_job(wifi_qr, ssid, password, "png")
