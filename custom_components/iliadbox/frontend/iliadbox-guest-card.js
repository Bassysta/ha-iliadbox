import { STYLE, esc, t, selectBox, subscribe } from "./shared.js?v=0.11.0";

export class IliadboxGuestCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._boxes = [];
    this._config = {};
  }
  static getStubConfig() {
    return {};
  }
  getCardSize() {
    return 7;
  }
  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }
  setConfig(config) {
    this._config = config;
    this._selected = config.entry_id;
    if (this._hass) this._render();
  }
  set hass(hass) {
    const changed = this._hass?.connection !== hass.connection;
    const languageChanged = this._hass?.language !== hass.language;
    this._hass = hass;
    if (changed) {
      this._unsubscribe?.();
      this._unsubscribe = null;
    }
    if (this.isConnected) this._start();
    if (languageChanged || !this._built) this._render();
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
  _render() {
    const tr = (key) => esc(t(this._hass, key));
    if (!this._built) {
      this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><h2 id="title"></h2><div id="selection"></div><div id="error" role="alert" class="error"></div><button id="retry" hidden>${tr("Retry")}</button><iliadbox-guest-manager no-heading></iliadbox-guest-manager></ha-card>`;
      this.shadowRoot.getElementById("retry").onclick = () => {
        this._unsubscribe?.();
        this._unsubscribe = null;
        this._start();
      };
      this._built = true;
    }
    this.shadowRoot.getElementById("title").textContent =
      this._config.title || t(this._hass, "Guest Wi-Fi");
    const selector = this.shadowRoot.getElementById("selection");
    selector.innerHTML =
      !this._config.entry_id && this._boxes.length > 1
        ? `<label>${tr("Box")}<select><option value="">${tr("Choose a box")}</option>${this._boxes.map((box) => `<option value="${esc(box.entry_id)}" ${this._selected === box.entry_id ? "selected" : ""}>${esc(box.title)}${box.loaded ? "" : ` · ${tr("Unavailable")}`}</option>`).join("")}</select></label>`
        : "";
    if (selector.firstChild)
      selector.querySelector("select").onchange = (event) => {
        this._selected = event.target.value;
        this._render();
      };
    const box = selectBox(this._boxes, this._selected);
    this.shadowRoot.getElementById("error").textContent = this._readError
      ? `${t(this._hass, "Cannot read data")}: ${this._readError}`
      : "";
    this.shadowRoot.getElementById("retry").hidden = !this._readError;
    const manager = this.shadowRoot.querySelector("iliadbox-guest-manager");
    manager.hidden = !box;
    manager.data = { hass: this._hass, box };
  }
}
if (!customElements.get("iliadbox-guest-card")) {
  customElements.define("iliadbox-guest-card", IliadboxGuestCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "iliadbox-guest-card",
    name: "Iliadbox guest Wi-Fi",
    description: "Guest access management",
  });
}
