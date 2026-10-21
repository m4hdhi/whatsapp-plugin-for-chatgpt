"""Make the bundled plugin AVAILABLE, without enabling it or editing ChatGPT config."""
from pathlib import Path
import json
import shutil


def register_plugin(source: Path, home: Path | None = None):
    home = (home or Path.home()).resolve()
    source = Path(source).resolve()
    target = home / ".codex" / "plugins" / "groupbrief"
    marketplace = home / ".agents" / "plugins" / "marketplace.json"
    if not target.resolve().is_relative_to(home) or not marketplace.resolve().is_relative_to(home):
        raise ValueError("The personal plugin folders must stay within your Windows profile.")
    if not (source / "bin" / "GroupBriefLink.exe").is_file():
        raise RuntimeError("Reinstall the complete GroupBrief Windows package before registering its ChatGPT plugin.")
    if target.exists() and not (target / ".groupbrief-owned").is_file():
        raise RuntimeError("A different plugin already uses this name. Your existing plugin was left unchanged.")
    if marketplace.exists():
        try:
            catalog = json.loads(marketplace.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError("The existing personal plugin list could not be read. It was left unchanged.") from None
        if not isinstance(catalog, dict) or not isinstance(catalog.get("plugins"), list):
            raise RuntimeError("The existing personal plugin list uses an unsupported format. It was left unchanged.")
    else:
        catalog = {"name": "personal", "interface": {"displayName": "Personal plugins"}, "plugins": []}
    entry = {"name": "groupbrief", "source": {"source": "local", "path": "./.codex/plugins/groupbrief"},
             "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}
    for old in catalog["plugins"]:
        if isinstance(old, dict) and old.get("name") == "groupbrief" and old.get("source") != entry["source"]:
            raise RuntimeError("The personal plugin list already has a different GroupBrief entry. It was left unchanged.")
    catalog["plugins"] = [old for old in catalog["plugins"] if not isinstance(old, dict) or old.get("name") != "groupbrief"] + [entry]
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target.resolve():
        shutil.copytree(source, target, dirs_exist_ok=True)
    (target / ".groupbrief-owned").write_text("GroupBrief local read-only integration\n", encoding="utf-8")
    marketplace.parent.mkdir(parents=True, exist_ok=True)
    if marketplace.exists():
        backup = marketplace.with_name("marketplace.before-groupbrief.json")
        if not backup.exists():
            shutil.copy2(marketplace, backup)
    temporary = marketplace.with_suffix(".groupbrief.tmp")
    temporary.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(marketplace)
    return {"status": "available", "message": "Restart the ChatGPT Windows app, open Plugins, find WhatsApp by Mahdhi under Personal plugins, and choose Install. Use it in a local Work chat. If your organization blocks local plugins, ask its administrator; this plugin cannot override that policy."}
