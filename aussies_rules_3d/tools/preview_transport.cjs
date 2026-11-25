const { createHash } = require('node:crypto');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const isJpeg = b => b.length >= 4 && b[0] === 255 && b[1] === 216 && b[b.length - 2] === 255 && b[b.length - 1] === 217;
function encodePreview(id, bytes) {
  if (!/^\d+$/.test(id) || !isJpeg(bytes) || bytes.length > 10000) throw new Error('Invalid JPEG preview or size budget exceeded');
  const data = bytes.toString('base64'), digest = hash(bytes), parts = [];
  const total = Math.ceil(data.length / 2800);
  for (let part = 0; part < total; part++) parts.push({
    title: `GAMEPLAY_PREVIEW_${id}_PART_${part}`,
    message: JSON.stringify({ part, total, sha256: digest, data: data.slice(part * 2800, (part + 1) * 2800) }),
  });
  return parts;
}
function decodePreviews(annotations) {
  const groups = new Map(), errors = [], images = [];
  for (const a of annotations) {
    const m = /^GAMEPLAY_PREVIEW_(\d+)_PART_(\d+)$/.exec(a.title ?? '');
    if (!m) {
      const legacy = /^GAMEPLAY_PREVIEW_(\d+)$/.exec(a.title ?? '');
      if (legacy) errors.push({ id: legacy[1], reason: 'Legacy unchunked preview has no integrity proof and may be truncated' });
      continue;
    }
    if (!groups.has(m[1])) groups.set(m[1], []);
    groups.get(m[1]).push({ index: Number(m[2]), message: a.message });
  }
  for (const [id, rows] of groups) {
    try {
      const chunks = rows.map(r => ({ ...JSON.parse(r.message), index: r.index })).sort((a, b) => a.part - b.part);
      const first = chunks[0];
      if (!Number.isInteger(first.total) || first.total < 1 || first.total > 5 || chunks.length !== first.total || chunks.some((c, i) => c.part !== i || c.index !== i || c.total !== first.total || c.sha256 !== first.sha256 || typeof c.data !== 'string')) throw new Error('Missing, duplicated or mismatched chunks');
      const bytes = Buffer.from(chunks.map(c => c.data).join(''), 'base64');
      if (!isJpeg(bytes) || bytes.length > 10000 || hash(bytes) !== first.sha256) throw new Error('JPEG integrity check failed');
      images.push({ id, bytes });
    } catch (err) { errors.push({ id, reason: err.message }); }
  }
  return { images, errors };
}
module.exports = { encodePreview, decodePreviews };
