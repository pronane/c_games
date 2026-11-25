import { it, expect } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
type Annotation = { title: string; message: string };
const { encodePreview, decodePreviews } = require('../tools/preview_transport.cjs') as {
  encodePreview(id: string, bytes: Buffer): Annotation[];
  decodePreviews(a: Annotation[]): { images: { id: string; bytes: Buffer }[]; errors: { id: string; reason: string }[] };
};
function jpeg() {
  const data = Buffer.alloc(9000, 170);
  data[0] = 255; data[1] = 216; data[data.length - 2] = 255; data[data.length - 1] = 217;
  return data;
}
it('round-trips a preview through 4096-character-limited, out-of-order annotations', () => {
  const input = jpeg();
  const chunks = encodePreview('006', input);
  expect(chunks.length).toBeLessThanOrEqual(5);
  for (const part of chunks) expect(part.message.length).toBeLessThan(4096);
  const result = decodePreviews(chunks.reverse().map(a => ({ ...a, message: a.message.slice(0, 4096) })));
  expect(result.errors).toEqual([]);
  expect(result.images[0].bytes.equals(input)).toBe(true);
});
it('rejects missing, duplicate and truncated chunks rather than showing a grey partial JPEG', () => {
  const parts = encodePreview('000', jpeg());
  for (const bad of [parts.slice(1), [...parts, parts[0]], parts.map((p, i) => i ? p : { ...p, message: p.message.slice(0, 100) })]) {
    expect(decodePreviews(bad).images).toEqual([]);
    expect(decodePreviews(bad).errors).toHaveLength(1);
  }
});
it('rejects changed content even with an intact JPEG envelope', () => {
  const parts = encodePreview('012', jpeg());
  const changed = JSON.parse(parts[0].message);
  changed.data = changed.data.slice(0, 100) + 'AAAA' + changed.data.slice(104);
  parts[0].message = JSON.stringify(changed);
  expect(decodePreviews(parts).images).toEqual([]);
  expect(decodePreviews(parts).errors[0].reason).toContain('integrity');
});
it('refuses legacy unverified annotations and oversize publication', () => {
  expect(decodePreviews([{ title: 'GAMEPLAY_PREVIEW_000', message: jpeg().toString('base64').slice(0, 4096) }]).images).toEqual([]);
  expect(() => encodePreview('000', Buffer.alloc(10001))).toThrow();
});
