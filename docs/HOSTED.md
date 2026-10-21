# Hosted edition: device-independent access

Made by [Mahdhi Muzammil](https://www.linkedin.com/in/m4hdhi/).

Version 3.0.0-beta.1 is an operator-managed hosted pilot. End users visit a website, sign in, pair WhatsApp, select permitted private/group chats and authorize ChatGPT. Their PC can be switched off after setup. No user-side executable, Docker, Python, Node or OpenAI API key is required for on-demand ChatGPT analysis.

**Not deployed, not approved for the OpenAI directory, and not yet verified inside native ChatGPT clients.** Hosting does not resolve the [unofficial-connector eligibility restriction](https://developers.openai.com/plugins/plugin-guidelines#third-party-content-and-integrations). A custom remote connection requires an eligible account/workspace/interface; public GitHub code does not make the plugin appear for every ChatGPT account. [OpenAI availability information](https://help.openai.com/en/articles/11487775-connected-apps-in-chatgpt).

## Device behavior

| Device | Setup/dashboard | ChatGPT analysis |
| --- | --- | --- |
| Windows, macOS, Linux | Modern browser; no local helper | Remote MCP in a supported ChatGPT interface |
| iPhone/iPad | Responsive browser | Subject to ChatGPT iOS/browser support and account eligibility |
| Android | Responsive browser | Subject to ChatGPT Android/browser support and account eligibility |

The QR must be scanned from WhatsApp's Linked devices screen. Display it on another screen for initial pairing; this edition has no phone-number pairing-code flow. Do not share or publish the QR. After pairing, the setup website can be used from any supported browser.

The hosted tools read captured text/captions and saved summaries/tasks. They do not send WhatsApp messages, analyze audio, save ChatGPT-generated tasks, or schedule reminders. Default analysis happens when you ask ChatGPT. Optional background analysis uses a separately billed API key and an explicit toggle. Pushover delivery of saved-task reminders is optional and has its own service/app requirements. ChatGPT subscription access is not used as a background API credential.

## Hosting for wa.robotuae.com

The publisher requires the existing register.lk shared hosting/cPanel account. Use the [direct cPanel guide](CPANEL.md) for that deployment: it uses Node, Python and sandboxed Chrome without Docker. Runtime prerequisites were verified on the account; full deployment and idle-process persistence are not yet established. The container instructions below are an alternative deployment reference, not a requirement to purchase another host or change the chosen hosting.

The operator installs Docker on the server once. Users do not install it. Start with a small pilot and measure memory/CPU before inviting more people: each account has its own Chromium worker. The generated default caps each bridge at 1 GiB and the gateway at 1 GiB; these are limits, not a capacity guarantee. Configuration accepts at most 50 accounts, not a claim that one small VPS can serve 50 accounts.

## Prepare the server

Use Python 3.12, Git, Docker Engine and the Docker Compose plugin on the Linux server. Clone this repository and install its Python dependencies in a virtual environment. All commands below run on that server. The private configuration lives outside the Git checkout.

```sh
git clone https://github.com/m4hdhi/whatsapp-plugin-for-chatgpt.git
cd whatsapp-plugin-for-chatgpt
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m cloud.manage --directory /srv/whatsapp-config init --url https://wa.robotuae.com
.venv/bin/python -m cloud.manage --directory /srv/whatsapp-config add-user mahdhi
```

Choose a unique password when prompted. The configuration directory must be owned by the operator running these commands. Provision each additional user with `add-user`; distribute credentials through your own secure channel. Do not post credentials in GitHub, ChatGPT, or command arguments.

The CLI generates private `config.json`, `compose.json` and `Caddyfile` files. They contain session/signing credentials and must never be published. It does not start services or modify DNS.

Set only the DNS A record for `wa.robotuae.com` to the server's IPv4 address. Add an AAAA record only if the server is configured for that IPv6 address. Keep the domain's other DNS/mail records unchanged. Permit inbound TCP 80 and 443 for HTTPS issuance/traffic; protect SSH separately. Do not publish the gateway or bridge ports.

```sh
docker compose -f /srv/whatsapp-config/compose.json up -d --build
docker compose -f /srv/whatsapp-config/compose.json ps
```

Caddy obtains HTTPS after DNS points to the server and ports are reachable. Verify `https://wa.robotuae.com/health`, then visit the sign-in page. A health response confirms the gateway is running, not that WhatsApp is paired or messages are complete.

## Connect ChatGPT

1. In an eligible ChatGPT MCP connection-management surface, enter the deployed URL `https://wa.robotuae.com/mcp` and choose OAuth with a predefined public client. Do not enter this URL until the service really exists.
2. Copy the exact redirect URI shown by that management surface. Register it using the command below. The CLI prints a public client ID, not a secret.
3. Enter that client ID in ChatGPT. This server uses a public OAuth client with PKCE S256 and token endpoint authentication `none`; it has no OAuth client secret. If your management surface cannot configure this, compatibility remains unresolved; do not disable authentication.
4. Sign in, review the read-only authorization screen, and allow access. Separately enable message-sharing permission in the website's Settings. Authorizing OAuth alone does not enable capture or sharing.

```sh
.venv/bin/python -m cloud.manage --directory /srv/whatsapp-config add-client --redirect 'EXACT_HTTPS_CALLBACK_FROM_CHATGPT'
docker compose -f /srv/whatsapp-config/compose.json up -d --build
docker compose -f /srv/whatsapp-config/compose.json restart gateway
```

The last restart loads changed configuration even when Compose sees no service-definition change. The callback argument is intentionally a placeholder, not an invented production URL. No dynamic client registration or client-metadata fetching is implemented. Protocol discovery supports predefined clients and exact redirect allowlists. See [OpenAI OAuth guidance](https://developers.openai.com/plugins/build/auth).

In the website, connect WhatsApp, save selected chats or all-chats permission, then enable **Allow ChatGPT to read permitted messages on request**. Ask ChatGPT: “Read my WhatsApp messages from the last 24 hours and tell me what needs my attention.” No API key is required. Grant revocation is available under **Account → Disconnect all ChatGPT grants**.

## Isolation and security boundaries

- One private Chromium container, network and session volume per account. Workers expose no host ports; the gateway can reach each worker. No Docker socket is mounted.
- One SQLite message database per account; no user/tenant parameter in MCP tools. An OAuth token determines identity even if the browser is signed into a different account.
- Browser sessions use Secure, HttpOnly, SameSite cookies with a 12-hour lifetime. Mutations require same-origin CSRF validation. No admin tokens are exposed to browsers or MCP clients.
- OAuth codes expire in two minutes and are one-use; access tokens expire in 15 minutes. Refresh tokens rotate, expire after 30 days, and replay revokes their token family. Password changes invalidate existing identities after gateway restart. Usernames are case-normalized. Passwords use salted PBKDF2-SHA256; bearer credentials are hashed at rest.
- Account and global authentication throttles limit abuse. With the default reverse proxy, IP-level limits are shared because the gateway intentionally does not trust forwarded-IP headers. This conservative limit should be load-tested before larger deployments.
- Webhooks use distinct per-account HMAC secrets. Caddy blocks public webhook paths. Permission, exclusions and retention are checked again during each read. Chat text is untrusted model input.
- The Chromium SUID sandbox is disabled in the bridge container; the container runs as a non-root user with dropped capabilities and no-new-privileges. Do not run it privileged or mount host directories containing other users' data. This is not a substitute for a production security assessment.

Only one gateway process is supported. Multiple Uvicorn workers would create duplicate engines/schedulers. There is no public signup, email verification/reset, MFA, billing or automatic scaling. Accounts are managed by the service operator.

## Operations and data deletion

Use `reset-password ACCOUNT` with the same CLI directory, then restart `gateway`; the user must sign in and reconnect ChatGPT. This retains WhatsApp pairing and chat settings. Browser sign-out ends that browser session; disconnecting ChatGPT grants is a separate account control.

For account erasure, first remove its entry from the private configuration and restart the gateway, then stop/remove only that account's bridge. After verifying the exact account and resolved volume/path, delete its individual session volume, its message database directory in the accounts volume, and its authorization rows. Never delete the shared accounts volume to erase one person. An operator must also remove that person's data from backups according to the adopted retention policy. Automated account-erasure UI is not implemented in this pilot.

Back up configuration and data volumes encrypted, restrict server access, and define a deletion/support process before admitting real users. The server operator can access message plaintext, optional provider credentials and WhatsApp linked-device sessions. This changes the data custody compared with the Windows-local edition. [Hosted data inventory](HOSTED-DATA.md) is technical documentation, not an adopted legal policy.

Do not remove the existing desktop profile or copy it into cloud storage automatically. Users explicitly pair a new linked-device session. To roll back the hosted pilot, stop only its generated Compose project and retain its volumes until the operator decides on deletion. Existing desktop installs are independent.

## Verification before inviting users

Run the automated suite, build both Linux images, and verify a dedicated test account through real HTTPS and a supported ChatGPT host. Verify another user's token cannot access that account, permission/grant revocation takes effect, the connection survives a server restart, and offline capture gaps are reported. Test the actual desired iOS, Android, macOS and Windows ChatGPT interfaces; responsive browser emulation alone does not establish native-client support.

The public listing also needs authorized integration access, appropriate branding rights, adopted privacy/terms pages, publisher verification, reviewer access and a host demonstration. The current draft package remains unsubmitted. Do not advertise this beta as available to every ChatGPT user or as an official WhatsApp product.
