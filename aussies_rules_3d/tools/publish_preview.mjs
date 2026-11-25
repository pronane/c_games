import fs from 'node:fs';
import path from 'node:path';
import transport from './preview_transport.cjs';
const file = process.argv[2];
try {
  const id = /^preview-(\d+)\.jpg$/.exec(path.basename(file ?? ''))?.[1];
  if (!id) throw new Error('Supply preview-NNN.jpg');
  for (const part of transport.encodePreview(id, fs.readFileSync(file))) console.log(`::notice title=${part.title}::${part.message}`);
} catch (error) {
  console.error(`::error::Preview publication failed: ${error.message}`);
  process.exitCode = 1;
}
