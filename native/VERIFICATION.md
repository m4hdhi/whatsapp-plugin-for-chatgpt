# GroupBrief Windows 2.0.0 — release verification

## Message capture fix — 21 October 2026

The `2.0.0-message-fix` package fixes current WhatsApp message keys that no longer include `_serialized`, replaces failing full-chat history serialization with a bounded projection of the requested chat, and caps older-history waits below the local API timeout. It also retries a stalled initial browser document once, completes the library's missed already-synced handshake, and uses the current WhatsApp web document rather than a separately cached HTML version. Existing processing permission and permission-time boundaries remain in force.

Fresh checks: 87 Python tests and 9 bridge tests passed. On a paired native session with all-chat consent, the old projection rejected real message keys; the corrected projection accepted them. Recovery found the user's test request. Replaying that real received event through the installed bridge captured it, and the actual analysis endpoint processed one message and created one task. Test content and credentials were not printed in diagnostics. This specific live analysis used the configured provider; the original account-free release checks below did not.

Built and tested on Windows 11 x64 on 20 October 2026. Windows 10/11 x64 is the target; a separate clean Windows 10 virtual machine was not available. This is an unsigned installer, not a Microsoft Store package.

## Fresh execution

- **87 Python tests passed** against real SQLite and the public API, with one Starlette test-client dependency deprecation warning. Remote OpenAI/Pushover boundaries use controlled transports. Coverage includes private/all-chat consent, aliases and exclusions, grant timestamps, task evidence, reminder retry/restart behavior, separate ChatGPT permission, read-only-token restrictions and output limits after scope filtering.
- **Four native bridge tests passed:** content-free metadata projection, numeric pagination, authenticated QR/session lifecycle, active-session preservation, signed incoming/outgoing events, stale-QR rejection and absence of send/logout APIs.
- **Eight Chats and six QR browser regressions passed**, using synthetic fixtures and no external requests.
- The **actual frozen Windows app** started with PATH containing only Windows System32 and provider environment credentials removed. It used bundled Node/Chromium, bound to a free local port, served its dashboard and generated a valid PNG WhatsApp QR. No account was paired. Normal shutdown returned exit code zero and left no Chromium process for that QA profile.
- The tray-enabled frozen app accepted a **Windows test notification** through its native notification channel without Pushover. This verifies API acceptance, not whether Focus or user notification settings display it.
- The **frozen MCP executable** completed JSON-RPC initialization, exposed exactly three read-only tools and called the real local application. Sharing was blocked by default, allowed after explicit permission and blocked again on revocation. Output did not contain administration/read tokens or provider credentials.
- A **real browser connected to the frozen app** verified the Settings workflow, blocked unsaved permission, made the plugin available under a separate test Windows profile, preserved the distinction between availability and ChatGPT installation, and revoked sharing. Desktop/mobile renders had no horizontal overflow or runtime errors. The save-before-connect warning clears after a successful save.
- The **277 MB installer** passed payload integrity and duplicate-entry checks. Its 8,057 payload files installed successfully into an isolated user-owned QA folder. Critical binaries and the final JavaScript asset matched the staged application by SHA256. The installed app started successfully with only bundled runtimes.
- The **uninstaller** removed its 8,059 registered files/records while preserving a deliberately added user file and the separate private settings directory. No real user registry or desktop shortcuts were modified by the installation QA. The same shortcut creation, arguments and ownership-safe removal functions were exercised separately in the QA folder using Windows' real shortcut API.

One preliminary UI run collided with another QA instance's single-instance mutex; it was rerun sequentially and passed. One server test fixture needed the new optional desktop capability attribute; its existing authentication assertions were preserved. Both issues were resolved before the above final results.

## Runtime and data checks

The bundled Node 24.12.0 executable has a valid OpenJS Foundation signature and matches the official Node distribution SHA256. Chromium 149.0.7827.55 and Node are pinned by the supplied runtime manifest. The WhatsApp library and QR dependency are locked in the npm lockfile. The installer bundles its runtimes; it does not install Docker or execute a runtime package installer on the recipient's PC.

The payload and source ZIP exclude environment files, session/profile directories, application databases, logs and personal credentials. Test captures use unpaired profiles and blank credential fields; QR images are not included. Original Docker data and WhatsApp session volumes were not migrated, reset or removed.

The existing Docker installation's launcher error was separately reproduced: another Python service occupied 8765 and returned 404 for /health while the assistant was healthy internally. The launcher now chooses a free local port; its actual NoBrowser run succeeded on 8766. The existing assistant remains healthy at that port with its original data volume.

## Recipient acceptance steps

The recipient still needs to scan their own WhatsApp QR, save their API credential locally and grant chat-processing permission. Native paired-account message sync, live model interpretation and real phone push delivery were not tested. No paid AI test request or WhatsApp reply was sent.

The ChatGPT plugin was verified as a local MCP executable, API permission boundary and discoverable personal-marketplace package. Installation and a tool call in the recipient's actual ChatGPT Windows account remain their acceptance step. This requires a supported local Work chat and permission to install local plugins; the app cannot override organization policy. It reads the authorized brief on request and does not push text into an existing ChatGPT conversation. Windows itself provides automatic reminders.

The PC must remain awake, online and running GroupBrief. Text/captions only; bounded history recovery is not a complete backup. AI results require source/deadline review. Permission changes take effect when acknowledged; already-sent provider requests and delivered notifications cannot be recalled. Local data is protected by Windows ACLs, not application-level at-rest encryption. See the setup guide and third-party notices for storage and integration details.
