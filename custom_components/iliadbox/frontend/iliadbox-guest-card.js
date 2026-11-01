// Lovelace card for Iliadbox guest Wi-Fi: create (all fields required), show the
// password, list and revoke accesses. Loaded on every dashboard by the integration.
//
//   type: custom:iliadbox-guest-card
//   title: Guest Wi-Fi        # optional
//   entry_id: ...             # optional, only with several boxes

const REFRESH_MS = 10000;
const MAX_HOURS = 8760;

// Same alphabet as guest.generate_password(): no look-alike characters
const PW_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
const generatePassword = (length = 12) =>
  Array.from(crypto.getRandomValues(new Uint32Array(length)), (n) => PW_ALPHABET[n % PW_ALPHABET.length]).join("");

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

const fmtRemaining = (s) => {
  if (s == null) return "—";
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d}d ${h}h` : `${h}h ${m}m`;
};

const accessLabel = (t) => (t === "full" ? "Full network" : "Internet only");

const STYLE = `
  ha-card { padding: 16px; color: var(--primary-text-color); }
  .head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-bottom: 12px; }
  .title { font-size: 18px; font-weight: 600; }
  .muted { color: var(--secondary-text-color); font-size: 13px; }
  .mono { font-family: ui-monospace, Consolas, monospace; }
  form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
  form[hidden] { display: none; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--secondary-text-color); min-width: 0; }
  label.wide { grid-column: 1 / -1; }
  input, select { padding: 8px 10px; border-radius: 8px; font: inherit; font-size: 14px; min-width: 0;
    border: 1px solid var(--divider-color); background: var(--card-background-color, transparent); color: var(--primary-text-color); }
  .inline { display: flex; gap: 6px; }
  .inline input { flex: 1; }
  .foot { grid-column: 1 / -1; display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap; }
  button { font: inherit; font-size: 14px; padding: 8px 14px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); }
  button.primary { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: transparent; }
  button.danger { color: var(--error-color, #db4437); border-color: var(--error-color, #db4437); padding: 4px 10px; }
  button:disabled { opacity: 0.45; cursor: default; }
  .created { border: 2px solid var(--success-color, #43a047); border-radius: 12px; padding: 12px; margin-bottom: 12px; }
  .row { display: flex; justify-content: space-between; gap: 12px; padding: 3px 0; }
  .row span:first-child { color: var(--secondary-text-color); }
  .pw { font-size: 22px; font-weight: 700; letter-spacing: 1px; }
  .actions { display: flex; gap: 8px; margin-top: 8px; }
  .access { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; padding: 8px 0; border-top: 1px solid var(--divider-color); }
  .access .name { font-weight: 600; }
  .access button { grid-row: 1 / span 2; grid-column: 2; align-self: center; }
  .error { color: var(--error-color, #db4437); font-size: 13px; }
`;

class IliadboxGuestCard extends HTMLElement {
  static getStubConfig() {
    return { title: "Guest Wi-Fi" };
  }

  setConfig(config) {
    this._config = { title: "Guest Wi-Fi", ...config };
    if (this._built) this.shadowRoot.querySelector(".title").textContent = this._config.title;
  }

  getCardSize() {
    return 7;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._build();
      this._start();
    }
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

  get _isAdmin() {
    return !!this._hass.user?.is_admin;
  }

  _build() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="head"><span class="title"></span><span class="muted mono" id="ssid"></span></div>
        <form novalidate ${this._isAdmin ? "" : "hidden"}>
          <label class="wide">Description
            <input name="description" maxlength="64" placeholder="e.g. Weekend guests" required>
          </label>
          <label class="wide">Password
            <span class="inline">
              <input name="password" class="mono" minlength="8" maxlength="63" required>
              <button type="button" id="gen">Generate</button>
            </span>
          </label>
          <label>Duration (hours)
            <input name="duration_hours" type="number" min="1" max="${MAX_HOURS}" step="1" value="24" required>
          </label>
          <label>Max devices (0 = unlimited)
            <input name="max_devices" type="number" min="0" step="1" value="0" required>
          </label>
          <label class="wide">Access type
            <select name="access_type" required>
              <option value="net_only" selected>Internet only</option>
              <option value="full">Full network (internet and home devices)</option>
            </select>
          </label>
          <div class="foot">
            <span class="muted" id="hint"></span>
            <button type="submit" class="primary" id="create" disabled>Create</button>
          </div>
        </form>
        <div id="result"></div>
        <div id="error" class="error"></div>
        <div id="list"></div>
      </ha-card>`;
    this.shadowRoot.querySelector(".title").textContent = this._config.title;

    const form = this.shadowRoot.querySelector("form");
    form.elements.password.value = generatePassword();
    form.addEventListener("input", () => this._validate());
    this.shadowRoot.getElementById("gen").addEventListener("click", () => {
      form.elements.password.value = generatePassword();
      this._validate();
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      this._create();
    });
    this.shadowRoot.getElementById("list").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-id]");
      if (btn) this._revoke(Number(btn.dataset.id), btn.dataset.name);
    });
    this._built = true;
    this._validate();
  }

  _box() {
    const boxes = this._boxes || [];
    return this._config.entry_id ? boxes.find((b) => b.entry_id === this._config.entry_id) : boxes[0];
  }

  async _refresh() {
    try {
      this._boxes = await this._hass.callWS({ type: "iliadbox/data" });
      this._setError("");
    } catch (err) {
      this._setError(`Cannot read the box: ${err.message || err}`);
    }
    this._render();
    this._validate();
  }

  _setError(text) {
    this.shadowRoot.getElementById("error").textContent = text;
  }

  _values() {
    const f = this.shadowRoot.querySelector("form").elements;
    return {
      description: f.description.value.trim(),
      password: f.password.value,
      duration_hours: f.duration_hours.value === "" ? NaN : Number(f.duration_hours.value),
      max_devices: f.max_devices.value === "" ? NaN : Number(f.max_devices.value),
      access_type: f.access_type.value,
    };
  }

  // Same rules as guest.validate() on the server
  _validate() {
    const v = this._values();
    let problem = "";
    if (!v.description) problem = "Enter a description.";
    else if (v.password.length < 8 || v.password.length > 63 || !/^[\x20-\x7e]+$/.test(v.password))
      problem = "Password: 8-63 characters, no accents.";
    else if (!Number.isInteger(v.duration_hours) || v.duration_hours < 1 || v.duration_hours > MAX_HOURS)
      problem = `Duration: whole hours, 1-${MAX_HOURS}.`;
    else if (!Number.isInteger(v.max_devices) || v.max_devices < 0)
      problem = "Max devices: 0 (unlimited) or more.";
    else if (!["net_only", "full"].includes(v.access_type)) problem = "Choose an access type.";
    else if (!this._box()) problem = "No Iliadbox available.";
    this.shadowRoot.getElementById("hint").textContent = problem;
    this.shadowRoot.getElementById("create").disabled = !!problem || this._busy;
    return !problem;
  }

  async _create() {
    if (!this._validate()) return;
    this._busy = true;
    this._validate();
    try {
      const res = await this._hass.callWS({
        type: "iliadbox/create_guest",
        entry_id: this._box().entry_id,
        ...this._values(),
      });
      this._showCreated(res);
      const f = this.shadowRoot.querySelector("form").elements;
      f.description.value = "";
      f.password.value = generatePassword();
    } catch (err) {
      this._setError(`Cannot create guest Wi-Fi: ${err.message || err}`);
    }
    this._busy = false;
    this._refresh();
  }

  _showCreated(res) {
    const el = this.shadowRoot.getElementById("result");
    el.innerHTML = `
      <div class="created">
        <div class="muted">"${esc(res.description)}" created</div>
        <div class="row"><span>Network</span><span class="mono">${esc(res.ssid || "—")}</span></div>
        <div class="row"><span>Password</span><span class="mono pw">${esc(res.password)}</span></div>
        <div class="row"><span>Access</span><span>${accessLabel(res.access_type)} · ${
          res.max_devices ? `${esc(res.max_devices)} devices` : "unlimited devices"
        }</span></div>
        <div class="row"><span>Expires</span><span>${esc(new Date(res.expires).toLocaleString())}</span></div>
        <div class="actions"><button type="button" id="copy">Copy password</button>
          <button type="button" id="close">Close</button></div>
      </div>`;
    el.querySelector("#copy").onclick = () => navigator.clipboard?.writeText(res.password);
    el.querySelector("#close").onclick = () => (el.innerHTML = "");
  }

  async _revoke(id, name) {
    if (!confirm(`Revoke guest access "${name}"? Devices using it will be disconnected.`)) return;
    try {
      await this._hass.callWS({ type: "iliadbox/delete_guest", entry_id: this._box().entry_id, access_id: id });
    } catch (err) {
      this._setError(`Cannot revoke: ${err.message || err}`);
    }
    this._refresh();
  }

  _render() {
    const box = this._box();
    this.shadowRoot.getElementById("ssid").textContent = box?.guest?.ssid || "";
    const keys = box?.guest?.keys || [];
    this.shadowRoot.getElementById("list").innerHTML = keys.length
      ? keys
          .map((k) => {
            const p = k.params;
            return `<div class="access">
              <span class="name">${esc(p.description)}${p.key ? ` · <span class="mono">${esc(p.key)}</span>` : ""}</span>
              ${
                this._isAdmin
                  ? `<button class="danger" data-id="${esc(k.id)}" data-name="${esc(p.description)}">Revoke</button>`
                  : ""
              }
              <span class="muted">${accessLabel(p.access_type)} · ${
                p.max_use_count ? `${esc(p.max_use_count)} devices` : "unlimited"
              } · expires in ${fmtRemaining(k.remaining)}</span>
            </div>`;
          })
          .join("")
      : `<div class="muted">No active guest access.</div>`;
  }
}

if (!customElements.get("iliadbox-guest-card")) {
  customElements.define("iliadbox-guest-card", IliadboxGuestCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "iliadbox-guest-card",
    name: "Iliadbox guest Wi-Fi",
    description: "Create, show and revoke guest Wi-Fi accesses on the Iliadbox.",
  });
}
