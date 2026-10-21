# Bundled runtime notices

GroupBrief's source, local bridge, MCP helper and installer are MIT licensed; see LICENSE. This Windows edition does not contain or run a WAHA Docker image. It uses the separately maintained [whatsapp-web.js 1.34.7](https://github.com/wwebjs/whatsapp-web.js) library under Apache-2.0; its license and dependency notices are retained in bridge/node_modules.

Node.js 24.12.0 is distributed under its MIT license and dependency notices in licenses/Node-LICENSE.txt. Chromium 149.0.7827.55, distributed by Playwright, retains its binaries and included resources; the Chromium BSD license is in licenses/Chromium-LICENSE.txt and upstream third-party notices remain embedded in the browser's about:credits surface.

The frozen app contains Python 3.12.10 under the PSF license (licenses/Python-LICENSE.txt), PyInstaller's bootloader under its GPL-with-distribution-exception license (licenses/PyInstaller-LICENSE.txt), FastAPI, Starlette, Uvicorn, HTTPX, Pydantic, Certifi, tzdata, Pillow and pystray. Each retains its own license. Exact Python application dependencies are pinned in requirements.lock; Node dependencies are pinned in native/bridge/package-lock.json. Additional package notice files are retained in the bundled distribution.

WhatsApp, ChatGPT and Windows names identify third-party products. No endorsement or official WhatsApp API access is claimed. The local ChatGPT plugin uses documented MCP interfaces and requires the user's app/account permission.
