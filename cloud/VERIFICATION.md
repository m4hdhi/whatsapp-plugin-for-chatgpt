# Hosted pilot verification

Date: 2026-10-21. Version: 3.0.0-beta.1. All account/message inputs used in automated tests were synthetic. No real user chat data or credentials were published.

## Executed

- Full Python suite: 105 passed, including nine new hosted tests exercising authentication, cross-account isolation, signed webhooks, chat exclusion/revocation, OAuth PKCE/code replay, refresh rotation/reuse, grant revocation, malformed protocol input and deployment boundaries. One existing Starlette/AnyIO deprecation warning.
- Node bridge tests include a regression for explicit container host validation, authentication and origin rejection. Desktop default remains loopback-only. Existing WAHA metadata checks also run; their optional installed-artifact check is skipped in a clean source checkout.
- Both Linux images built successfully. A temporary, isolated Compose project started the gateway and Chromium bridge with non-root users, dropped capabilities and separate volumes. Browser account sign-in/API access succeeded, and the real WhatsApp worker generated a pairing QR. It was not scanned, saved to the repository or exposed publicly. The test project and its synthetic volumes were removed.
- Automated Chromium UI testing against a local HTTPS test server: browser login, cookie/CSRF settings save, keyless sharing persistence, background analysis off, hidden Windows-only controls, grant revocation and logout. Widths 1440, 390 and 360 pixels; no horizontal overflow or JavaScript errors. Mobile screenshot visually inspected. This test used a test-only self-signed certificate; no production certificate validation was disabled.
- Browser testing found and fixed `Referrer-Policy: no-referrer` causing native form POSTs to use `Origin: null`. The hosted gateway now uses `same-origin`; cross-origin requests remain rejected.
- Container testing found and fixed the bridge rejecting its private container Host header. The hosted worker now allows exactly its configured service hostname; the desktop bridge's default Host restriction remains unchanged.

## Unresolved dependency audit

`npm audit --omit=dev` on the pinned bridge dependency graph reported nine high-severity package entries, including inherited entries through Puppeteer/whatsapp-web.js. Root advisories include `basic-ftp` directory-listing denial of service and `extract-zip` symlink traversal/arbitrary writes. The nine entries are not nine independently reachable application exploits. Audit suggested an older whatsapp-web.js version; it was not applied blindly.

This build uses distribution Chromium with Puppeteer's download disabled, does not accept user-supplied browser archives or FTP/proxy addresses, and does not expose browser administration as a tool. These constraints reduce the relevant surface but do not constitute a completed exploitability review. Resolve or formally assess the remaining dependencies before broad public operation. No clean dependency-audit claim is made.

## Not yet established

- Deployment at `wa.robotuae.com`, public TLS issuance, real DNS routing and production host capacity.
- End-to-end OAuth/tool invocation inside ChatGPT, including actual Windows/macOS/iOS/Android clients and plan/workspace eligibility.
- Real-account pairing, reconnect behavior after host restart, long-term collection completeness and load/concurrency testing.
- Independent security review, adopted hosted privacy/terms/deletion policy, MFA/self-service account recovery, large-scale operation or an uptime commitment.
- OpenAI directory approval or authorization from WhatsApp/Meta. The unofficial-connector guideline remains a blocking eligibility issue.

Browser responsiveness and a generated QR do not prove every native ChatGPT client supports this plugin. This is a hosted beta for controlled testing, not an already deployed service for everyone.
