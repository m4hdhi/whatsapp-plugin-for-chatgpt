# GroupBrief for Windows

Download and run **GroupBrief-Setup-2.0.0.exe**, then select Install and Finish. It includes its own runtimes and browser; Docker, Python, Node, command prompts and Pushover are not required. This build targets Windows 10/11 x64 and installs for the current Windows user.

## First use

1. Open GroupBrief from the desktop or Start menu. A small system-tray icon keeps the assistant running when you close the browser window.
2. Scan its QR using WhatsApp on your phone → Settings → Linked Devices → Link a Device.
3. Open Settings, save your name/timezone and your own OpenAI API key in the local password field. API billing is separate from a ChatGPT subscription. No credential is included with this installer.
4. Open Chats. Choose specific private chats/groups, or All chats with exclusions. Check the processing permission and save. New permissions apply from the time you save, not to a full historical import.
5. In Settings, enable Windows notifications and send a test. Focus/notification settings in Windows can silence alerts. iPhone Pushover credentials are optional.

The PC must stay awake, online and running GroupBrief. The app summarizes text and captions; it does not inspect attachments or transcribe voice notes. Important requests, decisions, changes and deadlines can be summarized without your name. Group task ownership uses names, mentions and your commitments; incoming private requests may refer to you implicitly. Review the linked source and uncertain dates before relying on a task.

## Connect his ChatGPT Windows app

1. In GroupBrief Settings, check **Allow ChatGPT to read my permitted briefings and tasks** and save.
2. Select **Make available in ChatGPT**. This adds a local plugin entry; it preserves other personal plugins and does not automatically enable anything in ChatGPT.
3. Fully restart the current ChatGPT Windows app. Open Plugins, find **GroupBrief** in the personal/local plugin list, and choose Install. Local plugin availability is subject to the account, app version and organization policy.
4. Start a local **Work** chat, select GroupBrief, and ask: “Summarize important WhatsApp updates and the tasks waiting on me.”

The local plugin exposes three read-only tools: latest brief, open tasks and connection status. It cannot read the provider key, browse raw conversations, send messages, change monitoring scope or control WhatsApp. Turning off ChatGPT sharing blocks further reads immediately. Removing a chat or pausing processing also removes it from plugin results.

This connection lets ChatGPT read the existing brief when you use the plugin. It does not inject messages into an existing ChatGPT conversation or replace Windows reminders with a ChatGPT notification service. If a managed workspace blocks local plugins, its administrator must allow them. The product cannot override that policy. The plugin is packaged according to [official OpenAI local-plugin guidance](https://developers.openai.com/plugins/build/plugins); actual installation in the recipient's ChatGPT account is an acceptance step.

## Permissions and storage

Pause monitoring in Chats to stop capture/AI processing and purge stored source text, summaries and local digest copies. Existing task titles remain history with reminders disabled outside active scope. Previously delivered notifications or provider requests cannot be recalled. Phone/device aliases and verified opaque WhatsApp IDs share permissions; uncertain private identities are held back when needed to protect an exclusion.

The dashboard and bridge bind only to 127.0.0.1. Independent local credentials protect administration, webhooks and the narrow ChatGPT read surface. The app stores settings, provider credentials, source excerpts and linked-device data under `%LOCALAPPDATA%\GroupBrief`, with access restricted to the Windows user and SYSTEM. These files are not application-encrypted at rest. Protect Windows access and backups.

WhatsApp's linked device still has account-level access and can cache other conversations; companion permissions limit storage/AI processing, not the underlying account credential. Permitted text is sent to OpenAI with store:false; applicable provider retention still applies. Pushover receives notification text only if configured. This is an unofficial linked-device integration and may require updates when WhatsApp changes.

Default analysis: every 30 minutes, up to 48 attempted API requests per local day. Selected mode processes one chat per check; All mode batches up to five pending chats. Request count is not a currency budget. Live events are primary; bounded recent-history recovery cannot guarantee a complete offline archive.

## Everyday controls and removal

Use the system-tray menu to reopen or quit GroupBrief. Start at Windows sign-in is an optional installer checkbox. On the next launch, it reuses its saved native profile. Uninstall through Windows Installed apps; saved user data is retained. Program files added by the user are not removed by the manifest-based uninstaller.

For an existing Docker installation, keep it as a separate fallback. The native edition uses a separate linked-device profile and data directory; link it and enter credentials locally once. Stop the old GroupBrief services before using both for the same monitored chats, to avoid duplicate processing. No personal Docker volume, key or session is embedded in this download.

This installer is unsigned. Windows may show an unknown-publisher prompt. Review the source and supplied SHA256 if distributing it internally; a production publisher can sign a rebuilt installer with their own certificate.

## Developer build

Install the locked Python requirements and `pyinstaller==6.16.0`, `pystray==0.19.5`, `Pillow==11.3.0` on a Windows build machine. Run npm ci --omit=dev --ignore-scripts in native/bridge; use its lockfile. Supply a pinned Node executable and clean Chromium distribution to native/build-windows.py. The build bundles the runtimes, freezes the app and MCP helper, verifies the payload and compiles Setup.cs with Windows' .NET Framework compiler. The recipient does not need those developer tools.
