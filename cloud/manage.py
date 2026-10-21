"""Operator CLI. Writes private deployment files; never publishes them to Git.

Run from the source root: python -m cloud.manage --directory /srv/whatsapp-config ...
Passwords are prompted using getpass, never passed as command-line arguments.
"""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit

from .auth import password_hash


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        temp.chmod(0o600)
        handle.write(value)
    temp.replace(path)


def compose(config, directory):
    root = Path(__file__).resolve().parent.parent
    common = {"restart": "unless-stopped", "init": True,
              "security_opt": ["no-new-privileges:true"], "cap_drop": ["ALL"],
              "logging": {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}}}
    gateway = {**common, "build": {"context": str(root), "dockerfile": "cloud/Dockerfile"},
               "volumes": [f"{directory / 'config.json'}:/config/config.json:ro", "accounts:/data"],
               "networks": ["edge"] + ["user-" + uid for uid in config["users"]],
               "mem_limit": "1g", "pids_limit": 256}
    services = {"gateway": gateway,
                "https": {"image": "caddy:2-alpine", "restart": "unless-stopped",
                          "ports": ["80:80", "443:443"], "networks": ["edge"],
                          "volumes": [f"{directory / 'Caddyfile'}:/etc/caddy/Caddyfile:ro", "tls:/data", "caddy-config:/config"]}}
    networks, volumes = {"edge": {}}, {"accounts": {}, "tls": {}, "caddy-config": {}}
    for uid, user in config["users"].items():
        services["bridge-" + uid] = {**common,
            "build": {"context": str(root), "dockerfile": "cloud/Dockerfile.bridge"},
            "environment": {"WA_ACCOUNT": uid, "WAHA_API_KEY": user["bridge_key"], "APP_WEBHOOK_SECRET": user["hook_secret"]},
            "volumes": [f"session-{uid}:/session"], "networks": ["user-" + uid],
            "shm_size": "256m", "mem_limit": "1g", "pids_limit": 256,
            "depends_on": ["gateway"]}
        networks["user-" + uid], volumes["session-" + uid] = {}, {}
    return {"name": "whatsapp-cloud", "services": services, "networks": networks, "volumes": volumes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True, help="Private deployment directory outside the repository")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--url", required=True)
    init.add_argument("--deployment", choices=("container", "cpanel"), default="container")
    init.add_argument("--python", dest="python_path")
    init.add_argument("--node", dest="node_path")
    init.add_argument("--chrome", dest="chrome_path")
    add = commands.add_parser("add-user")
    add.add_argument("username")
    reset = commands.add_parser("reset-password")
    reset.add_argument("username")
    client = commands.add_parser("add-client")
    client.add_argument("--redirect", required=True, help="Exact production HTTPS callback from ChatGPT management")
    commands.add_parser("render")
    args = parser.parse_args()
    directory = args.directory.resolve()
    root = Path(__file__).resolve().parent.parent
    if directory == root or root in directory.parents:
        parser.error("Keep private deployment configuration outside this Git repository.")
    file = directory / "config.json"
    if args.command == "init":
        if file.exists():
            parser.error("Configuration already exists; it has not been overwritten.")
        parsed = urlsplit(args.url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query
                or parsed.fragment or parsed.username or parsed.password or parsed.port not in (None, 443)):
            parser.error("Use an HTTPS origin without a trailing slash.")
        config = {"public_url": args.url, "users": {}, "oauth_clients": {}, "deployment": args.deployment}
        if args.deployment == "cpanel":
            runtime = {name: getattr(args, name + "_path") for name in ("python", "node", "chrome")}
            if not all(value and Path(value).is_absolute() and Path(value).is_file() for value in runtime.values()):
                parser.error("cPanel requires existing absolute --python, --node and --chrome executable paths.")
            private_write(directory / "runtime.json", json.dumps(runtime, indent=2) + "\n")
    else:
        config = json.loads(file.read_text(encoding="utf-8"))
    if args.command in {"add-user", "reset-password"}:
        import re
        uid = args.username.lower()
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,39}", uid):
            parser.error("Account names: 3–40 lowercase letters, digits or hyphens; start with a letter.")
        if args.command == "add-user" and uid in config["users"]:
            parser.error("Account already exists. Use reset-password to change credentials.")
        if args.command == "reset-password" and uid not in config["users"]:
            parser.error("Account not found.")
        password = getpass.getpass("New account password (14+ characters): ")
        if password != getpass.getpass("Repeat password: "):
            parser.error("Passwords did not match.")
        encoded = password_hash(password)
        del password
        if uid not in config["users"]:
            config["users"][uid] = {"bridge_url": f"http://bridge-{uid}:3000", "bridge_key": secrets.token_hex(32), "hook_secret": secrets.token_hex(32)}
        config["users"][uid]["password_hash"] = encoded
    if args.command == "add-client":
        uri = urlsplit(args.redirect)
        if uri.scheme != "https" or not uri.hostname or uri.username or uri.password or uri.query or uri.fragment:
            parser.error("Copy the exact HTTPS callback URL without query or fragment.")
        client_id = secrets.token_urlsafe(24)
        config["oauth_clients"][client_id] = {"redirect_uris": [args.redirect]}
        print("OAuth public client ID:", client_id)
    if config["users"]:
        from .server import validate_config
        validate_config(config)
    private_write(file, json.dumps(config, indent=2) + "\n")
    if config.get("deployment") == "cpanel":
        print("Private cPanel configuration saved. No service was started or DNS changed.")
        return
    private_write(directory / "compose.json", json.dumps(compose(config, directory), indent=2) + "\n")
    host = urlsplit(config["public_url"]).netloc
    private_write(directory / "Caddyfile", f'''{host} {{
    @private path /hooks/*
    respond @private 404
    request_body {{
        max_size 1MB
    }}
    reverse_proxy gateway:8000
}}
''')
    print("Private deployment files written. No service was started and no DNS was changed.")


if __name__ == "__main__":
    main()
