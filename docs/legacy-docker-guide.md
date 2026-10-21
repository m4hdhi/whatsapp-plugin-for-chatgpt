# GroupBrief for Windows and iPhone

A personal assistant for WhatsApp private chats and groups: important updates, tasks with source messages, a daily iPhone digest, and deadline reminders. Choose specific chats or allow all current and future chats with exclusions. The Windows PC runs the service. His iPhone stays on the normal WhatsApp app and receives notifications through Pushover.

This package adds a companion and a small metadata extension to a pinned WAHA image. Start.cmd builds both automatically; no repository fork is needed. It uses the OpenAI API; it does not read or write his existing ChatGPT conversation, and ChatGPT subscription billing does not cover its API calls.

## First launch

1. Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) and finish its setup. Use **Linux containers**. Docker Desktop must be running.
2. Extract this entire folder to a location you will keep, such as `Documents\GroupBrief`. Do not run it from inside the ZIP.
3. Double-click **Start.cmd**. The first launch downloads WAHA and builds the assistant. It opens a signed-in local dashboard. The launcher chooses an available port from 8765–8799 and remembers it in the private `.env` file.
4. Open **Settings**. Set his name, aliases/nicknames that people use in groups, and his timezone. Save his own OpenAI API credential through the local password field. No credential is included with this download. Never send API keys or the local `.env` in a chat or email. The secure OpenAI Platform setup flow in the development chat can provision a key; finish that flow if using it.
5. Set up Pushover as described below, save its two credentials in Settings, and select **Send test notification**.
6. Select **Connect WhatsApp**. On his iPhone: WhatsApp → Settings → Linked Devices → Link a Device. Scan the QR shown on the PC. Refresh the QR if it expires. Existing WhatsApp Web sessions can remain linked subject to WhatsApp's linked-device limits.
7. Open **Chats** and load the list. Choose **Selected chats** and tick private chats/groups, or choose **All chats** and untick exclusions. Check the permission to read those chats and send their text to OpenAI, then **Save monitoring permissions**. New permissions start from the time you save; no full old-history import is performed. Then select **Check now** after a new message arrives.

The setup is complete when WhatsApp is connected, an API key and push credentials are configured, chat processing is allowed, and a test notification reaches his iPhone. A successful test push confirms Pushover acceptance; phone Focus modes, notification permission, and network access still affect display.

## Set up iPhone reminders

