# Public submission assessment

Assessment date: 2026-10-21. **Status: blocked; not ready to submit.** No OpenAI review or publication has occurred.

## Product eligibility

1. The current product's main integration uses an unofficial WhatsApp linked-device bridge. OpenAI's [plugin guidelines](https://developers.openai.com/plugins/plugin-guidelines#third-party-content-and-integrations) state that unofficial connectors cannot be approved. Moving it to a public server would not resolve this.
2. The packaged MCP server runs locally over stdio. [Desktop-only submission](https://developers.openai.com/plugins/deploy/desktop-only) requires approved-partner access and organization allowlisting. Eligibility is unverified.
3. The existing display name and logo are WhatsApp branding. Publisher rights or an independent public identity must be resolved. A suggested independent name is GroupBrief, subject to the publisher's choice.

The publisher has chosen to preserve live-chat features and add hosted access across devices. The hosted pilot is implemented in `cloud/`, with remote OAuth MCP and isolated accounts, but it still uses the unofficial bridge. No chat-export product has been substituted. Authorized integration access is still required for public-directory eligibility.

## Materials prepared

- Working source, five MCP tools, explicit tool annotations and consent controls.
- Windows 2.2.0 package and checksum for direct public distribution and personal local installation.
- Hosted 3.0.0-beta.1 source, deployment generator, per-account sign-in/consent and remote read-only MCP. Not deployed or verified in native ChatGPT clients.
- Current setup/build instructions and technical data-practices inventory.
- Five positive and three negative draft review cases in `review-cases.json`.
- `plugin.draft.json` is a metadata preparation copy, not a complete upload bundle. The private source manifest is preserved.
- Automated engine/protocol tests and isolated frozen-runtime verification exist. They do not establish public-directory approval or host-level review-case results.

## Confirmed publisher details

Publisher: Mahdhi Muzammil. Intended countries: all available countries, represented by an empty restriction list. The plugin is free with no plugin commerce. Provider: register.lk, shared hosting/cPanel. The publisher requires the existing live-chat features and access across devices. The subdomain has been created; a production backend has not been deployed.

## Remaining decisions and evidence

- Product direction and authorized access model; local submission eligibility if retaining stdio.
- Confirm the selected OpenAI organization identity is verified as Mahdhi Muzammil; the intended name has been supplied, but dashboard verification has not been inspected.
- Independent public branding or permission for the third-party branding.
- Website and support URLs are verified public GitHub pages and saved in the draft metadata. Published publisher-approved privacy-policy and terms URLs remain missing; technical policy notes are not substitutes.
- A real demo recording in the intended ChatGPT host, hosted where reviewers can view it. The walkthrough is prepared below, but no video is claimed complete.
- Dedicated reviewer access with sample data; submit any credentials through secure portal fields only.
- Organization/domain verification, imported metadata, scans and authorized developer attestations.

## Hosting

The selected hostname is `wa.robotuae.com`; the publisher created the subdomain in cPanel and requires using only that existing hosting. The hosted gateway has OAuth, per-user storage, consent and token revocation. The desktop dashboard remains loopback-only. A direct cPanel Passenger launcher uses private Unix sockets and sandboxed Chrome; a container deployment is also retained. Node 24, Python 3.12 and a sandboxed Chrome launch were verified on the actual shared host. Full application deployment, HTTPS and idle/restart persistence remain unverified. No production service or DNS change has been made. Account erasure is operator-managed; there is no public self-signup. See `docs/CPANEL.md`, `docs/HOSTED.md` and `cloud/VERIFICATION.md`.

## Demo walkthrough to record after eligibility and development setup are resolved

Use a dedicated sample account. Show the actual version in ChatGPT, pairing/setup without exposing QR/session credentials, a recent private request, a group commitment, pagination, and message-sharing revocation. Run the prompts in `review-cases.json`, showing real tool results and clear limitations. Keep unrelated chats, tokens and account details off screen. Computer/browser control can help rehearse the flow; video capture must be available or started by the publisher. Verify the saved recording and its public/reviewer access before adding its URL.

## Next step

Preserve the requested live-chat features and resolve authorized integration access and local submission eligibility first. Then complete publisher/listing facts and reviewer materials, rebuild and inspect the exact bundle, and only then upload a draft if authorized. Upload, submission for review and publication are distinct states. See [OpenAI submission documentation](https://developers.openai.com/plugins/deploy/submission).
