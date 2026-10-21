# WhatsApp integration for ChatGPT

Made by [Mahdhi Muzammil](https://www.linkedin.com/in/m4hdhi/). Free, open-source distribution under the MIT license.

An independent Windows integration that lets ChatGPT read permitted WhatsApp text messages and captions on request. ChatGPT analyzes the returned evidence in the conversation; no OpenAI API key is needed for that default workflow. This project is not affiliated with or endorsed by WhatsApp, Meta or OpenAI.

**Public directory status: not submitted or approved.** The current linked-device bridge is unofficial and conflicts with OpenAI's public-directory rule on unofficial connectors. Local MCP submissions also need approved-partner eligibility. Hosting this same bridge does not remove those requirements. See [submission readiness](submission/READINESS.md).

The source and downloads are public. When installation documentation calls this a personal/private plugin, it means users install it into their own ChatGPT environment outside the public OpenAI directory; it does not mean this GitHub repository is private.

## Download and connect

Get the Windows ZIP and SHA-256 file from [Releases](https://github.com/m4hdhi/whatsapp-plugin-for-chatgpt/releases). No Docker, Python or Node installation is required for the packaged Windows edition.

1. Quit an older GroupBrief tray helper and close ChatGPT before upgrading. Keep your existing profile.
2. Extract the ZIP and run `Add-to-ChatGPT.cmd`.
3. Restart ChatGPT Windows, open Plugins → Personal, and install **WhatsApp** by **Mahdhi**. Your account must support local Work chats and permit local plugins.
4. Run `Connect-WhatsApp.cmd` or ask the plugin to connect WhatsApp. Pair via WhatsApp → Linked Devices.
5. Select private chats, groups, or all chats with exclusions and save processing permission.
6. In Settings, enable **Allow ChatGPT to read permitted messages on request**. Leave the API key blank.
7. Ask: **Read my WhatsApp messages from the last 24 hours and tell me what needs my attention.**

Keep the helper running and the PC awake. This edition does not work as a hosted web/mobile plugin. [Detailed guide](native/chatgpt-plugin/README.md).

## Capabilities

| Tool | Behavior |
| --- | --- |
| `read_whatsapp_messages` | Returns permitted captured text/captions, names, mentions and timestamps, with bounded pagination. |
| `get_whatsapp_brief` | Reads existing saved summaries and tasks with separate briefing permission. |
| `list_whatsapp_tasks` | Reads existing open tasks. |
| `groupbrief_status` | Reports connection and sharing status. |
| `open_whatsapp_setup` | Starts the bundled helper and opens local pairing/settings; it does not grant permissions. |

The default read window is 24 hours; a request may cover up to seven days, subject to retention and consent time. Each page has at most 50 messages. Long bodies are flagged as truncated. Capture and recovery can be incomplete. Photos, voice notes and attachments are not analyzed.

Reading messages does not trigger an OpenAI API call, mark messages processed, send replies, save ChatGPT-generated tasks, or schedule reminders. Conversation analysis appears in ChatGPT. Optional API analysis can generate dashboard briefs and tasks automatically and use local notifications. It requires a separately billed API key and explicit activation; background analysis is off by default, including upgrades with saved keys.

## Privacy and permissions

The local profile is `%LOCALAPPDATA%\GroupBrief`. New profiles start with capture and sharing disabled. Message sharing and saved-brief sharing are separate permissions. Current chat scope, exclusions, consent start times and retention apply to each read. Revocation stops future reads; messages already shared remain in their ChatGPT conversation.

Never upload `.env`, `local-config.json`, `runtime.json`, databases, logs, or linked-device sessions to an issue or repository. The download and source contain none of your account data. [Technical data practices](docs/DATA-PRACTICES.md) describe implementation behavior; they are not a publisher-approved privacy policy.

## Development

Use Python 3.12 and Node 24. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
node --test native/bridge/bridge.test.cjs waha/metadata-patch.test.cjs
node --check static/app.js
```

[Build the portable Windows package](docs/BUILD.md). Historical Docker instructions remain in [the legacy guide](docs/legacy-docker-guide.md); that edition uses a separate profile. The native Windows helper uses `whatsapp-web.js`; Docker uses WAHA with the metadata patch in `waha/`.

## Support and license

Use [GitHub Issues](https://github.com/m4hdhi/whatsapp-plugin-for-chatgpt/issues) for reproducible bugs, excluding private content. No response-time commitment is made. Source code is MIT licensed; dependencies retain their own licenses. The WhatsApp name and supplied logo are third-party branding and are not granted an MIT trademark license. Review branding before any public-directory submission.