1. Install **Pushover** from the iPhone App Store, create/sign into his account, and allow notifications.
2. Sign in at [pushover.net](https://pushover.net/). Copy his **User Key**.
3. Use [Create an Application/API Token](https://pushover.net/apps/build) and name it **GroupBrief**. Copy the application's **API Token**.
4. On the PC's GroupBrief Settings page, save the User Key and API Token in their respective local fields. Send a test notification.

Pushover is a separate service with its own trial/license terms. Check [current pricing](https://pushover.net/pricing) before purchasing. No purchase, email, Teams message, or WhatsApp reply is made by this package's installer.

## Everyday use

- **Overview:** recent chat summaries, connection state, and upcoming tasks.
- **Tasks:** see the original supporting messages, mark done/dismissed, snooze, and review uncertain deadlines. Confirm the deadline before enabling reminders on a task flagged for review. Dates in the review editor use the browser's local timezone; the label tells you this.
- **Chats:** choose selected private chats/groups, or all current and future normal chats with exclusions. New private permissions, switching to All, or including an excluded chat require consent. **Pause monitoring** revokes permission. Removing/excluding a chat or pausing purges its stored raw messages, summaries and pending task notifications, plus local digest records that may contain copied summaries. Existing task titles remain in history, with reminders disabled outside the allowed scope. Notifications already delivered to the phone/provider cannot be recalled. This does not leave or delete a WhatsApp conversation.
- **Settings:** change check interval, digest time, quiet hours, reminder lead time, daily AI request cap, retention, and provider credentials. Blank credential fields preserve saved credentials.
- **Export brief:** save readable Markdown that you can upload or paste into a normal ChatGPT chat if you want to discuss the results there.
- **Open.cmd:** reopen the dashboard already signed in. **Stop.cmd:** stop the services while preserving data.
- **Enable-Startup.cmd:** optionally start after this Windows user signs in. Keep this folder at the same path. **Disable-Startup.cmd** removes that startup shortcut.

Keep the PC **on, awake, online, and signed in**, with Docker Desktop available. Closing the browser is fine. The service cannot run continuously on iPhone alone. If the PC is asleep or off, it cannot check messages or send reminders; pending notifications are considered again after it resumes. Configure Windows sleep settings yourself if you need always-on monitoring.

## What is monitored

The assistant uses a WhatsApp linked-device session via WAHA's WEBJS engine. Only permitted normal private/group chat IDs enter the companion's message database. All mode includes future chats automatically, except saved exclusions. Status updates, broadcasts and newsletters/channels are excluded. Your own messages provide context for your commitments. Existing installations keep their previous selected-group scope until you grant wider permission; an update never silently enables private or all-chat processing.

It reads message content, not just names. Summaries cover important requests, announcements, decisions, changes, dates and unanswered questions even if your name is absent. In a private chat, “Can you send the invoice tomorrow?” can be your task because you are the recipient. In a group, your name, aliases, WhatsApp mentions or your own explicit commitment help establish ownership. General group announcements are not automatically your personal tasks. Your outgoing requests to someone else are not your commitments. Unclear assignments/deadlines need review, and AI interpretation still needs checking against the shown source.

The first release analyzes **text and captions**. It does not transcribe voice notes, inspect images, read document attachments, or reconstruct deleted/view-once content. If a message says “see the attached schedule,” check the attachment yourself. Source excerpts are shown beside tasks so you can verify the result. AI interpretation can still be wrong.

New message events are the primary input. Available recent messages are also polled as a recovery aid, rotating through up to ten permitted chats per pass and at most 100 available messages per chat. Newly granted scope excludes messages predating that permission. WhatsApp Web only exposes history synced to the linked device. This is **not a complete chat backup**, and missed messages during an outage cannot always be recovered. Very busy chats can exceed the recovery window; check the connection and backlog in the dashboard.

WhatsApp can represent a private conversation by a phone ID or an opaque linked ID. The assistant normalizes equivalent phone/device IDs and uses verified metadata mappings when available. If a phone conversation is excluded, an unresolved opaque ID is held back until it can be identified, so it cannot bypass that exclusion. An unresolved exclusion represented by an opaque ID can pause private capture until its identity is verified; group capture continues and the dashboard explains the pause. It never guesses a phone number from an opaque ID.

## Reminders and reliability

Automatic AI requests are capped by the daily request setting. Selected mode handles one chat per check (up to 100 new messages); All mode handles up to five pending chats per request (up to 30 new messages each when batching multiple chats), with bounded earlier context. Task source IDs must belong to the same chat. The default interval is 30 minutes and the cap is 48 attempted requests per local day. A request cap is not a currency limit: set a separate project budget/usage alert in OpenAI Platform. Pending messages remain available when the cap is reached or a provider fails.

The dashboard checks the WhatsApp session periodically. Two consecutive failed checks produce an outage notification. Pending outage notices are marked Recovered when the session returns to WORKING. WAHA handles brief reconnects; GroupBrief does not repeatedly restart an already recovering session. Use Connect WhatsApp if manual recovery is needed.

The assistant stores tasks and notification attempts across restarts. A reminder is eligible only for an open task with a clear or user-confirmed deadline; quiet hours defer delivery. A task remains open until you mark it done or dismiss it. Transient Pushover failures retry with backoff up to five attempts; permanent rejections remain visible and stop. There is a small unavoidable duplicate-delivery window if a push is accepted but its response is lost or the process stops before recording it.

Permission changes take effect when the save/pause completes. An in-progress provider request can delay this acknowledgement and cannot be recalled after it has been sent.

This is an **unofficial WhatsApp integration**. Account restrictions and breakage from WhatsApp changes are possible even when only reading. Do not treat it as a guaranteed service for an indispensable phone number. WAHA is independently maintained and is not endorsed by Meta or OpenAI.

## Privacy and storage

- The dashboard binds only to the PC's loopback address; it is not available on the LAN or public internet. Do not add port forwarding, a public tunnel, or change the bind address to expose it.
- The installer generates independent local administration, webhook, and WAHA credentials. Dashboard API calls require authentication; WAHA webhooks are verified using raw-body HMAC SHA-512.
- Credentials, selected message excerpts, tasks, and summaries stay in the local Docker data volume. WAHA's linked-device session lives in a separate volume. These are **not application-encrypted at rest**. Use Windows disk encryption and protect access to Docker/Desktop backups. Anyone controlling this Windows account or Docker can access them.
- Loading Chats retrieves and locally caches only names, IDs and chat types through the bundled metadata extension. It does not fetch message bodies as part of chat selection. Processing permission gates companion message storage, AI analysis and task reminders.
- WAHA itself has the account-level access of a linked WhatsApp device and may cache other conversations. The companion's permissions do not turn WhatsApp's linked-device session into a chat-scoped credential.
- Permitted message batches are sent to OpenAI for analysis with `store:false`. This does not override OpenAI's applicable service data-retention policies. Reminder/digest text is sent to Pushover and delivered through its notification service. Use the permission control only for conversations you are allowed to process; agree with participants and follow your organization's rules.
- Raw message retention is configurable from 7 to 90 days. Supporting excerpts expire with the raw messages, even if a task remains open. Task titles/deadlines remain; closed task history is cleaned up after 30 days. Summaries and completed notification records are kept for up to 30 days. Never share a copy of your `.env`, Docker volumes, QR code, session files, or provider credentials.
- The distributed ZIP contains source, launchers, documentation, and tests only. It contains no real group messages, session, account, or provider secret.

## Troubleshooting

**Docker is not ready / wrong container mode:** finish Docker Desktop's initial setup, switch to Linux containers, and run Start.cmd again. Docker Desktop on Windows typically uses WSL 2. Installation or corporate policy may require IT approval.

**Dashboard says sign in:** open it through Open.cmd or Start.cmd. The launcher supplies the local sign-in token in a URL fragment, which the page removes immediately. Keep browser history and this folder private.

**No QR / session failed:** select **Connect WhatsApp** or **Refresh QR code**. An unscanned pairing session can expire; version 1.0.1 restarts a failed session without deleting its saved authentication. Starting/preparing messages are normal while the QR loads, and reloading the dashboard resumes pairing automatically. The saved OpenAI key is separate from WhatsApp linking. If WhatsApp is already connected, no QR is needed. If pairing still fails, check Docker Desktop and WhatsApp → Linked Devices on the iPhone.

**Connected but no summaries:** save chat permissions, check the API key, wait for a new permitted text message, then Check now. Processing is off until permission is granted. Polling can recover only recent available history since the permission boundary. The daily request cap and provider errors appear in the dashboard.

**Chat list unavailable / stuck loading:** wait until WhatsApp is WORKING and select Load chats again. Version 1.1.0 clears the busy control after success or failure and retries after reconnection. If the message says the metadata extension is unavailable, run Start.cmd from the updated complete folder to build its WAHA image; do not substitute the stock image in Compose.

**No iPhone reminders:** send a test notification; verify both Pushover keys, notification permission, Focus modes, timezone, quiet hours, task review status, and whether the PC was awake. “Accepted by provider” is not a read receipt.

**Inspect containers:** open PowerShell in this folder and run `docker compose ps`. Avoid sharing unredacted container logs, settings databases, or `.env` files; they can contain private material.

**Dashboard port conflict after installation:** the initial launcher chooses an available port automatically. If another application later takes that saved port, stop GroupBrief and change only `APP_PORT` in its private `.env` to a free port between 1024 and 65535. Keep the secret values private and run Start.cmd again. Do not change the loopback bind address.

**Stop without deleting data:** use Stop.cmd. Removing/recreating the containers preserves named volumes. Removing the `assistant-data` volume deletes saved settings/tasks; removing `whatsapp-session` removes the linked-device session. Do not delete volumes as an ordinary troubleshooting step.

## Developer notes

Python 3.12, FastAPI, SQLite, and a static browser interface. The delivered Windows installation needs only Docker Desktop; Python/Node do not need to be installed on his PC. The source is MIT licensed; upstream WAHA remains separately licensed under its own license.

Dockerfile.waha pins WAHA `latest-2026.9.2` by immutable registry digest and applies `waha/metadata-patch.cjs`. Exact compiled-module hashes are verified before adding the opt-in metadata path; an unsupported image fails the build. Its tests run during the Docker build. It avoids stock chat serialization/group-metadata RPCs on the selection path; upstream message and session APIs remain intact. Compose does not publish WAHA's API/dashboard ports. The first launch downloads images and packages from their official registries. See [third-party notices](THIRD-PARTY-NOTICES.md). Refresh pins only after validating compatibility.

Local tests (development machine with Python): create a virtual environment, install `requirements-dev.txt`, and run `python -m pytest -q`. Do not set real credentials when running tests. To run the deterministic preview, use a fresh scratch data directory, `DEMO_MODE=1`, independent random `APP_ADMIN_TOKEN` and `APP_WEBHOOK_SECRET` of at least 32 characters, and `uvicorn app.server:create_app --factory --host 127.0.0.1 --port 8765 --no-access-log`. Demo mode never contacts WhatsApp, OpenAI, or Pushover and is visibly labelled.

Primary integration references: [WAHA source/release](https://github.com/devlikeapro/waha/releases/tag/2026.9.2), [sessions](https://waha.devlike.pro/docs/how-to/sessions/), [groups](https://waha.devlike.pro/docs/how-to/groups/), [message events and signatures](https://waha.devlike.pro/docs/how-to/events/), [available chat history](https://waha.devlike.pro/docs/how-to/chats/), [OpenAI structured output](https://developers.openai.com/api/docs/guides/structured-outputs), [Pushover API](https://pushover.net/api).
