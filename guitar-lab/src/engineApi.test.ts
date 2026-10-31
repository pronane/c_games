import { test } from "node:test";
import assert from "node:assert/strict";
import { encodeWav } from "./engineApi";
test("WAV encoder writes interleaved PCM with valid sizes and clipping", async () => {
  const blob = encodeWav(
    [new Float32Array([0, 1, -2]), new Float32Array([0.5, -0.5, 0])],
    44100,
  );
  const bytes = await blob.arrayBuffer(),
    v = new DataView(bytes);
  assert.equal(bytes.byteLength, 56);
  assert.equal(v.getUint16(22, true), 2);
  assert.equal(v.getUint32(24, true), 44100);
  assert.equal(v.getUint32(40, true), 12);
  assert.equal(v.getInt16(48, true), 32767);
  assert.equal(v.getInt16(52, true), -32768);
});
