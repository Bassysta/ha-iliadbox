# Development and validation

The integration is tested with synthetic router responses; no test requires a router or real credentials. Tests import the production modules and use Home Assistant's actual registries, config flows, platforms, authorization and WebSocket machinery.

## Run tests

Minimum supported version, Home Assistant 2024.12.5 / Python 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q --cov=custom_components.iliadbox
.venv/bin/ruff check custom_components tests
.venv/bin/ruff format --check custom_components tests
```

The second full-test matrix uses Python 3.14 and `requirements-test-recent.txt`, which pins the available external test harness and its matching HA 2026.10.4 dependency. The HA 2026.11.2 CI job is an import compatibility check only: the external harness still targets 2026.10 and cannot run against 2026.11 without upstream changes. It must not be represented as a complete 2026.11 runtime validation.

Frontend behavior tests use Node 20 and jsdom:

```bash
npm ci --ignore-scripts
npm test
npx prettier --check 'custom_components/iliadbox/frontend/*.js' 'tests/frontend/*.js'
```

The shared guest component preserves input while snapshots update. A single subscription is shared by widgets on the same HA connection; it is released when the last widget disconnects. Mutating commands and read failures have separate error state. QR SVG comes exclusively from the local `segno` generator, after backend authorization; arbitrary router/user text is HTML-escaped.

## Fix checklist

| Audit finding | Implementation | Regression coverage |
| --- | --- | --- |
| A01 transient login errors treated as revoked tokens | Preserve exception types; retry authentication only after explicit expired-session responses | API error matrix and write-timeout tests |
| A02 malformed API payloads | Validate discovery and response envelopes, list/object results, auth payloads and guest identities; classify HTTP failures | Malformed JSON/envelope/discovery and HTTP status tests |
| A03 optional errors erase healthy data | Per-source cache/freshness; no guest deletion after a failed read; propagate revoked auth | Coordinator and guest entity tests |
| A04 same-band BSS overwritten | Keep individual AP/BSS data, aggregate legacy band entities, dynamically add late bands | Multi-BSS and real platform lifecycle tests |
| A05 expiry moves when reading cache | Sample-time absolute expiry | Frozen-clock regression |
| A06 credentials cross privilege boundaries | Secret-free notifications/snapshots; admin/internal-context write policy; image opt-in | Services, entity actions, actual WebSockets and image tests |
| A07 notifications collide across boxes | Entry-scoped notification IDs | Two-box create/delete test |
| A08 wrong router accepted during reauth | Compare UID before authorization | Real config flow regression |
| Compatibility and missing tests | HA minimum 2024.12.5; two pinned HA matrices, import smoke check, frontend tests and lint | CI workflow |
| Session concurrency / frequent permissions polling | Invalidate only the session used by the failed request; throttle permission checks and support read-only mode | Late-response and permission tests |
| Destructive age filtering | Keep registries/customizations; mark absent hosts unavailable and reuse entities on return | Real HA setup/filter/return/unload test |
| Frontend error loss and ambiguous box selection | Persistent command errors, explicit multi-box selection, disabled unavailable controls | DOM tests |
| English-only UI / incorrect URLs / logger conflict | Shared EN/IT strings, translated HA errors, IPv6-safe URLs, deterministic documented global log policy | Translation, host validation and IPv6 tests |

Existing band sensor IDs remain stable. When members disagree about channel, SSID or encryption, the band aggregate is unknown for that field; the panel still shows each member. Client totals sum BSS station counts; they are not a unique-client count across bands.

## New-device and history semantics

The first successful LAN sample establishes known devices, including inactive entries remembered by the router. A later unseen active MAC generates a `new_device` event once. A new inactive historical entry is silently recorded as known. Recognizing or ignoring a device persists across reloads. Ignored devices remain visible in HA and only suppress subsequent presence events. MAC randomization can create legitimate first-seen alerts.

Snapshots stored in the journal contain only selected metadata; no raw API payload, guest key, application token or session token is saved. Timeline retention is seven days / 200 events; recognized devices are retained until the config entry is removed. Entry removal deletes the journal. Clearing only the timeline retains recognition and comparison baselines. The normal delayed save is ten seconds and unload flushes pending state; an abrupt power loss can lose the most recent unsaved events or recognition changes.

WAN durations are observational. Router availability means successful core API polling, not independent Internet probing. Events shorter than the polling interval can be missed. Guest accesses are removed from entity registries only after a successful authoritative list omits them.

## Hardware acceptance before release

Test against a real Iliadbox: initial authorization, reauthorization, expired session, revoked token, temporarily unavailable optional endpoints, restored connectivity, permissions changed in the router UI, and reload/restart. Verify AP/BSS station-count semantics on the firmware in use. Check creation/revocation with a phone joining via QR, including both the admin-only and explicit shared-image paths. Capture only redacted fixtures.

Browser checks should include mobile width, keyboard navigation, reconnecting HA, multiple cards, and two boxes. The automated DOM tests do not replace these visual and hardware checks.
