# Changelog

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
