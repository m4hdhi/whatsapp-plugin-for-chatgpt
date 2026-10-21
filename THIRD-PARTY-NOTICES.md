# Third-party components

GroupBrief's own source and the metadata extension in `waha/` are supplied under the MIT license in `LICENSE`.

The Docker build downloads [WAHA 2026.9.2](https://github.com/devlikeapro/waha/releases/tag/2026.9.2), copyright its contributors, under the [Apache License 2.0](https://github.com/devlikeapro/waha/blob/2026.9.2/LICENSE). The official image contains other components under their respective licenses. Preserve its license files and notices when redistributing the image.

`Dockerfile.waha` derives from the pinned official image and applies `waha/metadata-patch.cjs`. This modification adds an explicit `metadataOnly=true` path to the WEBJS chat list. It projects chat metadata from the local WhatsApp store without serializing messages. The extension checks exact compiled-source hashes before modifying the module and fails if the upstream artifact changes. The normal upstream chat endpoint remains unchanged when that parameter is absent. This is a GroupBrief modification, not an upstream WAHA release.

The distributed source ZIP contains the extension, not the WAHA image or a copy of WhatsApp. The assistant's Python dependencies are enumerated in `requirements.lock` and retain their respective licenses.
