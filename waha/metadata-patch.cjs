'use strict';

/*
 * GroupBrief metadata-only extension for WAHA 2026.9.2.
 * Copyright 2026 GroupBrief contributors. MIT license (see project LICENSE).
 * NOTICE: the base WAHA software is Copyright devlikeapro contributors,
 * licensed under Apache-2.0: https://github.com/devlikeapro/waha .
 * This extension changes only its pinned compiled WEBJS getChats method.
 */

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const PINNED_ENGINE_SHA256 = '927af227df6ff97c3aab5cb4ae83c8e17792830777e821aa71cca0741686bf9a';
const PINNED_CONTROLLER_SHA256 = '820984592bff0d8ebe8260779f9128ba21df3cb7075b0a51dbcf29b486a63a8c';
const ENGINE_ANCHOR = '    getChats(pagination, filter = null) {\n';

// This function is serialized by Puppeteer. It must capture no outer variables.
// Read only explicitly selected metadata properties. Never serialize a chat.
function readChatMetadata(query) {
  const clamp = (value, fallback, minimum, maximum) => {
    const numeric = Number(value);
    return Number.isFinite(numeric)
      ? Math.min(maximum, Math.max(minimum, Math.floor(numeric)))
      : fallback;
  };
  const limit = clamp(query.limit ?? 100, 100, 1, 1000);
  const offset = clamp(query.offset ?? 0, 0, 0, 50000);
  const collection = window.require('WAWebCollections').Chat;
  const rows = [];
  for (const chat of collection.getModelsArray()) {
    if (!chat) continue;
    const id = window.WWebJS.GetSerialized(chat.id);
    if (typeof id !== 'string') continue;
    const isGroup = /^[1-9]\d*(?:-\d+)?@g\.us$/.test(id);
    const isDirect = /^[1-9]\d*(?::\d+)?@(c\.us|s\.whatsapp\.net|lid)$/.test(id);
    if (!isGroup && !isDirect) continue;
    const title = chat.formattedTitle || chat.name;
    const unread = Number(chat.unreadCount);
    const timestamp = Number(chat.t ?? chat.timestamp);
    rows.push({
      id,
      name: typeof title === 'string' ? title : null,
      type: isGroup ? 'group' : 'direct',
      isGroup,
      archived: Boolean(chat.archive ?? chat.archived),
      unreadCount: Number.isFinite(unread) ? Math.max(0, Math.floor(unread)) : 0,
      timestamp: Number.isFinite(timestamp) && timestamp > 0 ? Math.floor(timestamp) : null,
    });
  }
  rows.sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0);
  return rows.slice(offset, offset + limit);
}

function sha256(text) {
  return crypto.createHash('sha256').update(text).digest('hex');
}

function verifyPinnedSources(engine, controller) {
  if (sha256(engine) !== PINNED_ENGINE_SHA256) {
    throw new Error('Unsupported WAHA engine compiled source; use the pinned 2026.9.2 base digest.');
  }
  if (sha256(controller) !== PINNED_CONTROLLER_SHA256) {
    throw new Error('Unsupported WAHA chats controller compiled source; query pass-through must be reverified.');
  }
  if (!/getChats\(session, pagination\)\s*\{\s*return session\.getChats\(pagination\);\s*\}/.test(controller)) {
    throw new Error('WAHA chats controller does not pass through the metadataOnly query.');
  }
}

function patchEngineSource(source) {
  if (source.split(ENGINE_ANCHOR).length !== 2) {
    throw new Error('Expected exactly one pinned WEBJS getChats patch anchor.');
  }
  const extension = `${ENGINE_ANCHOR}        // GROUPBRIEF_METADATA_ONLY_V1: opt-in, local metadata only.\n` +
    `        if (pagination?.metadataOnly === 'true') {\n` +
    `            return this.whatsapp.pupPage.evaluate(${readChatMetadata.toString()}, {\n` +
    `                limit: pagination.limit, offset: pagination.offset,\n` +
    `            });\n` +
    `        }\n`;
  return source.replace(ENGINE_ANCHOR, extension);
}

function install(root) {
  const enginePath = path.join(root, 'dist/core/engines/webjs/session.webjs.core.js');
  const controllerPath = path.join(root, 'dist/api/chats.controller.js');
  const original = fs.readFileSync(enginePath, 'utf8');
  const controller = fs.readFileSync(controllerPath, 'utf8');
  verifyPinnedSources(original, controller);
  const patched = patchEngineSource(original);
  // Refuse a second installation or a conflicting backup; never overwrite it.
  fs.writeFileSync(`${enginePath}.groupbrief-original`, original, { flag: 'wx' });
  fs.writeFileSync(enginePath, patched);
  process.stdout.write('Installed metadata-only WAHA 2026.9.2 extension.\n');
}

module.exports = {
  ENGINE_ANCHOR,
  PINNED_ENGINE_SHA256,
  PINNED_CONTROLLER_SHA256,
  patchEngineSource,
  readChatMetadata,
  verifyPinnedSources,
};

if (require.main === module) {
  install(process.argv[2] || '/app');
}
