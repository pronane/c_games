// Practice helpers: a click track on the song's beat grid, and a one-time measurement of
// how late this device's recordings arrive (so timing feedback is about the player, not the
// hardware). Pure functions; the UI wires them to Web Audio.

export type Click = { time: number; accent: boolean };

/** Clicks for every beat in [from, to). Beat 0 of the grid is bar 1, beat 1. */
export function clickTimes(beats: number[], from: number, to: number): Click[] {
  return beats
    .map((time, i) => ({ time, accent: i % 4 === 0 }))
    .filter((c) => c.time >= from - 1e-6 && c.time < to);
}

/** One click sound: a short decaying tone, higher on beat one. */
export function clickSound(rate: number, accent: boolean) {
  const n = Math.round(rate * 0.03),
    out = new Float32Array(n),
    hz = accent ? 1500 : 1000;
  for (let i = 0; i < n; i++) out[i] = Math.sin((2 * Math.PI * hz * i) / rate) * Math.exp(-i / (rate * 0.006));
  return out;
}

/**
 * Mix clicks into rendered audio that starts at song time `from` and was slowed to `speed`
 * (clicks are added after stretching so they stay crisp).
 */
export function addClicks(
  channels: Float32Array[],
  rate: number,
  clicks: Click[],
  from: number,
  speed = 1,
  level = 0.35,
) {
  const sounds = { true: clickSound(rate, true), false: clickSound(rate, false) };
  for (const c of clicks) {
    const at = Math.round(((c.time - from) / speed) * rate),
      sound = sounds[String(c.accent) as "true" | "false"],
      gain = level * (c.accent ? 1 : 0.7);
    for (const ch of channels)
      for (let i = 0; i < sound.length; i++) {
        const j = at + i;
        if (j >= 0 && j < ch.length) ch[j] += sound[i] * gain;
      }
  }
}

/**
 * For each expected click time, when did the recording first rise sharply? Searches
 * [t - before, t + after]. Returns seconds late (negative = early) or null if nothing clear.
 */
export function detectHits(
  samples: Float32Array,
  rate: number,
  expected: number[],
  before = 0.08,
  after = 0.45,
): (number | null)[] {
  const hop = Math.max(1, Math.round(rate / 1000)), // 1 ms frames
    frames = Math.floor(samples.length / hop),
    level = new Float32Array(frames);
  for (let f = 0; f < frames; f++) {
    let peak = 0;
    for (let i = f * hop; i < (f + 1) * hop; i++) peak = Math.max(peak, Math.abs(samples[i]));
    level[f] = peak;
  }
  return expected.map((t) => {
    const a = Math.max(0, Math.round((t - before) * 1000)),
      b = Math.min(frames, Math.round((t + after) * 1000));
    if (b - a < 10) return null;
    // Noise floor from the quietest part of the window, peak from the loudest.
    const slice = Array.from(level.subarray(a, b)),
      sorted = [...slice].sort((x, y) => x - y),
      floor = sorted[Math.floor(sorted.length * 0.2)],
      peak = sorted[sorted.length - 1];
    if (peak < 0.01 || peak < floor * 4) return null;
    const threshold = floor + (peak - floor) * 0.3;
    const first = slice.findIndex((v) => v >= threshold);
    return first < 0 ? null : (a + first) / 1000 - t;
  });
}

export type LatencyResult = {
  ms: number;
  spreadMs: number;
  used: number;
  ok: boolean;
  method: "speakers" | "play-along";
  measured: string;
};

/** Median offset; needs most clicks found and a tight spread to be trusted. */
export function summariseLatency(
  offsets: (number | null)[],
  method: LatencyResult["method"],
  now = new Date(),
): LatencyResult {
  const found = offsets.filter((o): o is number => o !== null).sort((a, b) => a - b);
  const median = found.length ? found[Math.floor(found.length / 2)] : 0;
  const deviations = found.map((o) => Math.abs(o - median)).sort((a, b) => a - b);
  const spread = deviations.length ? deviations[Math.floor(deviations.length / 2)] : 0;
  // People playing along are looser than a speaker loopback.
  const limit = method === "speakers" ? 0.006 : 0.035;
  return {
    ms: Math.round(median * 1000),
    spreadMs: Math.round(spread * 1000),
    used: found.length,
    ok: found.length >= Math.ceil(offsets.length * 0.6) && spread <= limit && median > -0.05 && median < 0.5,
    method,
    measured: now.toISOString().slice(0, 10),
  };
}

const KEY = "guitar-lab-latency";
/** Saved per browser and input; wrapped because storage can be blocked. */
export function loadLatency(input = "default"): LatencyResult | null {
  try {
    const all = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return all[input] ?? null;
  } catch {
    return null;
  }
}
export function saveLatency(result: LatencyResult, input = "default") {
  try {
    const all = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    all[input] = result;
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {}
}

/** Click times starting at `start`, gaps varying ±40% around `gap` (seeded for tests). */
export function jitteredTimes(start: number, count: number, gap: number, random = Math.random) {
  const out: number[] = [];
  let t = start;
  for (let i = 0; i < count; i++) {
    out.push(t);
    t += gap * (0.6 + 0.8 * random());
  }
  return out;
}
