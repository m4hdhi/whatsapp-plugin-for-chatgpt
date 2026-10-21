"""Build the offline Windows installer with bundled Python, Node and Chromium."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile

source = Path(__file__).resolve().parents[1]
workspace = source.parents[1] if source.parent.name == "work" else source
work = workspace / "work"
stage = work / "native-stage" / "GroupBrief"
build = work / "native-build"
outputs = workspace / "outputs"
compiler = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
parser = argparse.ArgumentParser()
parser.add_argument("--workspace", type=Path, help="Separate output directory for this build")
parser.add_argument("--skip-python", action="store_true")
parser.add_argument("--stage-only", action="store_true")
parser.add_argument("--node", type=Path, default=Path(r"C:\Program Files\nodejs\node.exe"))
parser.add_argument("--chromium", type=Path, default=Path.home() / "AppData/Local/ms-playwright/chromium-1228/chrome-win64")
args = parser.parse_args()
if args.workspace:
    workspace = args.workspace.resolve()
    work = workspace / "work"
    stage = work / "native-stage" / "GroupBrief"
    build = work / "native-build"
    outputs = workspace / "outputs"

def run(command):
    subprocess.run([str(value) for value in command], cwd=source, check=True)

if not args.skip_python:
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onedir", "--windowed", "--name", "GroupBrief",
         "--distpath", work / "native-python", "--workpath", build / "main", "--specpath", build,
         "--paths", source, "--add-data", str(source / "static") + ";static", "--collect-submodules", "uvicorn",
         "--collect-data", "tzdata", "--hidden-import", "pystray._win32", source / "native/desktop.py"])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--console", "--name", "GroupBriefLink",
         "--distpath", work / "native-link", "--workpath", build / "link", "--specpath", build, "--paths", source / "native", source / "native/mcp_link.py"])
assert (args.chromium / "chrome.exe").is_file() and args.node.is_file()
pins = json.loads((source / "native/runtime-pins.json").read_text(encoding="utf-8"))
assert hashlib.sha256(args.node.read_bytes()).hexdigest() == pins["node_sha256"], "Supply the pinned Node runtime."
assert hashlib.sha256((args.chromium / "chrome.exe").read_bytes()).hexdigest() == pins["chromium_sha256"], "Supply the pinned Chromium runtime."
stage.mkdir(parents=True, exist_ok=True)
shutil.copytree(work / "native-python" / "GroupBrief", stage, dirs_exist_ok=True)
shutil.copytree(source / "native/bridge", stage / "bridge", dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("*.test.cjs", ".env", "__pycache__"))
(stage / "runtime").mkdir(exist_ok=True)
shutil.copy2(args.node, stage / "runtime/node.exe")
shutil.copytree(args.chromium, stage / "runtime/chromium", dirs_exist_ok=True)
shutil.copytree(source / "native/chatgpt-plugin", stage / "chatgpt-plugin", dirs_exist_ok=True)
(stage / "chatgpt-plugin/bin").mkdir(exist_ok=True)
shutil.copy2(work / "native-link/GroupBriefLink.exe", stage / "chatgpt-plugin/bin/GroupBriefLink.exe")
shutil.copy2(source / "native/README.md", stage / "README.md")
shutil.copy2(source / "LICENSE", stage / "LICENSE")
shutil.copy2(source / "native/THIRD-PARTY-NOTICES.md", stage / "THIRD-PARTY-NOTICES.md")
licenses = stage / "licenses"
licenses.mkdir(exist_ok=True)
for name, url in {
    "Node-LICENSE.txt": "https://raw.githubusercontent.com/nodejs/node/v24.12.0/LICENSE",
    "Chromium-LICENSE.txt": "https://raw.githubusercontent.com/chromium/chromium/main/LICENSE",
    "Python-LICENSE.txt": "https://raw.githubusercontent.com/python/cpython/v3.12.10/LICENSE",
    "PyInstaller-LICENSE.txt": "https://raw.githubusercontent.com/pyinstaller/pyinstaller/v6.16.0/COPYING.txt",
}.items():
    destination = licenses / name
    if not destination.exists():
        with urllib.request.urlopen(url, timeout=30) as response:
            destination.write_bytes(response.read())
from importlib import metadata
import importlib.util
pystray_source = Path(importlib.util.find_spec("pystray").origin).parent
shutil.copytree(pystray_source, licenses / "pystray-source", dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for distribution in metadata.distributions():
    for relative in distribution.files or []:
        if Path(relative).name.upper().startswith(("LICENSE", "COPYING", "NOTICE")):
            original = Path(distribution.locate_file(relative))
            if original.is_file():
                target = licenses / "python-packages" / distribution.metadata["Name"] / original.name
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != original.read_bytes():
                    target = target.with_name(original.stem + "-" + hashlib.sha256(str(relative).encode()).hexdigest()[:10] + original.suffix)
                shutil.copy2(original, target)
manifest = pins
(stage / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
build.mkdir(parents=True, exist_ok=True)
stub = build / "UninstallPayload.cs"
stub.write_text('static class Payload { public const string Hash = ""; }\n', encoding="utf-8")
references = ["/r:" + name for name in ("System.Windows.Forms.dll", "System.Drawing.dll", "System.IO.Compression.dll", "System.IO.Compression.FileSystem.dll", "System.Web.Extensions.dll", "Microsoft.CSharp.dll")]
run([compiler, "/nologo", "/codepage:65001", "/target:winexe", "/platform:x64", "/optimize+", "/define:UNINSTALL_ONLY",
     "/out:" + str(stage / "UninstallGroupBrief.exe"), *references, source / "native/Setup.cs", stub])
files = sorted(file for file in stage.rglob("*") if file.is_file())
for file in files:
    relative = file.relative_to(stage)
    assert not any(part in {".sessions", "whatsapp", "data", "demo-data", "__pycache__"} for part in relative.parts)
    assert file.name != ".env" and file.suffix not in {".sqlite3", ".log"}
print(f"Native application staged: {len(files)} files, {sum(file.stat().st_size for file in files):,} bytes.", flush=True)
if args.stage_only:
    raise SystemExit(0)
build.mkdir(parents=True, exist_ok=True)
payload = build / "windows-payload.zip"
with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in files:
        archive.write(file, file.relative_to(stage).as_posix())
with zipfile.ZipFile(payload) as archive:
    assert archive.testzip() is None
digest = hashlib.sha256(payload.read_bytes()).hexdigest()
(build / "Payload.cs").write_text('static class Payload { public const string Hash = "' + digest + '"; }\n', encoding="utf-8")
outputs.mkdir(exist_ok=True)
installer = outputs / "GroupBrief-Setup-2.0.0.exe"
assert compiler.is_file()
run([compiler, "/nologo", "/codepage:65001", "/target:winexe", "/platform:x64", "/optimize+", "/out:" + str(installer),
     "/r:System.Windows.Forms.dll", "/r:System.Drawing.dll", "/r:System.IO.Compression.dll",
     "/r:System.IO.Compression.FileSystem.dll", "/r:System.Web.Extensions.dll", "/r:Microsoft.CSharp.dll",
     "/resource:" + str(payload) + ",GroupBrief.Payload", source / "native/Setup.cs", build / "Payload.cs"])
sha = hashlib.sha256(installer.read_bytes()).hexdigest()
(outputs / "GroupBrief-Setup-2.0.0.sha256").write_text(sha + "  " + installer.name + "\n")
print(f"Built {installer.name}: {installer.stat().st_size:,} bytes; SHA256 {sha}", flush=True)
