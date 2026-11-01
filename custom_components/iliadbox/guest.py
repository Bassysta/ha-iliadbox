"""Guest Wi-Fi access shared by the services, the button and the panel."""

from __future__ import annotations

import io
import logging
import secrets
import string
from datetime import timedelta
from typing import Any

from segno import helpers as segno_helpers

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .coordinator import IliadboxCoordinator

_LOGGER = logging.getLogger(__name__)

ACCESS_TYPES = ["net_only", "full"]
DEFAULT_HOURS = 24
DEFAULT_ACCESS_TYPE = "net_only"
DEFAULT_MAX_DEVICES = 0  # 0 = unlimited
MAX_HOURS = 8760

# No look-alike characters, so the password is easy to type on a phone
_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0OoIl1")


def generate_password(length: int = 12) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def wifi_qr(ssid: str, password: str, kind: str = "svg") -> bytes:
    """Standard Wi-Fi QR code (WIFI:T:WPA;S:...;P:...;;), as SVG or PNG.

    Phone cameras read it and offer to join the network.
    """
    qr = segno_helpers.make_wifi(ssid=ssid, password=password, security="WPA")
    buf = io.BytesIO()
    if kind == "png":
        qr.save(buf, kind="png", scale=10, border=2)
    else:
        qr.save(buf, kind="svg", scale=5, border=2, xmldecl=False, svgns=True, light="#fff")
    return buf.getvalue()


def access_qr_svg(coordinator: IliadboxCoordinator, access: dict[str, Any]) -> str | None:
    """QR of an access as inline SVG, or None if the box gave no network name."""
    ssid = coordinator.data["guest"]["ssid"]
    password = access.get("params", {}).get("key")
    if not ssid or not password:
        return None
    return wifi_qr(ssid, password).decode()


def validate(
    description: str, password: str, hours: int, max_devices: int, access_type: str
) -> None:
    """Raise ValueError with a user-facing message if a parameter is invalid."""
    if not description.strip():
        raise ValueError("Description is required")
    if len(description) > 64:
        raise ValueError("Description must be at most 64 characters")
    if not 8 <= len(password) <= 63 or not password.isascii() or not password.isprintable():
        raise ValueError("Password must be 8-63 printable ASCII characters")
    if not 1 <= hours <= MAX_HOURS:
        raise ValueError(f"Duration must be between 1 and {MAX_HOURS} hours")
    if max_devices < 0:
        raise ValueError("Max devices must be 0 (unlimited) or more")
    if access_type not in ACCESS_TYPES:
        raise ValueError(f"Access type must be one of {', '.join(ACCESS_TYPES)}")


async def async_create_guest(
    hass: HomeAssistant,
    coordinator: IliadboxCoordinator,
    description: str,
    password: str,
    hours: int,
    max_devices: int,
    access_type: str,
) -> dict[str, Any]:
    """Create the access on the box, notify the password and return its details."""
    validate(description, password, hours, max_devices, access_type)
    result = await coordinator.client.create_guest_key(
        description.strip(), password, hours * 3600, max_devices, access_type
    )
    await coordinator.async_request_refresh()

    ssid = coordinator.data["guest"]["ssid"]
    expires = dt_util.now() + timedelta(seconds=result.get("remaining", hours * 3600))
    details = {
        "id": result["id"],
        "ssid": ssid,
        "password": password,
        "description": description.strip(),
        "duration_hours": hours,
        "max_devices": max_devices,
        "access_type": access_type,
        "expires": expires.isoformat(),
    }
    persistent_notification.async_create(
        hass,
        f"**Network:** `{ssid}`\n\n**Password:** `{password}`\n\n"
        f"Access: {'internet only' if access_type == 'net_only' else 'full network'} · "
        f"devices: {max_devices or 'unlimited'} · "
        f"expires: {expires.strftime('%Y-%m-%d %H:%M')}",
        title=f"Guest Wi-Fi created: {details['description']}",
        notification_id=f"iliadbox_guest_{result['id']}",
    )
    _LOGGER.info("Guest Wi-Fi access %s created, expires %s", result["id"], details["expires"])
    return details


async def async_delete_guest(
    hass: HomeAssistant, coordinator: IliadboxCoordinator, access_id: int
) -> None:
    await coordinator.client.delete_guest_key(access_id)
    persistent_notification.async_dismiss(hass, f"iliadbox_guest_{access_id}")
    await coordinator.async_request_refresh()
