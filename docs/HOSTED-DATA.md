# Hosted data inventory — publisher review required

This is an implementation inventory for the hosted pilot, not an adopted privacy policy.

The account operator provisions a username and password hash. The HTTPS gateway stores hashed session and OAuth credentials, authorization metadata, expiry and throttling records. OAuth clients are configured by the operator; consent grants are specific to the authenticated account.

Each WhatsApp account gets a dedicated bridge session volume and a separate message SQLite database. Chat metadata is used for selection. Capture and subsequent sharing are subject to explicit permission, exclusions, consent start times and retention. Message-sharing and briefing-sharing are separate switches and start disabled. The same retention implementation as the local edition applies; see [the local inventory](DATA-PRACTICES.md) for message, summary and task lifetimes.

On request, permitted text/captions, names, identifiers, timestamps and mentions pass from this server to ChatGPT through authenticated MCP. ChatGPT analyzes them using the user's available plan. No OpenAI API request is needed for that path. Messages already delivered to ChatGPT are not erased by local revocation.

Optional background analysis sends permitted message text to the OpenAI API only with an explicitly enabled toggle and saved key. Optional Pushover delivery shares saved notification content with that service. The gateway does not send WhatsApp messages.

Provider credentials, cached message plaintext, and linked-device sessions are stored on the operator's server. Database and session volumes are protected by filesystem/container permissions, not an application-level encrypted vault. The operator can read them. Use encrypted disks/backups, control administrator access, and adopt an incident/deletion process before public operation.

Browser sessions last 12 hours, authorization codes two minutes, access tokens 15 minutes and rotating refresh tokens 30 days. Expired authorization/throttle records are pruned during request throttling. Stopping the server stops scheduled cleanup. Revoking grants does not erase historical message databases. Account erasure is operator-managed in this pilot; instructions are in [the deployment guide](HOSTED.md).

No public advertising analytics, public user directory or self-signup is implemented. Do not publish databases, raw logs, QR codes, private configuration or session files in the source repository or support issues. Production support contact, privacy terms, backup retention and deletion response commitments must be decided by the publisher.
