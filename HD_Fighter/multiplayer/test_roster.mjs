#!/usr/bin/env node
'use strict';

// The Padel Wars trio has to be consistent in four places or the online game
// breaks in a way that is hard to see: the client's select grid, its display
// names, the metadata that lists the sprite sheets, and the relay's allowed
// picks. A pick the relay rejects never reaches the fight, and a pick the client
// shows without sheets draws a silhouette. This test checks all four agree and
// that every sheet the metadata promises exists and slices cleanly.
//
//   node test_roster.mjs

import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const { hdFighter } = require('../../shared/netplay/server/games.js');

const PADEL = ['mike', 'daragh', 'dec'];
const STATES = ['idle', 'walk', 'crouch', 'jump', 'lp', 'hp', 'lk', 'hk',
  'block', 'throw', 'hit', 'special1', 'special2', 'super', 'win', 'lose'];

let failures = 0;
function check(cond, msg) {
  if (cond) return;
  failures += 1;
  console.error('FAIL', msg);
}

const gameJs = readFileSync(join(here, 'public/game.js'), 'utf8');
const rosterSrc = /const FIGHTERS = \[([^\]]*)\]/.exec(gameJs);
check(!!rosterSrc, 'public/game.js has a FIGHTERS roster');
const roster = rosterSrc ? rosterSrc[1].split(',').map((s) => s.trim().replace(/^'|'$/g, '')).filter(Boolean) : [];
const fnameSrc = /const FNAME = \{([\s\S]*?)\n\};/.exec(gameJs);
const fname = fnameSrc ? fnameSrc[1] : '';

for (const id of PADEL) {
  check(roster.includes(id), `select grid offers ${id}`);
  check(new RegExp(`\\b${id}:\\s*'`).test(fname), `FNAME has a label for ${id}`);
  check((hdFighter.picks || []).includes(id), `relay accepts the ${id} pick`);
}

// the original six must stay first, in their original order
const originals = ['kairo', 'lyra', 'naomi', 'brutus', 'void', 'zap'];
check(JSON.stringify(roster.slice(0, 6)) === JSON.stringify(originals), 'the six originals keep their order');
check(roster.length === originals.length + PADEL.length, `roster length is ${originals.length + PADEL.length}`);

for (const base of [join(here, 'public/assets_hd'), join(here, '..', 'assets_hd')]) {
  const metaPath = join(base, 'meta.json');
  check(existsSync(metaPath), `${metaPath} exists`);
  if (!existsSync(metaPath)) continue;
  const meta = JSON.parse(readFileSync(metaPath, 'utf8'));
  for (const id of roster) {
    const entry = meta.characters[id];
    check(!!entry, `${base}: meta.json has sheets for ${id}`);
    if (!entry) continue;
    for (const state of STATES) {
      check(Array.isArray(entry[state]), `${id} has a ${state} sheet`);
    }
    const portrait = meta.select[id];
    check(!!portrait && existsSync(join(base, portrait)), `${id} has a select portrait`);
    for (const [state, [rel, count]] of Object.entries(entry)) {
      const file = join(base, rel);
      check(existsSync(file), `${rel} exists`);
      if (!existsSync(file)) continue;
      // PNG signature (8) + length (4) + 'IHDR' (4) + width (4) + height (4).
      const buf = readFileSync(file);
      const w = buf.readUInt32BE(16);
      const h = buf.readUInt32BE(20);
      check(w % count === 0, `${rel}: width ${w} divides into ${count} frames`);
      check(w / count === 192 && h === 256, `${rel}: ${w / count}x${h} cells are 192x256`);
    }
  }
}

if (failures) {
  console.error(`\n${failures} roster check(s) failed`);
  process.exit(1);
}
console.log('PASS roster', roster.join(' '));
