// Packed inputs and gap detection. A steady packet carries a short tail,
// not every unacked frame. A hole is a NACK, answered immediately.

export const INPUT_KEYS = [
  'left', 'right', 'up', 'down', 'jump',
  'lp', 'hp', 'lk', 'hk', 'block', 'throw',
  'special1', 'special2', 'super',
];
export const TAIL_FRAMES = 32;

export function packInput(inp) {
  let bits = 0;
  for (let i = 0; i < INPUT_KEYS.length; i++) {
    if (inp && inp[INPUT_KEYS[i]]) bits |= 1 << i;
  }
  return bits;
}

export function unpackInput(bits) {
  const inp = {};
  const n = bits | 0;
  for (let i = 0; i < INPUT_KEYS.length; i++) inp[INPUT_KEYS[i]] = !!(n & (1 << i));
  return inp;
}

function rowsAfter(log, ack) {
  const rows = [];
  for (let i = 0; i < log.length; i++) {
    if (log[i] && log[i].frame > ack) rows.push(log[i]);
  }
  return rows;
}

// Contiguous tails use base+bits. A hole in the slice stays sparse so the
// receiver does not treat the gap as neutral inputs.
export function encodeTail(log, ack, limit = TAIL_FRAMES) {
  const rows = rowsAfter(log, ack);
  if (!rows.length) return null;
  let slice = rows;
  if (rows.length > limit) {
    const head = rows.slice(0, Math.max(1, limit - 8));
    const tail = rows.slice(rows.length - 8);
    const seen = new Set();
    slice = [];
    for (const row of head.concat(tail)) {
      if (seen.has(row.frame)) continue;
      seen.add(row.frame);
      slice.push(row);
    }
    slice.sort((a, b) => a.frame - b.frame);
  }
  let contiguous = true;
  for (let i = 1; i < slice.length; i++) {
    if (slice[i].frame !== slice[i - 1].frame + 1) contiguous = false;
  }
  if (contiguous) {
    return { base: slice[0].frame, bits: slice.map((r) => packInput(r.inp)) };
  }
  return { batch: slice.map((r) => ({ frame: r.frame, b: packInput(r.inp) })) };
}

export function encodeFrames(rows) {
  if (!rows || !rows.length) return null;
  const ordered = rows.slice().sort((a, b) => a.frame - b.frame);
  let contiguous = true;
  for (let i = 1; i < ordered.length; i++) {
    if (ordered[i].frame !== ordered[i - 1].frame + 1) contiguous = false;
  }
  if (contiguous) {
    return { base: ordered[0].frame, bits: ordered.map((r) => packInput(r.inp)) };
  }
  return { batch: ordered.map((r) => ({ frame: r.frame, b: packInput(r.inp) })) };
}

export function decodeInputs(m) {
  const out = [];
  if (m && typeof m.base === 'number' && Array.isArray(m.bits)) {
    const base = m.base | 0;
    for (let i = 0; i < m.bits.length; i++) {
      const bits = m.bits[i] | 0;
      out.push({ frame: base + i, bits, inp: unpackInput(bits) });
    }
  }
  if (m && Array.isArray(m.batch)) {
    for (const item of m.batch) {
      if (!item || typeof item.frame !== 'number') continue;
      const bits = typeof item.b === 'number' ? (item.b | 0) : packInput(item.inp);
      out.push({ frame: item.frame | 0, bits, inp: unpackInput(bits) });
    }
  }
  return out;
}

// contig: highest frame N such that every frame 0..N is present. -1 if frame 0 is missing.
export function absorbContig(contig, have) {
  let c = contig;
  while (have.has(c + 1)) c += 1;
  return c;
}

// The first hole strictly before the newest frame we just learned about.
export function gapBefore(contig, frames) {
  if (!frames.length) return null;
  let min = frames[0];
  for (let i = 1; i < frames.length; i++) if (frames[i] < min) min = frames[i];
  if (min > contig + 1) return { from: contig + 1, to: min - 1 };
  return null;
}

export function packHist(list) {
  const bytes = new Uint8Array(list.length * 2);
  for (let i = 0; i < list.length; i++) {
    const v = (list[i] || 0) & 0xffff;
    bytes[i * 2] = v & 0xff;
    bytes[i * 2 + 1] = (v >> 8) & 0xff;
  }
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

export function unpackHist(b64) {
  if (!b64) return [];
  const bin = atob(b64);
  const out = new Array(Math.floor(bin.length / 2));
  for (let i = 0; i < out.length; i++) {
    out[i] = bin.charCodeAt(i * 2) | (bin.charCodeAt(i * 2 + 1) << 8);
  }
  return out;
}
