import {
  STYLE,
  esc,
  t,
  date,
  rate,
  duration,
  bytes,
  ipv4,
  subscribe,
} from "./shared.js?v=0.11.0";

export class IliadboxPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._boxes = [];
    this._selected = null;
    this._filter = "";
  }
  set hass(hass) {
    const changed = this._hass?.connection !== hass.connection;
    const languageChanged = this._hass?.language !== hass.language;
    this._hass = hass;
    if (!this._built || languageChanged) {
      this._build();
      this._render();
    }
    this.shadowRoot.querySelector("ha-menu-button").hass = hass;
    if (changed) {
      this._unsubscribe?.();
      this._unsubscribe = null;
    }
    if (this.isConnected) this._start();
  }
  set narrow(value) {
    this._narrow = value;
    if (this._built)
      this.shadowRoot.querySelector("ha-menu-button").narrow = value;
  }
  set panel(_value) {}
  set route(route) {
    this._select((route?.path || "").replace(/^\//, "").split("/")[0] || null);
  }
  connectedCallback() {
    if (this._hass) this._start();
  }
  disconnectedCallback() {
    this._unsubscribe?.();
    this._unsubscribe = null;
  }
  _start() {
    if (this._unsubscribe) return;
    this._unsubscribe = subscribe(
      this._hass,
      (boxes) => {
        this._boxes = boxes;
        this._readError = "";
        this._render();
      },
      (error) => {
        this._readError = String(error.message || error);
        this._render();
      },
    );
  }
  _select(id) {
    this._selected = id;
    this._actionError = "";
    if (this._built) this._render();
  }
  _navigate(id) {
    history.pushState(
      null,
      "",
      id ? `/iliadbox/${encodeURIComponent(id)}` : "/iliadbox",
    );
    window.dispatchEvent(
      new CustomEvent("location-changed", { detail: { replace: false } }),
    );
    this._select(id);
  }
  _build() {
    const tr = (key) => esc(t(this._hass, key));
    this.shadowRoot.innerHTML = `<style>${STYLE}:host{background:var(--primary-background-color);min-height:100vh}.toolbar{display:flex;align-items:center;gap:12px;padding:8px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff)}main{max-width:1200px;margin:auto;padding:16px}.boxbutton{width:100%;text-align:left}.big{font-size:23px}</style>
      <div class="toolbar"><ha-menu-button></ha-menu-button><button id="back">${tr("All boxes")}</button><strong id="title">Iliadbox</strong></div>
      <main><div id="error" role="alert" class="error"></div><button id="retry" hidden>${tr("Retry")}</button><div id="home" class="grid"></div><div id="detail" hidden>
      <div id="summary"></div><div class="card"><iliadbox-guest-manager></iliadbox-guest-manager></div>
      <section id="review" class="card"></section><section class="card"><h2>${tr("Devices")}</h2><div class="actions"><label>${tr("Search devices")}<input id="search" type="search"></label><label><span><input id="active" type="checkbox"> ${tr("Online only")}</span></label></div><div id="devices" class="scroll"></div></section>
      <section id="events" class="card"></section></div></main>`;
    this.shadowRoot.getElementById("back").onclick = () => this._navigate(null);
    this.shadowRoot.getElementById("retry").onclick = () => {
      this._unsubscribe?.();
      this._unsubscribe = null;
      this._start();
    };
    this.shadowRoot.getElementById("search").oninput = (event) => {
      this._filter = event.target.value.toLowerCase();
      this._renderDevices();
    };
    this.shadowRoot.getElementById("active").onchange = (event) => {
      this._active = event.target.checked;
      this._renderDevices();
    };
    this.shadowRoot.onclick = (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) return;
      const { action, id, mac } = button.dataset;
      if (action === "open") this._navigate(id);
      else this._action(action, mac);
    };
    this._built = true;
  }
  _box() {
    return this._boxes.find((box) => box.entry_id === this._selected);
  }
  _render() {
    const tr = (key) => esc(t(this._hass, key));
    const box = this._box();
    this.shadowRoot.getElementById("error").textContent = [
      this._readError &&
        `${t(this._hass, "Cannot read data")}: ${this._readError}`,
      this._actionError,
    ]
      .filter(Boolean)
      .join("\n");
    this.shadowRoot.getElementById("retry").hidden = !this._readError;
    this.shadowRoot.getElementById("back").hidden = !this._selected;
    this.shadowRoot.getElementById("title").textContent =
      box?.title || "Iliadbox";
    this.shadowRoot.getElementById("home").hidden = !!this._selected;
    this.shadowRoot.getElementById("detail").hidden = !this._selected;
    this.shadowRoot.getElementById("home").innerHTML =
      this._boxes
        .map(
          (item) =>
            `<button class="card boxbutton" data-action="open" data-id="${esc(item.entry_id)}"><h2>${esc(item.title)}</h2><div>${esc(item.model || "Iliadbox")} · ${esc(item.host)}</div><div class="row"><strong>${item.loaded && item.available ? esc(item.connection.state) : tr("Unavailable")}</strong><span>${esc(rate(item.connection?.rate_down))}</span></div><div>${tr("Devices")}: ${(item.hosts || []).filter((host) => host.active).length}</div></button>`,
        )
        .join("") || `<p>${tr("No box configured")}</p>`;
    const summary = this.shadowRoot.getElementById("summary");
    if (!box?.loaded)
      summary.innerHTML = `<p class="warning">${tr("Unavailable")}</p>`;
    else {
      const connection = box.connection,
        system = box.system;
      const disabled =
        this._busy || !box.available || !box.can_modify ? "disabled" : "";
      summary.innerHTML = `${!box.available ? `<div class="warning">${tr("Stale data")}</div>` : ""}${box.read_only ? `<div class="warning">${tr("Read only")}</div>` : !box.can_modify ? `<div class="warning">${tr("Missing settings permission")} · <a href="${esc(box.configuration_url)}" target="_blank" rel="noopener">${tr("Open router settings")}</a></div>` : ""}
      <div class="grid"><section class="card"><h2>${tr("Connection")} · ${esc(connection.state)}</h2><div class="row big"><span>↓ ${esc(rate(connection.rate_down))}</span><span>↑ ${esc(rate(connection.rate_up))}</span></div><div class="row"><span>${tr("Public IP")}</span><span class="mono">${esc(connection.ipv4)}</span></div><div class="mono">${esc(connection.ipv6)}</div><div class="row"><span>${tr("Bandwidth")}</span><span>↓ ${esc(rate(connection.bandwidth_down == null ? null : connection.bandwidth_down / 8))} · ↑ ${esc(rate(connection.bandwidth_up == null ? null : connection.bandwidth_up / 8))}</span></div><div class="row"><span>${tr("Traffic")}</span><span>↓ ${esc(bytes(connection.bytes_down))} · ↑ ${esc(bytes(connection.bytes_up))}</span></div></section>
      <section class="card"><h2>${esc(box.model)}</h2><div class="row"><span>${tr("Firmware")}</span><span>${esc(system.firmware_version)}</span></div><div class="row"><span>${tr("Uptime")}</span><span>${esc(duration(system.uptime_val))}</span></div>${(system.sensors || []).map((sensor) => `<div class="row"><span>${esc(sensor.id)}</span><span>${esc(sensor.value)} °C</span></div>`).join("")}${(system.fans || []).map((fan) => `<div class="row"><span>${esc(fan.id)}</span><span>${esc(fan.value)} rpm</span></div>`).join("")}${this._hass.user?.is_admin ? `<button class="danger" data-action="reboot" ${disabled}>${tr("Reboot")}</button>` : ""}</section>
      <section class="card"><h2>Wi-Fi</h2><div class="row"><span>${tr("Power saving")}</span><span>${tr(box.wifi.power_saving ? "Yes" : "No")}</span></div><div class="row"><span>${tr("MAC filter")}</span><span>${esc(box.wifi.mac_filter_state || "—")}</span></div>${!box.freshness?.radios ? `<p class="warning">${tr("Stale data")}</p>` : ""}${(box.radios || []).map((radio) => `<div class="row"><span>${esc(radio.band)} · ${esc(radio.ssid)}<br><span class="muted">AP ${esc(radio.phy_id)} / BSS ${esc(radio.id)}</span></span><span>${tr("Channel")}: ${esc(radio.channel)}<br>${tr("Clients")}: ${esc(radio.clients)}</span></div>`).join("")}${this._hass.user?.is_admin ? `<button data-action="wifi" ${disabled}>${tr(box.wifi.enabled ? "Turn Wi-Fi off" : "Turn Wi-Fi on")}</button>` : ""}</section></div>`;
    }
    this.shadowRoot.querySelector("iliadbox-guest-manager").data = {
      hass: this._hass,
      box,
    };
    this._renderDevices();
    this._renderEvents();
  }
  _renderDevices() {
    const box = this._box(),
      tr = (key) => esc(t(this._hass, key));
    const hosts = (box?.hosts || [])
      .filter((host) => !this._active || host.active)
      .filter((host) =>
        [
          host.primary_name,
          host.default_name,
          host.l2ident?.id,
          host.vendor_name,
          ipv4(host),
        ].some((value) =>
          String(value || "")
            .toLowerCase()
            .includes(this._filter),
        ),
      );
    this.shadowRoot.getElementById("devices").innerHTML =
      `<table><thead><tr><th>${tr("Name")}</th><th>IP / MAC</th><th>${tr("Status")}</th><th>${tr("Last activity")}</th></tr></thead><tbody>${hosts.map((host) => `<tr><td>${esc(host.primary_name || host.default_name || host.l2ident?.id)}<div class="muted">${esc(host.vendor_name)}</div></td><td class="mono">${esc(ipv4(host))}<br>${esc(host.l2ident?.id)}</td><td>${tr(host.active ? "Connected" : "Disconnected")}${this._hass.user?.is_admin && box.devices?.[host.l2ident?.id?.toLowerCase()] ? `<label>${tr("Status")}<select data-status-mac="${esc(host.l2ident.id.toLowerCase())}">${["new", "known", "ignored"].map((status) => `<option value="${status}" ${box.devices[host.l2ident.id.toLowerCase()].status === status ? "selected" : ""} ${status === "new" ? "disabled" : ""}>${tr({ new: "New", known: "Known", ignored: "Ignored" }[status])}</option>`).join("")}</select></label>` : ""}</td><td>${esc(date(this._hass, host.last_activity))}</td></tr>`).join("")}</tbody></table>`;
    this.shadowRoot
      .querySelectorAll("select[data-status-mac]")
      .forEach((select) => {
        select.disabled = !!this._busy;
        select.onchange = () =>
          this._action(select.value, select.dataset.statusMac);
      });
    const review = this.shadowRoot.getElementById("review");
    review.hidden = !this._hass.user?.is_admin;
    const newDevices = Object.entries(box?.devices || {}).filter(
      ([, device]) => device.status === "new",
    );
    review.innerHTML = `<h2>${tr("New devices")} (${newDevices.length})</h2>${newDevices.map(([mac, device]) => `<div class="row"><div><strong>${esc(device.name)}</strong><div class="mono">${esc(mac)}</div><div class="muted">${esc(device.vendor)}</div></div><div class="actions"><button data-action="known" data-mac="${esc(mac)}" ${this._busy ? "disabled" : ""}>${tr("Recognize")}</button><button data-action="ignored" data-mac="${esc(mac)}" ${this._busy ? "disabled" : ""}>${tr("Ignore")}</button></div></div>`).join("") || `<p class="muted">${tr("No new devices")}</p>`}`;
  }
  _renderEvents() {
    const box = this._box(),
      tr = (key) => esc(t(this._hass, key));
    const section = this.shadowRoot.getElementById("events");
    section.hidden = !this._hass.user?.is_admin;
    section.innerHTML = `<div class="row"><h2>${tr("Network events")}</h2><button data-action="clear" ${this._busy || !box?.loaded ? "disabled" : ""}>${tr("Clear history")}</button></div><p class="muted">${tr("Last 200 events, up to 7 days")}</p><ul>${(box?.events || []).map((event) => `<li><strong>${tr(event.type)}</strong> ${esc(event.name || "")} ${event.previous != null ? `${esc(event.previous)} → ${esc(event.current)}` : ""}${event.access_id != null ? ` #${esc(event.access_id)}` : ""}${event.duration_seconds != null ? ` · ${esc(duration(event.duration_seconds))}` : ""}<div class="muted">${esc(date(this._hass, event.timestamp))}${event.mac ? ` · ${esc(event.mac)}` : ""}</div></li>`).join("") || `<li>${tr("No events yet")}</li>`}</ul>`;
  }
  async _action(action, mac) {
    const box = this._box();
    if (this._busy || !box?.loaded || !this._hass.user?.is_admin) return;
    let message;
    if (action === "known" || action === "ignored")
      message = { type: "iliadbox/device_status", mac, status: action };
    else if (action === "clear") {
      if (
        !confirm(
          t(this._hass, "Clear the timeline? Device recognition will be kept."),
        )
      )
        return;
      message = { type: "iliadbox/clear_history" };
    } else {
      if (!box.can_modify || !box.available) return;
      if (action === "reboot" && !confirm(t(this._hass, "Reboot the router?")))
        return;
      if (
        action === "wifi" &&
        box.wifi.enabled &&
        !confirm(
          t(this._hass, "Turn off Wi-Fi? Wireless devices will disconnect."),
        )
      )
        return;
      message =
        action === "wifi"
          ? { type: "iliadbox/set_wifi", enabled: !box.wifi.enabled }
          : { type: "iliadbox/reboot" };
    }
    this._busy = true;
    this._actionError = "";
    this._render();
    try {
      await this._hass.callWS({ ...message, entry_id: box.entry_id });
    } catch (error) {
      this._actionError = `${t(this._hass, "Operation failed")}: ${error.message || error}`;
    } finally {
      this._busy = false;
      this._render();
    }
  }
}
if (!customElements.get("iliadbox-panel"))
  customElements.define("iliadbox-panel", IliadboxPanel);
