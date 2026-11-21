"""Local network journal and first-seen device tracking, isolated per box."""

from __future__ import annotations

from copy import deepcopy
import time
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import CONF_NOTIFY_NEW_DEVICES, DOMAIN

MAX_EVENTS = 200
RETENTION_SECONDS = 7 * 86400


class NetworkHistory:
    """Persist only explicitly selected network metadata, never API payloads."""

    def __init__(self, hass: HomeAssistant, entry: Any) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.network")
        self.data: dict[str, Any] = {
            "initialized": False,
            "devices": {},
            "events": [],
            "last": {},
            "next_id": 1,
        }
        self._reachable: bool | None = None

    async def async_load(self) -> None:
        if saved := await self.store.async_load():
            self.data.update(saved)
        self._prune()

    async def async_save(self) -> None:
        await self.store.async_save(self.data)

    def _save_later(self) -> None:
        self.store.async_delay_save(lambda: self.data, 10)

    def _prune(self) -> None:
        cutoff = time.time() - RETENTION_SECONDS
        self.data["events"] = [e for e in self.data["events"] if e["timestamp"] >= cutoff][
            -MAX_EVENTS:
        ]

    @property
    def events(self) -> list[dict[str, Any]]:
        self._prune()
        return list(reversed(self.data["events"]))

    def _emit(self, kind: str, **details: Any) -> None:
        event = {
            "id": self.data["next_id"],
            "timestamp": time.time(),
            "type": kind,
            **details,
        }
        self.data["next_id"] += 1
        self.data["events"].append(event)
        self._prune()
        payload = {"entry_id": self.entry.entry_id, **event}
        self.hass.bus.async_fire(f"{DOMAIN}_network_event", payload)
        if kind == "new_device":
            self.hass.bus.async_fire(f"{DOMAIN}_new_device", payload)
            if self.entry.options.get(CONF_NOTIFY_NEW_DEVICES, False):
                italian = self.hass.config.language.startswith("it")
                persistent_notification.async_create(
                    self.hass,
                    (
                        "Un nuovo dispositivo è apparso sulla rete. Apri il pannello Iliadbox per riconoscerlo o ignorarlo."
                        if italian
                        else "A new device appeared on the network. Open the Iliadbox panel to recognize or ignore it."
                    ),
                    title=("Nuovo dispositivo" if italian else "New device")
                    + f": {details['name']}",
                    notification_id=self._notification_id(details["mac"]),
                )
        self._save_later()

    def _notification_id(self, mac: str) -> str:
        return f"{DOMAIN}_{self.entry.entry_id}_new_{mac}"

    def set_device_status(self, mac: str, status: str) -> None:
        if status not in {"known", "ignored"} or mac not in self.data["devices"]:
            raise ValueError("Unknown device or invalid status")
        self.data["devices"][mac]["status"] = status
        persistent_notification.async_dismiss(self.hass, self._notification_id(mac))
        self._save_later()

    def clear(self) -> None:
        """Clear the timeline while retaining device recognition and baselines."""
        self.data["events"] = []
        self._save_later()

    def reachable(self, value: bool) -> None:
        if self._reachable is not None and self._reachable != value:
            self._emit("router_available" if value else "router_unavailable")
        self._reachable = value

    def observe(self, data: dict[str, Any], all_hosts: dict[str, Any]) -> None:
        """Compare successful samples. The first sample establishes a baseline."""
        before = deepcopy(self.data)
        self.reachable(True)
        old = self.data["last"]
        connection, system = data["connection"], data["system"]
        current = {
            "wan": connection.get("state"),
            "ipv4": connection.get("ipv4"),
            "uptime": system.get("uptime_val"),
            "wifi": data["wifi"].get("enabled"),
            "active": sorted(mac for mac, host in all_hosts.items() if host.get("active")),
        }
        if data["freshness"]["guest"]:
            current["guest_ids"] = sorted(k["id"] for k in data["guest"]["keys"])
        elif "guest_ids" in old:
            current["guest_ids"] = old["guest_ids"]
        if old:
            for field, event_type in (
                ("wan", "wan_changed"),
                ("ipv4", "public_ip_changed"),
                ("wifi", "wifi_changed"),
            ):
                if (
                    old.get(field) is not None
                    and current[field] is not None
                    and old[field] != current[field]
                ):
                    details = {"previous": old[field], "current": current[field]}
                    if field == "wan":
                        if current[field] != "up" and old[field] == "up":
                            self.data["wan_down_since"] = time.time()
                        elif (
                            current[field] == "up"
                            and (since := self.data.pop("wan_down_since", None)) is not None
                        ):
                            details["duration_seconds"] = round(time.time() - since)
                    self._emit(event_type, **details)
            if (
                isinstance(current["uptime"], (int, float))
                and isinstance(old.get("uptime"), (int, float))
                and current["uptime"] < old["uptime"]
            ):
                self._emit("router_restarted")
            if "guest_ids" in old and "guest_ids" in current and data["freshness"]["guest"]:
                for key in set(current["guest_ids"]) - set(old["guest_ids"]):
                    self._emit("guest_created", access_id=key)
                for key in set(old["guest_ids"]) - set(current["guest_ids"]):
                    self._emit("guest_removed", access_id=key)

        devices = self.data["devices"]
        for mac, host in all_hosts.items():
            name = str(host.get("primary_name") or host.get("default_name") or mac)[:255]
            is_new = mac not in devices
            if is_new:
                devices[mac] = {
                    "name": name,
                    "status": "new" if self.data["initialized"] and host.get("active") else "known",
                    "first_seen": time.time(),
                    "vendor": str(host.get("vendor_name") or "")[:255],
                }
                if devices[mac]["status"] == "new":
                    self._emit("new_device", mac=mac, name=name, vendor=devices[mac]["vendor"])
            devices[mac]["name"] = name
            if old and not is_new and devices[mac]["status"] != "ignored":
                was_active = mac in old.get("active", [])
                if was_active != bool(host.get("active")):
                    self._emit(
                        "device_connected" if host.get("active") else "device_disconnected",
                        mac=mac,
                        name=name,
                    )
        # A host omitted from a successful LAN list is no longer connected.
        for mac in set(old.get("active", [])) - all_hosts.keys():
            if mac in devices and devices[mac]["status"] != "ignored":
                self._emit("device_disconnected", mac=mac, name=devices[mac]["name"])
        self.data["initialized"] = True
        self.data["last"] = current
        self._prune()
        if before != self.data:
            self._save_later()
