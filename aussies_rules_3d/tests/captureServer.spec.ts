import { it, expect } from 'vitest';
import { createRequire } from 'node:module';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { Server } from 'node:http';
import type { AddressInfo } from 'node:net';
const require = createRequire(import.meta.url);
const { createCaptureServer } = require('../tools/capture_server.cjs') as { createCaptureServer(root: string): Server };

it('serves the production page and fetchable model/JSON over a real HTTP origin', async () => {
  const root = mkdtempSync(join(tmpdir(), 'capture-http-'));
  writeFileSync(join(root, 'index.html'), '<html>game</html>');
  writeFileSync(join(root, 'motion.json'), '{"clips":32}');
  writeFileSync(join(root, 'player.glb'), 'glTF');
  const server = createCaptureServer(root);
  try {
    await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
    const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    expect(await (await fetch(`${url}/?ab=1`)).text()).toContain('game');
    expect(await (await fetch(`${url}/motion.json`)).json()).toEqual({ clips: 32 });
    const model = await fetch(`${url}/player.glb`);
    expect(model.headers.get('content-type')).toBe('model/gltf-binary');
    expect(await model.text()).toBe('glTF');
    expect((await fetch(`${url}/missing.glb`)).status).toBe(404);
    expect((await fetch(`${url}/%ZZ`)).status).toBe(400);
  } finally {
    await new Promise<void>((resolve, reject) => server.close(err => err ? reject(err) : resolve()));
    rmSync(root, { recursive: true, force: true });
  }
});
