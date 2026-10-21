# Start here: GroupBrief

**Runs on his Windows PC. Sends reminders to his iPhone.** Keep the PC awake and online.

1. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/), finish setup, and use Linux containers.
2. Extract the complete ZIP to a permanent folder. Double-click **Start.cmd**. The first download/build can take several minutes.
3. In **Settings**, enter his name/nicknames and timezone. Connect his OpenAI API credential using the local password field. API usage is billed separately from ChatGPT. No key or account is included with this package.
4. Install **Pushover** on his iPhone and allow notifications. At [pushover.net](https://pushover.net/), get his User Key and create a GroupBrief application for its API Token. Save both in the PC's Settings screen and send a test notification. Pushover has its own trial/license terms.
5. Select **Connect WhatsApp**. Scan the PC's QR using iPhone WhatsApp → Settings → Linked Devices → Link a Device.
6. Open **Chats** and load the list. Choose **Selected chats** for chosen private chats/groups, or **All chats** for current and future chats with exclusions. Check the permission to read these chats and send text to OpenAI, then save. Wait for a new message and select **Check now**. Automatic checks continue while the PC is running.

He will get a daily digest and reminders for clear assigned deadlines. It reads important content even without his name; names and mentions help establish group task ownership. A private request addressed to “you” can be his task. Uncertain deadlines appear for review on the PC. New permissions start from the time saved. Only permitted chats are processed; status, broadcasts and channels are excluded. This release reads text/captions, not voice notes or attachments.

Use **Pause monitoring** in Chats to revoke permission and purge stored source text/summaries and queued task notifications. Existing task titles remain in history with reminders disabled. Updating an existing installation preserves its previous group-only permission until you explicitly widen it.

Use **Open.cmd** to reopen the dashboard, **Stop.cmd** to pause the services, and **Enable-Startup.cmd** if he wants it to start after Windows sign-in. An iPhone alone cannot run this service.

This uses the **OpenAI API alongside WAHA**, rather than his existing ChatGPT chat. Export the brief if he wants to discuss it in ChatGPT. WAHA is unofficial: WhatsApp restrictions or connection breakage remain possible.

[Full guide and troubleshooting](README.md) · [What was tested](VERIFICATION.md)
