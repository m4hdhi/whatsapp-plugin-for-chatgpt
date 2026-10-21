# WhatsApp for ChatGPT Windows — 2.2.1

Made by [Mahdhi](https://www.linkedin.com/in/m4hdhi/).

**Default: no OpenAI API key required.** Ask ChatGPT to read permitted messages and analyze them in your conversation using your ChatGPT plan. Your plan limits and local plugin availability apply.

The portable plugin edition needs no separate GroupBrief installer, Docker, Python or Node installation. Its download includes the Windows WhatsApp helper, browser and runtimes. This is a local plugin with a background helper, not a hosted service or an official WhatsApp integration.

## Add the plugin

Use the entire **2.2.1 ZIP**, including `bin` and `helper`. Do not copy only the plugin manifest or executable. Version 2.2.1 distinguishes helper authentication failures from denied sharing and checks portable runtime completeness before registration. Your message-sharing checkbox and saved-brief checkbox are separate; enable and save the first for new-message reads. A fresh installation keeps both off until you choose.

If upgrading from the old GroupBrief installer, its desktop/sign-in shortcuts still point to that old installation. Quit that helper first and start this version with `Connect-WhatsApp.cmd`. Avoid starting both editions. Your WhatsApp pairing and data remain in the existing local profile.

1. If upgrading, quit the old GroupBrief helper from its Windows tray and close ChatGPT first. Extract the whole ZIP. Do not run it inside Windows' ZIP preview. Keep your existing profile to preserve pairing and messages.
2. Double-click `Add-to-ChatGPT.cmd`. It copies the plugin and its helper into your personal plugin folder and makes it available. It preserves other plugins and does not enable itself or change WhatsApp permission.
3. Restart ChatGPT Windows. Open Plugins, find **WhatsApp** by **Mahdhi** under Personal plugins, and choose Install. The account must support local Work chats and allow local plugins.
4. In a local Work chat, select WhatsApp and ask: **Connect my WhatsApp.** Its setup tool starts the bundled helper and opens the local pairing page.
5. Scan the QR in WhatsApp > Settings > Linked Devices. Choose private chats/groups or all chats with exclusions and save processing permission. In Settings, enable **Allow ChatGPT to read permitted messages on request** and save. Existing summaries-only permission does not grant message access.
6. Leave the API key blank. Ask ChatGPT: **Read my WhatsApp messages from the last 24 hours. Summarize important updates and tell me which requests and deadlines need my attention.**

If setup does not open from ChatGPT, run `Connect-WhatsApp.cmd` from the extracted folder. An existing working native GroupBrief profile is reused, including pairing and permissions. The older Docker installation is a separate profile.

## What runs

The plugin starts the included Windows helper when needed; the helper remains in the system tray so it can receive messages and run reminders. Keep the PC awake. Quit from its tray menu to stop monitoring. There is no Installed Apps entry, desktop shortcut or sign-in startup registration created by this package. Removing the ChatGPT plugin alone does not stop an already-running helper: quit it from the tray first.

ChatGPT's `read_whatsapp_messages` tool returns locally captured text/captions, sender/chat names, mentions and timestamps. ChatGPT analyzes that evidence itself. Reads do not mark messages processed or trigger an API request. The dashboard's **Refresh messages** button also works without a key.

The default window is 24 hours; you can request up to seven days within your retention and permission period. Pages contain at most 50 messages with a continuation cursor. Long messages are truncated with a flag. Photos, voice notes and attachments are not analyzed. Live capture and periodic recovery need the helper running and the PC awake; history and recovery may be incomplete.

Analysis appears in your ChatGPT conversation. It does **not** save dashboard tasks, schedule reminders, send replies or automatically post into existing ChatGPT conversations. Review uncertain assignments and deadlines. Ask ChatGPT for a reminder separately if your environment supports that feature; the plugin itself does not create it.

## Optional API features

For automatic analysis while you are away, save an OpenAI API key and enable **Enable automatic analysis using an API key** in Settings. This enables periodic dashboard briefs and task extraction. Saved tasks can produce Windows or optional Pushover reminders. API usage is billed separately from ChatGPT.

Background analysis is off by default, including on upgrade, even if a key is already saved. Existing scheduled local reminders continue according to your notification settings. Saved brief/task access has a separate **Allow ChatGPT to read my permitted briefings and tasks** permission; message sharing works independently.

## Permissions and storage

New profiles start with processing paused and both ChatGPT sharing permissions off. Every read checks current chat permissions, exclusions, retention and the permission start time. The setup tool cannot grant permission. Revocation stops future reads; content already shared remains in its ChatGPT conversation. No API key, WhatsApp session or user's chat history is included in the ZIP.

Profile data stays under `%LOCALAPPDATA%\GroupBrief`. The personal plugin is under `%USERPROFILE%\.codex\plugins\groupbrief`. The personal catalog is under `%USERPROFILE%\.agents\plugins\marketplace.json`; registration preserves existing entries and creates a backup before its first change.

The binaries are unsigned. This private package has not been published to the OpenAI public directory. Public distribution of a local-MCP plugin requires eligibility/approval; account or organization policies can block local installation.

[OpenAI plugin packaging and local installation](https://developers.openai.com/plugins/build/plugins) · [Desktop-only distribution](https://developers.openai.com/plugins/deploy/desktop-only)
