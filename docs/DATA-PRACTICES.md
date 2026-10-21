# Technical data practices — publisher review required

This describes the current local implementation. It is not an adopted public privacy policy or a promise about a future hosted service.

- The linked-device bridge connects to WhatsApp and stores its session in the user's local GroupBrief profile.
- The helper stores permitted text/captions, chat identifiers/names, sender labels, mentions, timestamps, and optional extracted summaries/tasks in a local SQLite database.
- Chat capture permission and ChatGPT sharing permissions are separate. Message reads return a bounded set of evidence to ChatGPT. Brief sharing returns saved summaries/tasks. Provider keys and session credentials are not returned by MCP tools.
- Optional background analysis sends permitted text to the OpenAI API when enabled with a saved key. It is disabled by default. Pushover is optional and receives configured reminder content; desktop notifications use Windows.
- Message retention defaults to seven days and is configurable from seven to ninety days. The reader exposes at most a seven-day window. Summary cleanup uses thirty days; completed/dismissed tasks older than thirty days are removed. Open tasks may remain. Cleanup runs while the helper is running.
- Pausing or excluding chats removes their stored message text and summaries; existing task titles may remain, but restricted chat data is filtered from sharing. Previously delivered notifications and ChatGPT conversations are not recalled.
- Credentials are stored in the local profile, protected by the user's Windows permissions, not by an application-level encrypted vault. Protect and restrict access to that profile.
- No hosted analytics or hosted publisher database is part of this local implementation. GitHub downloads/issues and third-party services have their own data practices. Users should never put sensitive chat content or secrets into public issues.

Before publication, the publisher must confirm identity/contact details, applicable policy terms, deletion/support handling, countries and any commerce. A hosted edition would need a new data-flow review, policy and isolation design.
