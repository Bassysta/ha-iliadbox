// Sidebar panel for the Iliadbox integration. Plain web component, no build step.
// Home: one card per configured box. /iliadbox/<entry_id>: management of that box.

const REFRESH_MS = 10000;
const PANEL_URL = "/iliadbox";
const ICON_URL = "/iliadbox_static/brand/icon.png";
const MAX_HOURS = 8760;

// Same alphabet as guest.generate_password(): no look-alike characters
const PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
const generatePassword = (length = 12) =>
  Array.from(crypto.getRandomValues(new Uint32Array(length)), (n) => PW_ALPHABET[n % PW_ALPHABET.length]).join("");

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

const fmtBytes = (b) => {
  if (b == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (b >= 1000 && i < units.length - 1) {
    b /= 1000;
    i++;
  }
  return `${b.toFixed(i ? 1 : 0)} ${units[i]}`;
};

const fmtBits = (b) =>
  b == null ? "—" : b >= 1e9 ? `${(b / 1e9).toFixed(1)} Gbit/s` : `${Math.round(b / 1e6)} Mbit/s`;

const ago = (ts) => {
  if (!ts) return "—";
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
};

const fmtUptime = (s) => {
  if (s == null) return "—";
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`;
};

// The box localizes sensor names (e.g. Italian): derive English names from the ids
const sensorName = (id) =>
  id.startsWith("temp_") ? `Temperature ${id.slice(5).toUpperCase()}`
  : /^fan(\d+)/.test(id) ? `Fan ${Number(id.match(/^fan(\d+)/)[1]) + 1}`
  : id;

const ipv4 = (host) =>
  (host.l3connectivities || []).find((l) => l.af === "ipv4" && l.active)?.addr ||
  (host.l3connectivities || []).find((l) => l.af === "ipv4")?.addr ||
  "";

const STYLE = `
  :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); }
  .toolbar { display: flex; align-items: center; height: 56px; padding: 0 12px; gap: 8px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff)); font-size: 20px; }
  .toolbar .back { display: none; border: none; background: transparent; color: inherit; padding: 8px; font-size: 22px; line-height: 1; cursor: pointer; }
  .toolbar.detail .back { display: inline-flex; }
  .toolbar.detail ha-menu-button { display: none; }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 16px; }
  [hidden] { display: none !important; }
  .home { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
  .boxcard { cursor: pointer; display: flex; flex-direction: column; gap: 10px; transition: box-shadow 0.2s, transform 0.1s; }
  .boxcard:hover { box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25); }
  .boxcard:active { transform: scale(0.99); }
  .boxcard:focus-visible { outline: 2px solid var(--primary-color); }
  .boxhead { display: flex; gap: 14px; align-items: center; }
  .boxhead img { width: 56px; height: 56px; border-radius: 12px; flex: none; }
  .boxhead .t { font-size: 18px; font-weight: 600; }
  .boxhead .s { font-size: 13px; color: var(--secondary-text-color); margin-bottom: 4px; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .stat { background: var(--secondary-background-color, rgba(127, 127, 127, 0.08)); border-radius: 10px; padding: 8px; text-align: center; }
  .stat b { display: block; font-size: 16px; }
  .stat span { font-size: 11px; color: var(--secondary-text-color); }
  .boxcard.off { opacity: 0.75; cursor: default; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 16px; }
  .card { background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px); box-shadow: var(--ha-card-box-shadow, none);
    border: 1px solid var(--divider-color); padding: 16px; }
  .card h2 { margin: 0 0 12px; font-size: 16px; font-weight: 500; }
  .row { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; }
  .row span:first-child { color: var(--secondary-text-color); }
  .row span:last-child { text-align: right; overflow-wrap: anywhere; }
  .big { display: flex; gap: 24px; margin-bottom: 8px; }
  .big div { font-size: 24px; font-weight: 500; }
  .big small { display: block; font-size: 12px; color: var(--secondary-text-color); font-weight: 400; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 13px; color: #fff; }
  .ok { background: var(--success-color, #43a047); }
  .ko { background: var(--error-color, #db4437); }
  .actions { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
  button { font: inherit; padding: 8px 14px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button.danger { color: var(--error-color, #db4437); border-color: var(--error-color, #db4437); }
  button:disabled { opacity: 0.5; cursor: default; }
  .filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  .filters input[type=search] { flex: 1; min-width: 180px; padding: 8px 10px; border-radius: 8px; font: inherit;
    border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--divider-color); font-size: 14px; }
  th { color: var(--secondary-text-color); font-weight: 500; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .muted { color: var(--secondary-text-color); }
  .error { padding: 12px 16px; margin-bottom: 16px; border-radius: 8px; color: #fff; background: var(--error-color, #db4437); }
  .guest { margin-bottom: 16px; }
  #guest-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 16px; }
  #guest-form[hidden] { display: none; }
  #guest-form label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  #guest-form input, #guest-form select { padding: 8px 10px; border-radius: 8px; font: inherit; font-size: 14px; min-width: 0;
    border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
  .inline { display: flex; gap: 6px; }
  .inline input { flex: 1; }
  .form-foot { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .created { border: 2px solid var(--success-color, #43a047); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
  .mono { font-family: ui-monospace, Consolas, monospace; }
  .big-pw { font-size: 22px; font-weight: 600; letter-spacing: 1px; }
  @media (max-width: 700px) { .hide-narrow { display: none; } }
`;

class IliadboxPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._boxes = [];
    this._selected = null; // entry_id of the box being managed, null on the home
    this._filter = "";
    this._onlyActive = true;
    this._error = null;
    this._busy = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._build();
      this._start();
    }
    this._menu.hass = hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menu) this._menu.narrow = narrow;
  }

  set panel(_panel) {}

  // HA passes the part of the URL after /iliadbox: "" or "/<entry_id>"
  set route(route) {
    const id = (route?.path || "").replace(/^\//, "").split("/")[0] || null;
    if (id !== this._selected) this._select(id);
  }

  _navigate(id) {
    history.pushState(null, "", id ? `${PANEL_URL}/${id}` : PANEL_URL);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
    this._select(id);
  }

  _select(id) {
    this._selected = id;
    if (!this._built) return;
    // Each box starts with no leftover guest result
    this.shadowRoot.getElementById("guest-result").innerHTML = "";
    this._render();
    window.scrollTo(0, 0);
  }

  // The box shown on the detail page (only loaded boxes can be managed)
  _box() {
    return this._boxes.find((b) => b.entry_id === this._selected && b.loaded) || null;
  }

  connectedCallback() {
    if (this._hass) this._start();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
  }

  _start() {
    if (this._timer) return;
    this._refresh();
    this._timer = setInterval(() => this._refresh(), REFRESH_MS);
  }

  _build() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar"><ha-menu-button></ha-menu-button>
        <button class="back" id="back" title="All boxes" aria-label="All boxes">&larr;</button>
        <span id="title">Iliadbox</span></div>
      <div class="wrap">
        <div id="error"></div>
        <div id="home" class="home"></div>
        <div id="detail" hidden>
        <div id="boxes"></div>
        <div class="card guest">
          <h2 id="guest-title">Guest Wi-Fi</h2>
          <form id="guest-form" novalidate ${this._hass.user?.is_admin ? "" : "hidden"}>
            <label>Description
              <input name="description" maxlength="64" placeholder="e.g. Weekend guests" required>
            </label>
            <label>Password
              <span class="inline">
                <input name="password" minlength="8" maxlength="63" required>
                <button type="button" id="gen">Generate</button>
              </span>
            </label>
            <label>Duration (hours)
              <input name="duration_hours" type="number" min="1" max="${MAX_HOURS}" step="1" value="24" required>
            </label>
            <label>Max devices (0 = unlimited)
              <input name="max_devices" type="number" min="0" step="1" value="0" required>
            </label>
            <label>Access type
              <select name="access_type" required>
                <option value="net_only" selected>Internet only</option>
                <option value="full">Full network (internet and home devices)</option>
              </select>
            </label>
            <div class="form-foot">
              <span id="guest-hint" class="muted"></span>
              <button type="submit" class="primary" id="create" disabled>Create guest Wi-Fi</button>
            </div>
          </form>
          <div id="guest-result"></div>
          <div id="guest-list"></div>
        </div>
        <div class="card">
          <h2 id="dev-title">Devices</h2>
          <div class="filters">
            <input type="search" id="search" placeholder="Search name, IP, MAC, vendor">
            <label><input type="checkbox" id="active" checked> Connected only</label>
          </div>
          <div id="devices"></div>
        </div>
        </div>
      </div>`;
    this._menu = this.shadowRoot.querySelector("ha-menu-button");
    this._menu.narrow = this._narrow;
    this.shadowRoot.getElementById("back").addEventListener("click", () => this._navigate(null));
    const home = this.shadowRoot.getElementById("home");
    home.addEventListener("click", (e) => {
      const card = e.target.closest("[data-open]");
      if (card) this._navigate(card.dataset.open);
    });
    home.addEventListener("keydown", (e) => {
      const card = e.target.closest("[data-open]");
      if (card && (e.key === "Enter" || e.key === " ")) {
        e.preventDefault();
        this._navigate(card.dataset.open);
      }
    });
    this.shadowRoot.getElementById("search").addEventListener("input", (e) => {
      this._filter = e.target.value.toLowerCase();
      this._renderDevices();
    });
    this.shadowRoot.getElementById("active").addEventListener("change", (e) => {
      this._onlyActive = e.target.checked;
      this._renderDevices();
    });
    this.shadowRoot.getElementById("boxes").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (btn) this._action(btn.dataset.action, btn.dataset.entry, btn.dataset.enabled === "1");
    });

    const form = this.shadowRoot.getElementById("guest-form");
    form.elements.password.value = generatePassword();
    form.addEventListener("input", () => this._validateGuest());
    this.shadowRoot.getElementById("gen").addEventListener("click", () => {
      form.elements.password.value = generatePassword();
      this._validateGuest();
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      this._createGuest();
    });
    this.shadowRoot.getElementById("guest-list").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-delete]");
      if (btn) this._deleteGuest(btn.dataset.entry, Number(btn.dataset.delete), btn.dataset.name);
    });
    this._built = true;
    this._validateGuest();
  }

  _guestValues() {
    const f = this.shadowRoot.getElementById("guest-form").elements;
    return {
      description: f.description.value.trim(),
      password: f.password.value,
      duration_hours: f.duration_hours.value === "" ? NaN : Number(f.duration_hours.value),
      max_devices: f.max_devices.value === "" ? NaN : Number(f.max_devices.value),
      access_type: f.access_type.value,
    };
  }

  // Same rules as guest.validate() on the server
  _validateGuest() {
    const v = this._guestValues();
    let problem = "";
    if (!v.description) problem = "Enter a description.";
    else if (v.password.length < 8 || v.password.length > 63 || !/^[\x20-\x7e]+$/.test(v.password))
      problem = "Password must be 8-63 characters (letters, digits, symbols, no accents).";
    else if (!Number.isInteger(v.duration_hours) || v.duration_hours < 1 || v.duration_hours > MAX_HOURS)
      problem = `Duration must be a whole number of hours between 1 and ${MAX_HOURS}.`;
    else if (!Number.isInteger(v.max_devices) || v.max_devices < 0)
      problem = "Max devices must be 0 (unlimited) or a positive whole number.";
    else if (!["net_only", "full"].includes(v.access_type)) problem = "Choose an access type.";
    else if (!this._box()) problem = "No box available.";
    this.shadowRoot.getElementById("guest-hint").textContent = problem;
    this.shadowRoot.getElementById("create").disabled = !!problem || this._busy;
    return !problem;
  }

  async _createGuest() {
    if (!this._validateGuest()) return;
    const values = this._guestValues();
    this._busy = true;
    this._validateGuest();
    try {
      const res = await this._hass.callWS({
        type: "iliadbox/create_guest",
        entry_id: this._box().entry_id,
        ...values,
      });
      this.shadowRoot.getElementById("guest-result").innerHTML = `
        <div class="created">
          <div class="muted">Guest Wi-Fi "${esc(res.description)}" created</div>
          <div class="row"><span>Network</span><span class="mono">${esc(res.ssid || "—")}</span></div>
          <div class="row"><span>Password</span><span class="mono big-pw">${esc(res.password)}</span></div>
          <div class="row"><span>Access</span><span>${res.access_type === "full" ? "Full network" : "Internet only"} · ${
            res.max_devices ? `${res.max_devices} devices` : "unlimited devices"
          }</span></div>
          <div class="row"><span>Expires</span><span>${esc(new Date(res.expires).toLocaleString())}</span></div>
          <div class="actions"><button type="button" id="copy">Copy password</button>
            <button type="button" id="dismiss">Close</button></div>
        </div>`;
      this.shadowRoot.getElementById("copy").onclick = () => navigator.clipboard?.writeText(res.password);
      this.shadowRoot.getElementById("dismiss").onclick = () =>
        (this.shadowRoot.getElementById("guest-result").innerHTML = "");
      const f = this.shadowRoot.getElementById("guest-form").elements;
      f.description.value = "";
      f.password.value = generatePassword();
    } catch (err) {
      alert(`Cannot create guest Wi-Fi: ${err.message || err}`);
    }
    this._busy = false;
    this._validateGuest();
    this._refresh();
  }

  async _deleteGuest(entryId, accessId, name) {
    if (!confirm(`Revoke guest access "${name}"? Devices using it will be disconnected.`)) return;
    try {
      await this._hass.callWS({ type: "iliadbox/delete_guest", entry_id: entryId, access_id: accessId });
    } catch (err) {
      alert(`Cannot revoke guest access: ${err.message || err}`);
    }
    this._refresh();
  }

  _renderGuests() {
    const isAdmin = this._hass.user?.is_admin;
    const box = this._box();
    const ssid = box?.guest?.ssid;
    this.shadowRoot.getElementById("guest-title").textContent =
      ssid ? `Guest Wi-Fi · ${ssid}` : "Guest Wi-Fi";
    const keys = (box?.guest?.keys || []).map((k) => ({ ...k, entry: box.entry_id }));
    this.shadowRoot.getElementById("guest-list").innerHTML = keys.length
      ? `<table>
          <thead><tr><th>Description</th><th>Password</th><th>Access</th>
            <th class="hide-narrow">Devices</th><th>Expires in</th><th></th></tr></thead>
          <tbody>${keys
            .map((k) => {
              const p = k.params;
              return `<tr>
                <td>${esc(p.description)}</td>
                <td class="mono">${p.key ? esc(p.key) : "<span class='muted'>hidden</span>"}</td>
                <td>${p.access_type === "full" ? "Full network" : "Internet only"}</td>
                <td class="hide-narrow">${p.max_use_count ? esc(p.max_use_count) : "unlimited"}</td>
                <td>${fmtUptime(k.remaining)}</td>
                <td>${
                  isAdmin
                    ? `<button class="danger" data-delete="${esc(k.id)}" data-entry="${esc(k.entry)}" data-name="${esc(p.description)}">Revoke</button>`
                    : ""
                }</td>
              </tr>`;
            })
            .join("")}</tbody></table>`
      : `<div class="muted">No active guest access.</div>`;
  }

  async _refresh() {
    try {
      this._boxes = await this._hass.callWS({ type: "iliadbox/data" });
      this._error = null;
    } catch (err) {
      this._error = err.message || String(err);
      console.warn("Iliadbox panel: refresh failed", err);
    }
    this._render();
  }

  _render() {
    const detail = this._selected !== null;
    this.shadowRoot.querySelector(".toolbar").classList.toggle("detail", detail);
    this.shadowRoot.getElementById("error").innerHTML = this._error
      ? `<div class="error">${esc(this._error)}</div>`
      : "";
    this.shadowRoot.getElementById("home").hidden = detail;
    this.shadowRoot.getElementById("detail").hidden = !detail;
    if (!detail) {
      this.shadowRoot.getElementById("title").textContent = "Iliadbox";
      this._renderHome();
      return;
    }
    const box = this._boxes.find((b) => b.entry_id === this._selected);
    this.shadowRoot.getElementById("title").textContent = box ? box.title : "Iliadbox";
    this._renderBoxes();
    this._renderGuests();
    this._renderDevices();
    this._validateGuest();
  }

  _renderHome() {
    const home = this.shadowRoot.getElementById("home");
    if (!this._boxes.length) {
      home.innerHTML = this._error
        ? ""
        : `<div class="card muted">No Iliadbox configured. Add one from Settings → Devices &amp; services.</div>`;
      return;
    }
    home.innerHTML = this._boxes
      .map((box) => {
        const head = (status, cls) => `
          <div class="boxhead">
            <img src="${ICON_URL}" alt="">
            <div>
              <div class="t">${esc(box.title)}</div>
              <div class="s">${esc(box.model || "Iliadbox")} · ${esc(box.host || "")}</div>
              <span class="badge ${cls}">${status}</span>
            </div>
          </div>`;
        if (!box.loaded) {
          const why = ["setup_error", "setup_retry"].includes(box.state) ? "Not reachable" : esc(box.state);
          return `<div class="card boxcard off" title="${esc(box.reason || "")}">${head(why, "ko")}
            <div class="muted">Check this box in Settings → Devices &amp; services.</div></div>`;
        }
        const c = box.connection;
        const s = box.system;
        const up = c.state === "up";
        const active = box.hosts.filter((h) => h.active).length;
        const clients = (box.radios || []).reduce((n, r) => n + (r.clients || 0), 0);
        const status = !box.available ? "Stale data" : up ? "Online" : esc(c.state || "Offline");
        return `<div class="card boxcard" role="button" tabindex="0" data-open="${esc(box.entry_id)}">
          ${head(status, up && box.available ? "ok" : "ko")}
          <div class="row"><span>Public IP</span><span>${esc(c.ipv4 || "—")}</span></div>
          <div class="row"><span>Firmware · uptime</span><span>${esc(s.firmware_version || "—")} · ${fmtUptime(s.uptime_val)}</span></div>
          <div class="stats">
            <div class="stat"><b>${fmtBytes(c.rate_down)}/s</b><span>↓ download</span></div>
            <div class="stat"><b>${active}/${box.hosts.length}</b><span>devices online</span></div>
            <div class="stat"><b>${box.wifi.enabled ? clients : "off"}</b><span>Wi-Fi clients</span></div>
          </div>
          <div class="row"><span>Guest accesses</span><span>${(box.guest?.keys || []).length}</span></div>
        </div>`;
      })
      .join("");
  }

  async _action(action, entryId, enabled) {
    let msg;
    if (action === "wifi") {
      if (!enabled && !confirm("Turn off Wi-Fi? Wireless devices will lose their connection.")) return;
      msg = { type: "iliadbox/set_wifi", entry_id: entryId, enabled };
    } else {
      if (!confirm("Reboot the Iliadbox? The network will be down for a few minutes.")) return;
      msg = { type: "iliadbox/reboot", entry_id: entryId };
    }
    this._busy = true;
    this._render();
    try {
      await this._hass.callWS(msg);
    } catch (err) {
      alert(`Action failed: ${err.message || err}`);
    }
    this._busy = false;
    this._refresh();
  }

  _renderBoxes() {
    const isAdmin = this._hass.user?.is_admin;
    const selected = this._box();
    const missing = selected
      ? ""
      : `<div class="card muted">This box is not available. Go back to the list of boxes.</div>`;
    const dis = this._busy ? "disabled" : "";

    this.shadowRoot.getElementById("boxes").innerHTML =
      missing +
      (selected ? [selected] : [])
        .map((box) => {
          const c = box.connection;
          const s = box.system;
          const up = c.state === "up";
          const wifiOn = !!box.wifi.enabled;
          const temps = (s.sensors || [])
            .map((t) => `<div class="row"><span>${esc(sensorName(t.id))}</span><span>${esc(t.value)} °C</span></div>`)
            .join("");
          const fans = (s.fans || [])
            .map((f) => `<div class="row"><span>${esc(sensorName(f.id))}</span><span>${esc(f.value)} rpm</span></div>`)
            .join("");
          const unavailable = box.available
            ? ""
            : `<div class="error">Last update failed: data may be stale.</div>`;
          return `
            ${unavailable}
            <div class="grid">
              <div class="card">
                <h2>Connection <span class="badge ${up ? "ok" : "ko"}">${up ? "Online" : esc(c.state || "Offline")}</span></h2>
                <div class="big">
                  <div>${fmtBytes(c.rate_down)}/s<small>↓ download</small></div>
                  <div>${fmtBytes(c.rate_up)}/s<small>↑ upload</small></div>
                </div>
                <div class="row"><span>Bandwidth</span><span>↓ ${fmtBits(c.bandwidth_down)} · ↑ ${fmtBits(c.bandwidth_up)}</span></div>
                <div class="row"><span>Public IP</span><span>${esc(c.ipv4 || "—")}</span></div>
                <div class="row"><span>IPv6</span><span>${esc(c.ipv6 || "—")}</span></div>
                <div class="row"><span>Line</span><span>${esc(c.media || c.type || "—")}</span></div>
                <div class="row"><span>Traffic</span><span>↓ ${fmtBytes(c.bytes_down)} · ↑ ${fmtBytes(c.bytes_up)}</span></div>
              </div>
              <div class="card">
                <h2>${esc(box.title)}</h2>
                <div class="row"><span>Model</span><span>${esc(box.model || "—")}</span></div>
                <div class="row"><span>Firmware</span><span>${esc(s.firmware_version || "—")}</span></div>
                <div class="row"><span>Uptime</span><span>${fmtUptime(s.uptime_val)}</span></div>
                ${temps}${fans}
                ${isAdmin ? `<div class="actions"><button class="danger" data-action="reboot" data-entry="${esc(box.entry_id)}" ${dis}>Reboot</button></div>` : ""}
              </div>
              <div class="card">
                <h2>Wi-Fi <span class="badge ${wifiOn ? "ok" : "ko"}">${wifiOn ? "On" : "Off"}</span></h2>
                <div class="row"><span>Power saving</span><span>${box.wifi.power_saving ? "Yes" : "No"}</span></div>
                <div class="row"><span>MAC filter</span><span>${esc(box.wifi.mac_filter_state || "—")}</span></div>
                ${
                  isAdmin
                    ? `<div class="actions"><button class="${wifiOn ? "" : "primary"}" data-action="wifi" data-entry="${esc(box.entry_id)}" data-enabled="${wifiOn ? "0" : "1"}" ${dis}>${wifiOn ? "Turn off Wi-Fi" : "Turn on Wi-Fi"}</button></div>`
                    : ""
                }
              </div>
            </div>`;
        })
        .join("");
  }

  _renderDevices() {
    const hosts = this._box()?.hosts || [];
    const active = hosts.filter((h) => h.active).length;
    this.shadowRoot.getElementById("dev-title").textContent =
      `Devices · ${active} of ${hosts.length} connected`;

    const rows = hosts
      .map((h) => ({
        h,
        name: h.primary_name || h.default_name || h.l2ident?.id || "",
        ip: ipv4(h),
        mac: h.l2ident?.id || "",
      }))
      .filter(({ h }) => !this._onlyActive || h.active)
      .filter(({ h, name, ip, mac }) =>
        !this._filter ||
        [name, ip, mac, h.vendor_name].some((v) => (v || "").toLowerCase().includes(this._filter))
      )
      .sort((a, b) => (b.h.active - a.h.active) || a.name.localeCompare(b.name));

    this.shadowRoot.getElementById("devices").innerHTML = rows.length
      ? `<table>
          <thead><tr><th></th><th>Name</th><th>IP</th><th class="hide-narrow">MAC</th>
            <th class="hide-narrow">Vendor</th><th>Last activity</th></tr></thead>
          <tbody>${rows
            .map(
              ({ h, name, ip, mac }) => `<tr>
                <td><span class="dot ${h.active ? "ok" : "ko"}" title="${h.active ? "Connected" : "Not connected"}"></span></td>
                <td>${esc(name)}</td>
                <td>${esc(ip || "—")}</td>
                <td class="hide-narrow muted">${esc(mac)}</td>
                <td class="hide-narrow muted">${esc(h.vendor_name || "—")}</td>
                <td class="muted">${h.active ? "now" : ago(h.last_activity)}</td>
              </tr>`
            )
            .join("")}</tbody></table>`
      : `<div class="muted">No devices.</div>`;
  }
}

customElements.define("iliadbox-panel", IliadboxPanel);
