# Changes

## 2.2.0 — ChatGPT analysis without an API key — 21 October 2026

- Read permitted recent text/captions through the new read-only `read_whatsapp_messages` tool and let ChatGPT analyze them in the conversation.
- Require separate message-sharing permission; summaries-only access does not expand on upgrade. Enforce current chat scope, exclusions, consent start times, retention and pagination limits on every read.
- Make background API analysis opt-in, including on upgrade with a saved key. Keep API analysis available for automatic dashboard briefs and tasks.
- Refresh captured messages from the dashboard without invoking AI. Explain that conversation analysis does not save tasks or schedule reminders.
- Preserve WhatsApp branding and the linked Made by Mahdhi credit in the portable package.

## 2.0.0 message capture fix — 21 October 2026

- Capture structured WhatsApp message IDs even when `_serialized` is absent, with stable deduplication keys.
- Recover permitted messages without the failing full-chat serializer; stop older-history waits before the API timeout.
- Restore startup after a stalled initial browser document or a missed already-synced event, without deleting the linked-device profile.

## 2.0.0 — Windows desktop edition

- Add a single Windows installer with bundled Python, Node and Chromium; no Docker or separate developer tools required.
- Add system-tray controls and optional Windows sign-in startup. Keep profiles and settings in the Windows user's private app-data folder.
- Support Windows desktop reminders independently of Pushover, with per-channel retry bookkeeping to avoid repeating successful delivery.
- Bundle a read-only ChatGPT Windows plugin for permitted summaries, open tasks and connection status. Require separate sharing consent and the user's plugin installation in ChatGPT.
- Keep raw chat browsing, API keys, monitoring controls and WhatsApp sending outside the plugin's capabilities.
- Recover the Docker launcher's dashboard-port conflict by choosing a free loopback port and preserving its existing volumes and credentials.

## 1.1.0 — 20 October 2026

- Monitor selected private chats and groups, or all current and future normal chats with exclusions and explicit processing permission. Existing group permission stays limited to those groups.
- Pause processing or remove a chat to purge its stored source text, summaries and queued notifications; retain task history with reminders disabled.
- Read important content independently of name matching. Private incoming requests can refer to the owner implicitly; group assignment uses mentions, aliases and context.
- In all-chat mode, analyze up to five pending chats in one request with per-chat source validation.
- Add a version-checked WAHA metadata extension so listing chats does not fetch message text or slow group metadata. Preserve the upstream message APIs and linked-device session.
- Resolve pending disconnection alerts after recovery, debounce brief connection failures, and repair chat-list loading/retry controls.

## 1.0.1 — 20 October 2026

- Recover a failed WhatsApp session using WAHA's restart endpoint, preserving authentication and saved settings.
- Show normal waiting states while the QR initializes; distinguish expired pairing and already-connected sessions.
- Keep Refresh QR code usable after the connection panel rerenders.
- Resume QR polling after a page reload, prevent overlapping requests, and remove stale connection errors after recovery.
- Add seven backend pairing regression cases and browser coverage for the recovery flow.

## 1.0.0

Initial Windows companion: selected groups, AI summaries, task evidence, deadline review, quiet hours, Pushover reminders, and local launchers.
