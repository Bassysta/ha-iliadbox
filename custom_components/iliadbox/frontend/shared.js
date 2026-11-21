// Shared UI, translations and one backend subscription per HA connection.
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const IT = {
  "Guest Wi-Fi": "Wi-Fi ospiti",
  Box: "Box",
  "Choose a box": "Scegli una box",
  "No box configured": "Nessuna box configurata",
  Unavailable: "Non disponibile",
  "Stale data": "Dati non aggiornati",
  "Read only": "Sola lettura",
  "Missing settings permission": "Permesso di modifica impostazioni mancante",
  Description: "Descrizione",
  Password: "Password",
  Generate: "Genera",
  "Duration (hours)": "Durata (ore)",
  "Max devices (0 = unlimited)": "Dispositivi massimi (0 = illimitati)",
  Access: "Accesso",
  "Internet only": "Solo Internet",
  "Full network": "Rete completa",
  Create: "Crea",
  Network: "Rete",
  Expires: "Scadenza",
  "Show password and QR": "Mostra password e QR",
  Revoke: "Revoca",
  "Revoke this access?": "Revocare questo accesso?",
  "No guest accesses": "Nessun accesso ospite",
  Close: "Chiudi",
  "Copy password": "Copia password",
  Copied: "Copiata",
  "Scan to join the network": "Scansiona per connetterti alla rete",
  Connection: "Connessione",
  Bandwidth: "Banda",
  Traffic: "Traffico",
  "Power saving": "Risparmio energetico",
  "MAC filter": "Filtro MAC",
  Yes: "Sì",
  No: "No",
  Download: "Download",
  Upload: "Upload",
  "Public IP": "IP pubblico",
  Firmware: "Firmware",
  Uptime: "Tempo di attività",
  Devices: "Dispositivi",
  "Search devices": "Cerca dispositivi",
  "Online only": "Solo connessi",
  Name: "Nome",
  Vendor: "Produttore",
  Status: "Stato",
  "Last activity": "Ultima attività",
  Connected: "Connesso",
  Disconnected: "Disconnesso",
  Known: "Conosciuto",
  Ignored: "Ignorato",
  New: "Nuovo",
  Recognize: "Riconosci",
  Ignore: "Ignora",
  "New devices": "Nuovi dispositivi",
  "No new devices": "Nessun nuovo dispositivo",
  "Network events": "Eventi di rete",
  "No events yet": "Ancora nessun evento",
  "Clear history": "Cancella cronologia",
  "Clear the timeline? Device recognition will be kept.":
    "Cancellare la cronologia? I dispositivi riconosciuti saranno conservati.",
  "Last 200 events, up to 7 days": "Ultimi 200 eventi, fino a 7 giorni",
  "All boxes": "Tutte le box",
  "Open router settings": "Apri impostazioni router",
  Reboot: "Riavvia",
  "Reboot the router?": "Riavviare il router?",
  "Turn Wi-Fi off": "Spegni Wi-Fi",
  "Turn Wi-Fi on": "Accendi Wi-Fi",
  "Turn off Wi-Fi? Wireless devices will disconnect.":
    "Spegnere il Wi-Fi? I dispositivi wireless si disconnetteranno.",
  Channel: "Canale",
  Clients: "Client",
  Unknown: "Sconosciuto",
  "Operation failed": "Operazione non riuscita",
  "Cannot read data": "Impossibile leggere i dati",
  Retry: "Riprova",
  new_device: "Nuovo dispositivo",
  device_connected: "Dispositivo connesso",
  device_disconnected: "Dispositivo disconnesso",
  wan_changed: "Stato WAN cambiato",
  public_ip_changed: "IP pubblico cambiato",
  wifi_changed: "Stato Wi-Fi cambiato",
  router_restarted: "Router riavviato",
  router_available: "Router raggiungibile",
  router_unavailable: "Router irraggiungibile",
  guest_created: "Accesso ospite creato",
  guest_removed: "Accesso ospite rimosso",
};
const EN_EVENTS = {
  new_device: "New device",
  device_connected: "Device connected",
  device_disconnected: "Device disconnected",
  wan_changed: "WAN state changed",
  public_ip_changed: "Public IP changed",
  wifi_changed: "Wi-Fi state changed",
  router_restarted: "Router restarted",
  router_available: "Router reachable",
  router_unavailable: "Router unreachable",
  guest_created: "Guest access created",
  guest_removed: "Guest access removed",
};
export const t = (hass, key) =>
  (hass?.language || "en").startsWith("it")
    ? IT[key] || key
    : EN_EVENTS[key] || key;
