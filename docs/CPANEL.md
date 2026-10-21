# Direct cPanel pilot (no Docker)

Made by [Mahdhi](https://www.linkedin.com/in/m4hdhi/).

This mode targets the publisher's existing register.lk account. End users only need a supported browser and an eligible ChatGPT remote connection. No OpenAI API key is needed for ChatGPT's on-demand analysis. Public-directory approval remains blocked by the unofficial connector rule; deploying a server does not change that.

## Verified hosting prerequisites

On 2026-10-21 the existing account exposed Node 24.21.0, Python 3.12.15, glibc 2.34, an 8 GB physical-memory limit, 400% CPU limit and 300 process limit. These resources are shared with the account's other websites. Google Chrome for Testing 156.0.8078.47 started headless and returned `about:blank` with exit 0, without `--no-sandbox`. Runtime and capacity are not an always-on service guarantee.

The private real-worker probe subsequently passed on this account, including sandboxed WhatsApp QR readiness, authentication checks and clean shutdown. The cPanel Node application is deployed: public HTTPS sign-in, health, OAuth metadata and unauthenticated access restrictions passed. HTTP redirects to HTTPS, and health returned 200 after a cPanel restart request. Real-account pairing, paired-session recovery and idle behavior must still be verified. Do not advertise continuous monitoring until the provider permits persistent background connections and an idle test confirms it. No keep-alive traffic or cron workaround should be used to evade hosting restrictions.

## Private files and installation

Keep source, virtual environment, configuration, browser sessions and databases **outside public_html**. Only cPanel's public document root should be web-accessible. The examples use `$HOME/wa-app` for source and `$HOME/wa-private` for private configuration. Choose a short configuration path because Linux Unix sockets have a path-length limit.

```sh
git clone https://github.com/m4hdhi/whatsapp-plugin-for-chatgpt.git "$HOME/wa-app"
cd "$HOME/wa-app"
/opt/alt/python312/bin/python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
PATH=/opt/alt/alt-nodejs24/root/usr/bin:$PATH PUPPETEER_SKIP_DOWNLOAD=true npm ci --prefix native/bridge --omit=dev --ignore-scripts
```

Install Chrome from the [official Chrome for Testing distribution](https://googlechromelabs.github.io/chrome-for-testing/) into a private directory. Run `ldd` to check dependencies and a sandboxed headless launch before configuring the app. Do not disable the sandbox for this shared-hosting mode. Supply the actual installed executable paths:

```sh
.venv/bin/python -m cloud.manage --directory "$HOME/wa-private" init \
  --url https://wa.robotuae.com --deployment cpanel \
  --python "$HOME/wa-app/.venv/bin/python" \
  --node /opt/alt/alt-nodejs24/root/usr/bin/node \
  --chrome /ABSOLUTE/PRIVATE/PATH/chrome-linux64/chrome
.venv/bin/python -m cloud.manage --directory "$HOME/wa-private" add-user mahdhi
```

The operator enters a unique password in the terminal prompt. Never put it in command arguments, chat, screenshots or Git. Repeat `add-user` for a small number of invited pilot users after measuring capacity. Keep `wa-private` private (0700); configuration is written with mode 0600.

## cPanel setup

Create a **new** Node.js application for `wa.robotuae.com`; do not edit another website's app:

| Setting | Value |
| --- | --- |
| Node version | 24 |
| Mode | Production |
| Application root | `wa-app` (outside public_html) |
| Application URL | `wa.robotuae.com`, path `/` |
| Startup file | `cloud/start.cjs` |
| Environment variable | `WA_CPANEL_DIR=/home/YOUR_CPANEL_USER/wa-private` |

Enable a valid certificate for this subdomain and force HTTPS before any password or WhatsApp pairing. The site needs normal public HTTPS access; its internal services must never be exposed as TCP ports. The launcher binds the Python gateway and each bridge to Unix sockets inside the private configuration directory. Public webhook paths are blocked. The underlying signed webhook validation remains enabled.

Passenger's process policy determines whether the app stays running between visits. Ask the provider whether `PassengerMinInstances 1` and `PassengerMaxInstances 1` are supported for this application, and whether long-running WhatsApp/Chromium processes are permitted. Do not assume those directives are honored by the installed server. A file lock prevents duplicate engines when multiple frontends start; the runtime stops when its owning frontend exits. A subsequent request can restart it, but monitoring during that downtime is not guaranteed.

This mode uses one Linux hosting account rather than separate containers: application-level user separation and private socket permissions remain, but administrators or compromised applications under the same Unix account may access its files. Start with an operator-controlled pilot, not an unrestricted public signup service.

## Verification and connection

1. Check `https://wa.robotuae.com/health` with normal certificate validation.
2. Sign in, pair a dedicated test WhatsApp account, and select permitted chats. Do not record the QR in public screenshots.
3. Send a sample private request and a group request from your own test accounts. Verify only permitted messages appear; revoke a chat and verify its contents disappear from reads.
4. Leave the app idle, test a message, restart the Node application, and test session recovery. Document any gaps before promising reminders.
5. Register the exact ChatGPT OAuth callback using `cloud.manage add-client`, restart the Node app to load the configuration, then follow [Connect ChatGPT](HOSTED.md#connect-chatgpt). Use cPanel restart instead of the Docker commands in that reference.

Optional background API analysis remains disabled by default. ChatGPT on-demand reading does not automatically create reminders. Review the dependency audit and remaining limitations in [verification](../cloud/VERIFICATION.md).
