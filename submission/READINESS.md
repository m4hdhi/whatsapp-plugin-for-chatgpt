# Public submission assessment

Assessment date: 2026-10-21. **Status: blocked; not ready to submit.** No OpenAI review or publication has occurred.

## Product eligibility

1. The current product's main integration uses an unofficial WhatsApp linked-device bridge. OpenAI's [plugin guidelines](https://developers.openai.com/plugins/plugin-guidelines#third-party-content-and-integrations) state that unofficial connectors cannot be approved. Moving it to a public server would not resolve this.
2. The packaged MCP server runs locally over stdio. [Desktop-only submission](https://developers.openai.com/plugins/deploy/desktop-only) requires approved-partner access and organization allowlisting. Eligibility is unverified.
3. The existing display name and logo are WhatsApp branding. Publisher rights or an independent public identity must be resolved. A suggested independent name is GroupBrief, subject to the publisher's choice.

Possible directions requiring a publisher decision: keep this private local product; build a separate chat-export analysis product; or establish an authorized official integration whose documented capabilities cover the intended workflows. An export product would not automatically read live chats and is not implemented here. No alternate product has been substituted.

## Materials prepared

- Working source, five MCP tools, explicit tool annotations and consent controls.
- Windows 2.2.0 private distribution package and checksum.
- Current setup/build instructions and technical data-practices inventory.
- Five positive and three negative draft review cases in `review-cases.json`.
- `plugin.draft.json` is a metadata preparation copy, not a complete upload bundle. The private source manifest is preserved.
- Automated engine/protocol tests and isolated frozen-runtime verification exist. They do not establish public-directory approval or host-level review-case results.

## Confirmed publisher details

Publisher: Mahdhi Muzammil. Intended countries: all available countries, represented by an empty restriction list. The plugin is free with no plugin commerce. Provider: register.lk; hosting plan/type and access are unverified. The publisher requires the existing live-chat features to remain.

## Remaining decisions and evidence

- Product direction and authorized access model; local submission eligibility if retaining stdio.
- Confirm the selected OpenAI organization identity is verified as Mahdhi Muzammil; the intended name has been supplied, but dashboard verification has not been inspected.
- Independent public branding or permission for the third-party branding.
- Four live, verified pages: product website, support, privacy policy and terms. The repository/Issues provide source and issue reporting; draft policy material is not an adopted published privacy policy.
- A real demo recording in the intended ChatGPT host, hosted where reviewers can view it. The walkthrough is prepared below, but no video is claimed complete.
- Dedicated reviewer access with sample data; submit any credentials through secure portal fields only.
- Organization/domain verification, imported metadata, scans and authorized developer attestations.

## Hosting

The proposed hostname is `wa.robotuae.com`. No server has been deployed there and no DNS change is included. The current dashboard is loopback-only administration; do not expose it as a remote MCP endpoint. A hosted integration would require an authenticated HTTPS MCP implementation, per-user session/storage isolation, explicit consent, token lifecycle and deletion controls. The provider is register.lk. The specific hosting plan, access and authorized integration model are still needed before selecting a deployment design.

## Demo walkthrough to record after eligibility and development setup are resolved

Use a dedicated sample account. Show the actual version in ChatGPT, pairing/setup without exposing QR/session credentials, a recent private request, a group commitment, pagination, and message-sharing revocation. Run the prompts in `review-cases.json`, showing real tool results and clear limitations. Keep unrelated chats, tokens and account details off screen. Computer/browser control can help rehearse the flow; video capture must be available or started by the publisher. Verify the saved recording and its public/reviewer access before adding its URL.

## Next step

Preserve the requested live-chat features and resolve authorized integration access and local submission eligibility first. Then complete publisher/listing facts and reviewer materials, rebuild and inspect the exact bundle, and only then upload a draft if authorized. Upload, submission for review and publication are distinct states. See [OpenAI submission documentation](https://developers.openai.com/plugins/deploy/submission).