export const date = (hass, seconds) =>
  seconds == null
    ? "—"
    : new Date(seconds * 1000).toLocaleString(hass?.language || "en");
export const rate = (value) =>
  value == null ? "—" : `${((value * 8) / 1e6).toFixed(2)} Mbit/s`;
export const bytes = (value) =>
  value == null ? "—" : `${(value / 1e9).toFixed(2)} GB`;
export const duration = (seconds) =>
  seconds == null
    ? "—"
    : `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
export const ipv4 = (host) =>
  (host.l3connectivities || []).find(
    (item) => item.af === "ipv4" && item.active,
  )?.addr || "";
export function generatePassword() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
  let result = "";
  while (result.length < 12) {
    for (const n of crypto.getRandomValues(new Uint8Array(24))) {
      if (n < 256 - (256 % alphabet.length))
        result += alphabet[n % alphabet.length];
      if (result.length === 12) break;
    }
  }
  return result;
}
export function selectBox(boxes, entryId) {
  return entryId
    ? boxes.find((box) => box.entry_id === entryId)
    : boxes.length === 1
      ? boxes[0]
      : undefined;
}
const feeds = new WeakMap();
export function subscribe(hass, listener, onError) {
  const connection = hass.connection;
  let feed = feeds.get(connection);
  if (!feed) {
    feed = { listeners: new Map(), data: undefined };
    feeds.set(connection, feed);
    feed.ready = connection
      .subscribeMessage(
        (data) => {
          feed.data = data;
          for (const fn of feed.listeners.keys()) fn(data);
        },
        { type: "iliadbox/subscribe" },
      )
      .then((unsubscribe) => {
        feed.unsubscribe = unsubscribe;
        if (!feed.listeners.size) unsubscribe();
      })
      .catch((error) => {
        feeds.delete(connection);
        for (const report of feed.listeners.values()) report(error);
      });
  }
  feed.listeners.set(listener, onError);
  if (feed.data) listener(feed.data);
  return () => {
    feed.listeners.delete(listener);
    if (!feed.listeners.size) {
      if (feeds.get(connection) === feed) feeds.delete(connection);
      feed.unsubscribe?.();
    }
  };
}
export const STYLE = `
  :host { display:block; color:var(--primary-text-color); font-family:var(--paper-font-body1_-_font-family, sans-serif); }
  * { box-sizing:border-box; } [hidden] { display:none !important; }
  .card, ha-card { padding:16px; border-radius:var(--ha-card-border-radius,12px); background:var(--ha-card-background,var(--card-background-color,#fff)); border:1px solid var(--divider-color,#ddd); margin-bottom:16px; }
  h2 { font-size:18px; margin:0 0 12px; } h3 { font-size:16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; }
  .row, .actions { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin:8px 0; } .row { justify-content:space-between; }
  .muted { color:var(--secondary-text-color); font-size:13px; } .mono { font-family:ui-monospace,monospace; overflow-wrap:anywhere; }
  button, input, select { font:inherit; color:inherit; padding:9px; border:1px solid var(--divider-color,#aaa); border-radius:7px; background:var(--card-background-color,#fff); max-width:100%; }
  button { cursor:pointer; } button:disabled { opacity:.5; cursor:default; } button:focus-visible, input:focus-visible, select:focus-visible { outline:2px solid var(--primary-color); outline-offset:2px; }
  .primary { background:var(--primary-color); color:var(--text-primary-color,#fff); } .danger, .error { color:var(--error-color,#c33); }
  .error { white-space:pre-wrap; margin:10px 0; } .warning { padding:10px; border:1px solid var(--warning-color,#c80); border-radius:8px; margin-bottom:10px; }
  form { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; } label { display:flex; flex-direction:column; gap:5px; } .wide { grid-column:1/-1; }
  .scroll { overflow-x:auto; } table { width:100%; border-collapse:collapse; } td,th { padding:10px 8px; text-align:left; border-bottom:1px solid var(--divider-color,#ddd); }
  .qr { max-width:220px; background:white; padding:10px; } .qr svg { width:100%; height:auto; }
  .result { border:1px solid var(--success-color,#393); padding:12px; margin:12px 0; border-radius:8px; }
  a { color:var(--primary-color); } ul { padding-left:20px; } li { margin:10px 0; }
`;

export class GuestManager extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
  }
  set data({ hass, box }) {
    const rebuild =
      !this._built ||
      this._box?.entry_id !== box?.entry_id ||
      this._hass?.language !== hass.language ||
      this._hass?.user?.is_admin !== hass.user?.is_admin;
    this._hass = hass;
    this._box = box;
    if (rebuild) this._build();
    this._render();
  }
  _build() {
    this._shownId = null;
    this._shownSnapshot = null;
    const tr = (key) => esc(t(this._hass, key));
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><h2 ${this.hasAttribute("no-heading") ? "hidden" : ""}>${tr("Guest Wi-Fi")}</h2><div id="warning"></div>
      <form ${this._hass.user?.is_admin ? "" : "hidden"}>
      <label>${tr("Description")}<input name="description" maxlength="64" required></label>
      <label>${tr("Password")}<span class="actions"><input name="password" minlength="8" maxlength="63" pattern="[ -~]{8,63}" required><button id="generate" type="button">${tr("Generate")}</button></span></label>
      <label>${tr("Duration (hours)")}<input name="duration_hours" type="number" min="1" max="8760" step="1" value="24" required></label>
      <label>${tr("Max devices (0 = unlimited)")}<input name="max_devices" type="number" min="0" step="1" value="0" required></label>
      <label>${tr("Access")}<select name="access_type"><option value="net_only">${tr("Internet only")}</option><option value="full">${tr("Full network")}</option></select></label>
      <div class="actions"><button class="primary" id="create" type="submit">${tr("Create")}</button></div></form>
      <div id="error" class="error" role="alert"></div><div id="result"></div><div id="list"></div>`;
    const form = this.shadowRoot.querySelector("form");
    form.elements.description.value = this._box?.guest?.default_name || "guest";
    form.elements.password.value = generatePassword();
    this.shadowRoot.getElementById("generate").onclick = () => {
      form.elements.password.value = generatePassword();
    };
    form.onsubmit = (event) => {
      event.preventDefault();
      this._create();
    };
    this.shadowRoot.getElementById("list").onclick = (event) => {
      const button = event.target.closest("button[data-action]");
      if (button)
        this._access(button.dataset.action, Number(button.dataset.id));
    };
    this._built = true;
  }
  _canWrite() {
    return !!(
      this._hass.user?.is_admin &&
      this._box?.loaded &&
      this._box.available &&
      this._box.can_modify &&
      this._box.freshness?.guest
    );
  }
  _render() {
    const box = this._box,
      tr = (key) => esc(t(this._hass, key));
    const warning =
      !box?.loaded || !box.available
        ? "Unavailable"
        : box.read_only
          ? "Read only"
          : !box.can_modify
            ? "Missing settings permission"
            : !box.freshness?.guest
              ? "Stale data"
              : "";
    this.shadowRoot.getElementById("warning").textContent = warning
      ? t(this._hass, warning)
      : "";
    this.shadowRoot.getElementById("create").disabled =
      this._busy || !this._canWrite();
    this.shadowRoot.getElementById("list").innerHTML =
      (box?.guest?.keys || [])
        .map(
          (
            key,
          ) => `<div class="row"><div><strong>${esc(key.params.description)}</strong><div class="muted">${tr(key.params.access_type === "full" ? "Full network" : "Internet only")} · ${tr("Expires")}: ${esc(date(this._hass, key.expires_at))}</div></div>
      ${this._hass.user?.is_admin ? `<div class="actions"><button data-action="qr" data-id="${esc(key.id)}" ${!box.available || !box.freshness?.guest || !box.freshness?.radios || this._busy ? "disabled" : ""}>${tr("Show password and QR")}</button><button class="danger" data-action="revoke" data-id="${esc(key.id)}" ${!this._canWrite() || this._busy ? "disabled" : ""}>${tr("Revoke")}</button></div>` : ""}</div>`,
        )
        .join("") || `<p class="muted">${tr("No guest accesses")}</p>`;
    // Never retain credentials for a revoked access or an unavailable box.
    if (
      this._shownId != null &&
      (box !== this._shownSnapshot || !box?.available) &&
      (!box?.available ||
        !box.freshness?.guest ||
        !(box.guest?.keys || []).some(
          (key) =>
            key.id === this._shownId &&
            (key.expires_at == null || key.expires_at > Date.now() / 1000),
        ))
    ) {
      this.shadowRoot.getElementById("result").replaceChildren();
      this._shownId = null;
    }
  }
  async _perform(operation) {
    if (this._busy) return;
    const entryId = this._box?.entry_id;
    this._busy = true;
    this.shadowRoot.getElementById("error").textContent = "";
    this._render();
    try {
      await operation();
    } catch (error) {
      if (this._box?.entry_id !== entryId) return;
      this.shadowRoot.getElementById("error").textContent =
        `${t(this._hass, "Operation failed")}: ${error.message || error}`;
    } finally {
      this._busy = false;
      this._render();
    }
  }
  async _create() {
    const form = this.shadowRoot.querySelector("form");
    if (!this._canWrite() || !form.reportValidity()) return;
    const values = Object.fromEntries(new FormData(form));
    values.duration_hours = Number(values.duration_hours);
    values.max_devices = Number(values.max_devices);
    const entryId = this._box.entry_id;
    await this._perform(async () => {
      const result = await this._hass.callWS({
        type: "iliadbox/create_guest",
        entry_id: this._box.entry_id,
        ...values,
      });
      if (this._box?.entry_id !== entryId) return;
      this._show(result, result.id);
      form.elements.password.value = generatePassword();
    });
  }
  async _access(action, id) {
    if (
      action === "revoke" &&
      (!this._canWrite() || !confirm(t(this._hass, "Revoke this access?")))
    )
      return;
    const entryId = this._box.entry_id;
    await this._perform(async () => {
      const result = await this._hass.callWS({
        type: `iliadbox/${action === "qr" ? "guest_qr" : "delete_guest"}`,
        entry_id: this._box.entry_id,
        access_id: id,
      });
      if (this._box?.entry_id !== entryId) return;
      if (action === "qr") this._show(result, id);
      else {
        this._shownId = null;
        this.shadowRoot.getElementById("result").replaceChildren();
      }
    });
  }
  _show(result, id) {
    this._shownId = id;
    this._shownSnapshot = this._box;
    const tr = (key) => esc(t(this._hass, key));
    const target = this.shadowRoot.getElementById("result");
    // SVG is generated locally by segno in the authenticated admin endpoint.
    target.innerHTML = `<div class="result"><div>${tr("Network")}: ${esc(result.ssid || "—")}</div><div>${tr("Password")}: <strong class="mono">${esc(result.password)}</strong></div>${result.qr_svg ? `<div class="qr">${result.qr_svg}</div><p>${tr("Scan to join the network")}</p>` : ""}<div class="actions"><button id="copy">${tr("Copy password")}</button><button id="close">${tr("Close")}</button></div></div>`;
    target.querySelector("#close").onclick = () => {
      target.replaceChildren();
      this._shownId = null;
    };
    target.querySelector("#copy").onclick = async () => {
      try {
        await navigator.clipboard.writeText(result.password);
        target.querySelector("#copy").textContent = t(this._hass, "Copied");
      } catch (error) {
        this.shadowRoot.getElementById("error").textContent =
          `${t(this._hass, "Operation failed")}: ${error.message}`;
      }
    };
  }
}
if (!customElements.get("iliadbox-guest-manager"))
  customElements.define("iliadbox-guest-manager", GuestManager);
