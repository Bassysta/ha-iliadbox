import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>", {
  url: "http://localhost/",
});
for (const key of [
  "window",
  "document",
  "HTMLElement",
  "customElements",
  "CustomEvent",
  "FormData",
])
  globalThis[key] = dom.window[key];
globalThis.confirm = () => true;
const { GuestManager, selectBox, subscribe, t, esc, generatePassword } =
  await import("../../custom_components/iliadbox/frontend/shared.js?v=0.11.0");
const { IliadboxGuestCard } = await import(
  "../../custom_components/iliadbox/frontend/iliadbox-guest-card.js"
);
const { IliadboxPanel } = await import(
  "../../custom_components/iliadbox/frontend/iliadbox-panel.js"
);
const hass = () => ({
  language: "en",
  user: { is_admin: true },
  connection: { subscribeMessage: async () => () => {} },
  callWS: async () => ({}),
});
const box = () => ({
  entry_id: "box-1",
  title: "Test box",
  loaded: true,
  available: true,
  can_modify: true,
  read_only: false,
  freshness: { guest: true, radios: true },
  guest: { default_name: "test-guest", ssid: "test", keys: [] },
  connection: { state: "up" },
  system: {},
  wifi: { enabled: true },
  hosts: [],
  devices: {},
  events: [],
  radios: [],
});

test("multiple boxes require an explicit selection, even when one is offline", () => {
  const boxes = [box(), { ...box(), entry_id: "box-2", loaded: false }];
  assert.equal(selectBox(boxes, undefined), undefined);
  assert.equal(selectBox(boxes, "box-2").loaded, false);
});

test("subscription shared across widgets and removed with final subscriber", async () => {
  let callbacks,
    subscriptions = 0,
    removed = 0;
  const h = hass();
  h.connection.subscribeMessage = async (fn) => {
    subscriptions++;
    callbacks = fn;
    return () => removed++;
  };
  const a = [],
    b = [];
  const removeA = subscribe(h, (value) => a.push(value), assert.fail);
  const removeB = subscribe(h, (value) => b.push(value), assert.fail);
  await Promise.resolve();
  callbacks([box()]);
  assert.equal(subscriptions, 1);
  assert.equal(a.length, 1);
  assert.equal(b.length, 1);
  removeA();
  assert.equal(removed, 0);
  removeB();
  assert.equal(removed, 1);
});

test("pending subscription cleanup does not leak a listener", async () => {
  let resolve,
    removed = 0;
  const h = hass();
  h.connection.subscribeMessage = () => new Promise((r) => (resolve = r));
  const stop = subscribe(h, () => {}, assert.fail);
  stop();
  resolve(() => removed++);
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(removed, 1);
});

test("action failure stays visible when fresh data arrives", async () => {
  const manager = new GuestManager(),
    h = hass(),
    b = box();
  manager.data = { hass: h, box: b };
  h.callWS = async () => {
    throw new Error("permission denied");
  };
  await manager._create();
  assert.match(
    manager.shadowRoot.getElementById("error").textContent,
    /permission denied/,
  );
  manager.data = { hass: h, box: { ...b } };
  assert.match(
    manager.shadowRoot.getElementById("error").textContent,
    /permission denied/,
  );
});

test("guest creation result survives until a later snapshot", async () => {
  const manager = new GuestManager(),
    h = hass(),
    b = box();
  manager.data = { hass: h, box: b };
  h.callWS = async () => ({
    id: 2,
    ssid: "test",
    password: "SYNTHETIC",
    qr_svg: "<svg></svg>",
  });
  await manager._create();
  assert.match(
    manager.shadowRoot.getElementById("result").textContent,
    /SYNTHETIC/,
  );
  manager.data = { hass: h, box: { ...b } };
  assert.equal(manager.shadowRoot.getElementById("result").textContent, "");
});

test("read-only and offline states disable writes", () => {
  const manager = new GuestManager(),
    h = hass(),
    b = box();
  for (const changes of [
    { available: false },
    { loaded: false },
    { read_only: true, can_modify: false },
  ]) {
    manager.data = { hass: h, box: { ...b, ...changes } };
    assert.equal(manager.shadowRoot.getElementById("create").disabled, true);
  }
});

test("non-admin does not receive controls and malicious names are escaped", () => {
  const manager = new GuestManager(),
    h = hass(),
    b = box();
  h.user.is_admin = false;
  b.guest.keys = [
    {
      id: 1,
      params: {
        description: '<img src=x onerror="alert(1)">',
        access_type: "net_only",
      },
    },
  ];
  manager.data = { hass: h, box: b };
  assert.equal(manager.shadowRoot.querySelector("form").hidden, true);
  assert.equal(manager.shadowRoot.querySelector("img"), null);
  assert.equal(manager.shadowRoot.querySelector("button[data-action]"), null);
});

test("Italian guest form and event names", () => {
  const manager = new GuestManager(),
    h = hass();
  h.language = "it";
  manager.data = { hass: h, box: box() };
  assert.match(manager.shadowRoot.textContent, /Durata \(ore\)/);
  assert.equal(t(h, "wan_changed"), "Stato WAN cambiato");
});

test("card honors configured box and preserves current selection", () => {
  const card = new IliadboxGuestCard(),
    h = hass();
  card.setConfig({ entry_id: "box-2" });
  card.hass = h;
  card._boxes = [box(), { ...box(), entry_id: "box-2" }];
  card._render();
  assert.equal(
    card.shadowRoot.querySelector("iliadbox-guest-manager")._box.entry_id,
    "box-2",
  );
});

test("panel escapes timeline and device data, shows new-device review", () => {
  const panel = new IliadboxPanel(),
    h = hass(),
    b = box();
  panel.hass = h;
  b.devices = {
    "aa:bb:cc:dd:ee:01": {
      name: "<script>bad()</script>",
      status: "new",
      vendor: "Test",
    },
  };
  b.events = [{ type: "new_device", name: "<img src=x>", timestamp: 1 }];
  panel._boxes = [b];
  panel._select(b.entry_id);
  assert.equal(panel.shadowRoot.querySelector("script"), null);
  assert.equal(panel.shadowRoot.querySelector("img"), null);
  assert.equal(panel.shadowRoot.querySelectorAll("button[data-mac]").length, 2);
});

test("generated passwords meet validation and escaping preserves content", () => {
  for (let i = 0; i < 50; i++)
    assert.match(generatePassword(), /^[A-Za-z2-9]{12}$/);
  assert.equal(esc('<&"'), "&lt;&amp;&quot;");
});

test("changing boxes while creation is pending cannot show the previous password", async () => {
  const manager = new GuestManager(),
    h = hass(),
    b = box();
  let resolve;
  h.callWS = () =>
    new Promise((done) => {
      resolve = done;
    });
  manager.data = { hass: h, box: b };
  const pending = manager._create();
  manager.data = { hass: h, box: { ...b, entry_id: "box-2" } };
  resolve({ id: 2, ssid: "old-box", password: "OLD-BOX-SECRET" });
  await pending;
  assert.doesNotMatch(manager.shadowRoot.textContent, /OLD-BOX-SECRET/);
});
