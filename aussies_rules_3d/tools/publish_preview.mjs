import fs from 'node:fs';
import path from 'node:path';
import transport from './preview_transport.cjs';
const file = process.argv[2];
try {
  const id = /^preview-(\d+)\.jpg$/.exec(path.basename(file ?? ''))?.[1];
  if (!id) throw new Error('Supply preview-NNN.jpg');
  const stateFile = path.join(path.dirname(file), `state-${id}.json`);
  if (fs.existsSync(stateFile)) {
    const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    const context = Object.fromEntries(['tick', 'phase', 'mode', 'worldBall', 'ballNdc', 'groundNdc', 'cameraPosition', 'heading', 'velocity', 'clip'].map(key => [key, state[key]]));
    console.log(`::notice title=GAMEPLAY_STATE_${id}::${JSON.stringify(context)}`);
  }
  for (const part of transport.encodePreview(id, fs.readFileSync(file))) console.log(`::notice title=${part.title}::${part.message}`);
} catch (error) {
  console.error(`::error::Preview publication failed: ${error.message}`);
  process.exitCode = 1;
}
