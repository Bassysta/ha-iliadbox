# Changelog

## 0.7.0

- **Every value is an entity.** New box entities: connection state and type, IPv4 port range, firmware, serial, MAC, board, disk status, Wi-Fi power saving, MAC filter, guest network, connected/known devices, total Wi-Fi clients.
- **Wi-Fi radios** (2.4 / 5 GHz): active, clients, network, channel, channel width, encryption.
- **Each LAN device**: Connected, IP address, connection type, Wi-Fi signal, band, network, standard, download/upload rate, session traffic, last activity, first seen.
- **Each guest access**: expiry sensor, added and removed automatically.
- **Configure** now changes every setting: host, port, HTTPS, certificate check, polling interval and log level. Connection changes are tested before saving.
- Default polling interval is now **60 seconds** (configurable 10-3600 s).

## 0.6.0

- Every LAN device is now a Home Assistant device with its tracker, enabled by default. Trackers created disabled by earlier versions are enabled automatically.
- Devices the box no longer lists can be deleted from the UI.
- New dashboard card `custom:iliadbox-guest-card` to create, show and revoke guest Wi-Fi accesses.
- New sensor *Guest Wi-Fi*: number of active accesses, with network name and access list (no passwords).

## 0.5.1

- Integration icon in `brand/`, shown by Home Assistant 2026.3+.

## 0.5.0

- HTTPS: new *Verify the certificate* option. Turn it off to accept the box self-signed certificate (needed when connecting by IP). Existing entries keep working without verification.
- With HTTPS on, port 80 is switched to 443 automatically.
- New **Reconfigure** step to change address, port and HTTPS settings without a new authorization.
- Clear error when the certificate cannot be verified.

## 0.4.0

First public release. Tested on iliadbox (r1), firmware 4.12.4, Freebox OS API 16.1.

- Config flow with authorization on the box display, re-authorization when the token is revoked.
- Sensors: connection state, rates, bandwidth, traffic, public IPs, line type, uptime, temperatures, fan.
- Device trackers for every LAN device.
- Wi-Fi switch and reboot button.
- Guest Wi-Fi: panel form, button with defaults, `iliadbox.create_guest_wifi` and `iliadbox.delete_guest_wifi` actions.
- Sidebar panel.
- Log level option (Error / Info / Debug).
