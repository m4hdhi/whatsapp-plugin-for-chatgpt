# Windows build

The source does not include downloaded runtimes, dependency directories or personal data. Run from the repository root on Windows using Python 3.12.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r native/requirements-build.txt
cd native/bridge
npm ci --omit=dev --ignore-scripts
cd ../..
```

Provide Node and Chromium matching `native/runtime-pins.json`. The build checks the actual executable hashes and rejects mismatched binaries. The recorded release used Node 24.12.0 and Chromium 149.0.7827.55. Do not remove the checks to use arbitrary runtimes; intentionally update pins and rerun verification when upgrading.

```powershell
.venv\Scripts\python native/build-windows.py --stage-only --node C:/path/to/node.exe --chromium C:/path/to/chrome-win64
.venv\Scripts\python native/build-portable-plugin.py
```

The second command packages the `work/native-python`, `work/native-link` and `work/native-stage` outputs of the first. Generated ZIP/checksum files go to `outputs/`. `--workspace` optionally selects another build root. These commands require the .NET Framework C# compiler used by the Windows staging script. Building the source is a developer workflow; end users can download the prebuilt release.

Before distributing, test a clean temporary Windows profile, verify all five MCP tools, check consent and revocation, inspect the ZIP for private files, and verify its hash. Release binaries are currently unsigned. Private distribution is distinct from public OpenAI directory eligibility.
