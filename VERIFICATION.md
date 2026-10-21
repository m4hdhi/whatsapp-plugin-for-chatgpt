# GroupBrief 1.1.0: verification and limits

Verified on 20 October 2026 with Windows PowerShell, Python 3.12, Docker Desktop Linux containers, and Chromium. This source package installs its runtime through Docker; it is not a signed Windows executable or a native iPhone app.

## Behavior and integration checks

The Python suite uses real SQLite and the public FastAPI application. Only external HTTP services are replaced with controlled transports. It covers authentication, signed raw-body webhooks, message ingestion, structured AI requests, persisted tasks/evidence, scheduler and notifications across restarts. It tests orchestration and validation, not model interpretation quality.

New 1.1.0 regressions cover:

- Private/all-chat scope requires explicit permission; old selected groups migrate without widening access.
- Pausing survives restart and cannot be undone by legacy group-selection payloads. Excluding/revoking scope purges stored text, summaries and pending reminders/digests.
- All mode accepts future normal chats, excludes status/broadcast/newsletter IDs and respects grant timestamps. Restoring an excluded chat requires consent and excludes the intervening history.
- Private input identifies the owner as recipient without requiring a name match. All mode sends up to five chats in one request; task evidence is checked within each chat. Missing, unknown, duplicate or cross-cited results leave the whole batch pending.
- The daily request cap persists across restarts; failed provider requests retain pending messages.
- The metadata API requests only metadataOnly=true, rejects stock message-bearing models, exposes only chat identifiers/names/types and requires dashboard authentication.
- Recovery rotates through at most ten permitted chats per pass. Brief connection failures are debounced and pending outage alerts become Recovered after WORKING returns.
- Equivalent phone/device IDs and verified LID identities share permissions. Unresolved exclusions block uncertain private capture; mapping migrations purge task-only queued reminders and delivery rechecks task/digest permissions.

The WAHA extension is verified against exact compiled-engine and controller SHA256 hashes in the pinned official image. Its Docker build runs seven Node tests plus a compiled-module syntax check. Synthetic models have forbidden message getters that throw, demonstrating that metadata projection does not inspect them. Tests also check numeric pagination, normal chat categories, unchanged stock behavior unless the explicit metadata flag is supplied, and refusal of unsupported artifacts.

Browser regressions intercept every network request, use synthetic account data and exercise actual controls. They cover fresh consent, selected/private/all scope, exclusions, pause, failed list retry, rerendered busy controls, recovery refresh without automatic permission saving, and the existing QR lifecycle. No real chat text or QR is included in previews.

## Installation checks

The earlier launcher acceptance test actually started an isolated Compose project on Windows, generated ACL-protected local credentials and chose an available dashboard port. PowerShell launchers were parsed successfully. The dashboard API requires a bearer token, rejects unexpected Host and cross-origin requests, limits request bodies and emits private no-store responses. The admin port binds to 127.0.0.1; WAHA has no published host port.

Version 1.0.1 reproduced and fixed WAHA returning HTTP 201 from /start while remaining FAILED. Failed sessions use /restart, stopped sessions use /start, and starting/connected sessions are preserved. No logout, session deletion or volume reset is used. Pairing regression coverage remains in 1.1.0.

The live installation has since been paired by the user. Update acceptance checks inspect only service health, connected status, saved-key presence, permission scope/counts and metadata counts. They do not inspect private message bodies, enable broader monitoring or issue paid AI requests. Credentials and the linked-device volume are preserved during the update.

## Rendered interface

The original screen was concepted with ImageGen before implementation. The included design-reference and overview previews use synthetic data. The 1.1.0 Chats screen adds permission controls within the same white/navy/teal interface. Desktop and phone layouts, readable labels, keyboard controls, focus states, busy/error recovery and horizontal overflow are checked in Chromium.

Browser/IAB was attempted earlier; its inventory call timed out after 33 seconds and reset. Browser verification therefore uses the installed Playwright Chromium runtime. Existing overview reference images show the earlier group-only wording; current 1.1.0 Chats previews show the expanded permission screen.

## Practical limits

- Live AI interpretation and actual iPhone push delivery were not tested for this update. Synthetic API fixtures verify that the correct content/context is supplied and returned evidence is validated; no paid AI test request was issued. Pushover acceptance is not a phone read receipt.
- The default check interval is 30 minutes and the cap is 48 attempted AI requests per local day. Selected mode processes one chat per check, up to 100 new messages. All mode processes up to five pending chats per request, up to 30 new messages per chat when batching, plus bounded context. Request count does not enforce a currency budget.
- Text and captions are supported; voice, images and attachment contents are not analyzed. Message events are primary; recovery is bounded to 100 available messages per chat, ten chats per pass. WhatsApp linked-device history is incomplete, and newly granted permission does not backfill earlier conversations.
- The Windows PC must be awake, online and running Docker. The local dashboard stays on the PC; iPhone notifications use Pushover. The optional Windows sign-in shortcut was syntax-checked, not enabled on this PC.
- Processing permission controls the companion's storage/AI/reminders. The underlying linked WhatsApp device still has account-level access and may cache other chats. Local volumes are not application-encrypted. OpenAI/Pushover processing and unofficial WhatsApp integration limits are described in the full guide.

## Fresh release execution

- Python: 81 passed, one dependency deprecation warning from Starlette's test client. Final run completed after all permission and delivery fixes.
- Chromium: eight isolated Chats regressions and six QR regressions passed. No external network requests, real credentials or chat contents were used.
- WAHA: the actual pinned-image build passed all seven extension tests and the compiled JavaScript syntax check. The delivered Compose build uses that same pinned source and patch.
- Independent review found and verified fixes for retained digest excerpts and alternate-ID permission bypasses, including reverse LID exclusions and expired-source queued reminders. No unresolved release blocker remained.

## Live update acceptance

The existing Windows installation was rebuilt and restarted successfully. `/health` reports 1.1.0 and the WhatsApp session is WORKING. Its saved OpenAI key is still configured. The previous single selected group remains selected; all/private processing was not activated by the update. Pending connection notices are zero after recovery.

The authenticated metadata-only chat list returned HTTP 200 with 132 conversations (90 groups, 42 private chats), projected to exactly id/name/type. The check recorded counts and field names only; no real names, IDs, messages or QR were copied into this package. Unauthenticated listing returned 401. Both original named data/session volumes remain attached and the private environment file is byte-for-byte unchanged.

iPhone push credentials are not configured on this installation yet. Save Pushover's User Key and application token in Settings and send the test notification to enable phone delivery. Broader monitoring still requires choosing scope and saving consent in Chats. The release ZIP is checked for integrity and excludes environment files, databases, sessions and credentials.
