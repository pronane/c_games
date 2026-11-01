// Pure helpers for the learn-a-song mixer and play-along recorder.

export type BarRole = {
  bar: number;
  start: number;
  end: number;
  role: "lead" | "rhythm" | "mixed" | "rest";
  /** The part only carries leakage from another part in this bar. */
  bleed?: boolean;
};

/** Attack envelope: positive energy change per 10 ms frame, normalised. */
export function onsetEnvelope(samples: Float32Array, rate: number) {
  const hop = Math.max(1, Math.round(rate / 100)),
    frames = Math.floor(samples.length / hop),
    env = new Float32Array(frames);
  let previous = 0;
  for (let f = 0; f < frames; f++) {
    let e = 0;
    for (let i = f * hop; i < (f + 1) * hop; i++) e += samples[i] * samples[i];
    const level = Math.log1p(1000 * Math.sqrt(e / hop));
    env[f] = Math.max(0, level - previous);
    previous = level;
  }
  let mean = 0;
  for (const v of env) mean += v;
  mean /= Math.max(1, frames);
  for (let f = 0; f < frames; f++) env[f] -= mean;
  return env;
}

/**
 * How late the take is relative to the reference part (seconds, positive = late), found by
 * cross-correlating attack envelopes within ±maxLag. Returns null when the match is weak,
 * e.g. the player played something else or the take is mostly silence.
 */
export function estimateOffset(
  reference: Float32Array,
  take: Float32Array,
  rate: number,
  maxLag = 0.5,
): { seconds: number; strength: number } | null {
  const a = onsetEnvelope(reference, rate),
    b = onsetEnvelope(take, rate),
    n = Math.min(a.length, b.length),
    lagMax = Math.min(Math.round(maxLag * 100), n - 1);
  if (n < 50) return null;
  let norm = 0,
    normA = 0,
    normB = 0;
  for (let i = 0; i < n; i++) {
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  norm = Math.sqrt(normA * normB);
  if (!norm) return null;
  let best = -Infinity,
    bestLag = 0;
  for (let lag = -lagMax; lag <= lagMax; lag++) {
    let s = 0;
    for (let i = Math.max(0, -lag); i < n && i + lag < n; i++)
      s += a[i] * b[i + lag];
    if (s > best) {
      best = s;
      bestLag = lag;
    }
  }
  const strength = best / norm;
  return strength < 0.2 ? null : { seconds: bestLag / 100, strength };
}

/** Gain automation for one part: silent during the given bar roles, with short ramps. */
export function muteSchedule(
  roles: BarRole[],
  mutedRoles: BarRole["role"][],
  ramp = 0.03,
): { time: number; gain: number }[] {
  return scheduleFor(roles, (bar) => mutedRoles.includes(bar.role), ramp);
}

/** Gain at a time from a schedule (for starting playback mid-song). */
export function gainAt(points: { time: number; gain: number }[], t: number) {
  let g = points[0]?.gain ?? 1;
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    if (p.time > t) {
      const prev = points[i - 1];
      if (prev && p.time > prev.time)
        return prev.gain + ((p.gain - prev.gain) * (t - prev.time)) / (p.time - prev.time);
      return g;
    }
    g = p.gain;
  }
  return g;
}

/** Bars to seconds for a loop, clamped to the song. */
export function loopRange(
  bars: number[],
  fromBar: number,
  toBar: number,
  duration: number,
) {
  const start = Math.max(0, bars[Math.max(0, fromBar - 1)] ?? 0),
    end = Math.min(duration, bars[toBar] ?? duration);
  return { start, end: Math.max(start + 0.5, end) };
}

/** Mix mono/stereo channel data with gains into stereo, clipping safely. */
export function mixInto(
  out: [Float32Array, Float32Array],
  channels: Float32Array[],
  gain: number,
  offsetFrames = 0,
) {
  const [l, r] = out,
    left = channels[0],
    right = channels[1] ?? channels[0];
  for (let i = 0; i < left.length; i++) {
    const j = i + offsetFrames;
    if (j < 0 || j >= l.length) continue;
    l[j] += left[i] * gain;
    r[j] += right[i] * gain;
  }
}

// ---------------------------------------------------------------- what the player replaces

export type PartInfo = {
  id: string;
  label: string;
  role: string;
  roles: BarRole[];
};
export type TargetRole = "any" | "lead" | "rhythm";
/** The music the player takes over: whole parts, or only their lead / rhythm bars. */
export type Target = {
  id: string;
  label: string;
  detail: string;
  parts: string[];
  role: TargetRole;
};

const MUTED_FOR: Record<TargetRole, BarRole["role"][]> = {
  any: ["lead", "rhythm", "mixed", "rest"],
  // Mixed bars hold some lead playing; leaving them in would double the player's line.
  lead: ["lead", "mixed"],
  rhythm: ["rhythm"],
};

/** "5–8, 11–14" from bar numbers. */
export function barRanges(bars: number[]) {
  const sorted = [...new Set(bars)].sort((a, b) => a - b),
    out: string[] = [];
  for (let i = 0; i < sorted.length; ) {
    let j = i;
    while (j + 1 < sorted.length && sorted[j + 1] === sorted[j] + 1) j++;
    out.push(i === j ? `${sorted[i]}` : `${sorted[i]}–${sorted[j]}`);
    i = j + 1;
  }
  return out.join(", ");
}

const barsWith = (part: PartInfo, roles: BarRole["role"][]) =>
  part.roles.filter((r) => roles.includes(r.role)).map((r) => r.bar);

/**
 * Choices for "the part I'm playing", in the order a player would look for them: each
 * audible part, each part's lead or rhythm bars when it plays both, then every lead
 * passage across all parts (two guitars trading solos), every rhythm passage, all parts.
 */
export function buildTargets(parts: PartInfo[], instrument: string): Target[] {
  const audible = parts.filter((p) => p.role !== "silent");
  const name = instrument.toLowerCase();
  const out: Target[] = [];
  for (const p of audible) {
    const lead = barsWith(p, ["lead"]),
      rhythm = barsWith(p, ["rhythm"]);
    out.push({
      id: p.id,
      label: audible.length > 1 ? p.label : `The ${name} part`,
      detail: p.role,
      parts: [p.id],
      role: "any",
    });
    if (lead.length && rhythm.length) {
      out.push({ id: `${p.id}:lead`, label: `${p.label} · lead bars`, detail: `bars ${barRanges(lead)}`, parts: [p.id], role: "lead" });
      out.push({ id: `${p.id}:rhythm`, label: `${p.label} · rhythm bars`, detail: `bars ${barRanges(rhythm)}`, parts: [p.id], role: "rhythm" });
    }
  }
  const leadParts = audible.filter((p) => barsWith(p, ["lead"]).length),
    rhythmParts = audible.filter((p) => barsWith(p, ["rhythm"]).length);
  if (leadParts.length > 1)
    out.push({
      id: "all:lead",
      label: `Every lead passage (any ${name})`,
      detail: `bars ${barRanges(leadParts.flatMap((p) => barsWith(p, ["lead"])))}`,
      parts: leadParts.map((p) => p.id),
      role: "lead",
    });
  if (rhythmParts.length > 1)
    out.push({
      id: "all:rhythm",
      label: `Every rhythm passage (any ${name})`,
      detail: `bars ${barRanges(rhythmParts.flatMap((p) => barsWith(p, ["rhythm"])))}`,
      parts: rhythmParts.map((p) => p.id),
      role: "rhythm",
    });
  if (audible.length > 1)
    out.push({ id: "all", label: `All ${name} parts`, detail: "everything", parts: audible.map((p) => p.id), role: "any" });
  return out;
}

/** Bar numbers the target silences (any of its parts). */
export function targetBars(target: Target, parts: PartInfo[]) {
  const muted = new Set<number>();
  for (const p of parts)
    if (target.parts.includes(p.id))
      for (const r of p.roles) if (MUTED_FOR[target.role].includes(r.role)) muted.add(r.bar);
  return muted;
}

function scheduleFor(roles: BarRole[], silent: (bar: BarRole) => boolean, ramp: number) {
  const points: { time: number; gain: number }[] = [{ time: 0, gain: 1 }];
  let muted = false;
  for (const bar of roles) {
    const should = silent(bar);
    if (should === muted) continue;
    const t = Math.max(0, bar.start);
    points.push({ time: Math.max(0, t - ramp), gain: muted ? 0 : 1 });
    points.push({ time: t, gain: should ? 0 : 1 });
    muted = should;
  }
  return points;
}

/**
 * Gain over time for one part when the player takes over `target`.
 * mode "without": the band minus the target. mode "only": just the target.
 * Other parts' bleed bars that overlap the target are silenced too, so no ghost of the
 * replaced part is left in the backing track. Returns null for "always full volume".
 */
export function targetSchedule(
  target: Target,
  part: PartInfo,
  parts: PartInfo[],
  mode: "without" | "only",
  ramp = 0.03,
): { time: number; gain: number }[] | null {
  const mine = target.parts.includes(part.id);
  const bars = targetBars(target, parts);
  // Any part's bleed in a bar the target silences would leave a ghost of the replaced part.
  const silentWithout = (b: BarRole) =>
    (mine && MUTED_FOR[target.role].includes(b.role)) || (!!b.bleed && bars.has(b.bar));
  if (mode === "without") {
    if (mine && target.role === "any") return [{ time: 0, gain: 0 }];
    const s = scheduleFor(part.roles, silentWithout, ramp);
    return s.length === 1 ? null : s;
  }
  if (!mine) return [{ time: 0, gain: 0 }];
  if (target.role === "any") return null;
  return scheduleFor(part.roles, (b) => !MUTED_FOR[target.role].includes(b.role), ramp);
}

/** Apply a gain schedule to channel data (in place on a copy). */
export function applySchedule(
  channels: Float32Array[],
  rate: number,
  points: { time: number; gain: number }[],
) {
  const step = Math.max(1, Math.round(rate / 100));
  return channels.map((src) => {
    const dst = new Float32Array(src.length);
    for (let i = 0; i < src.length; i += step) {
      const g = gainAt(points, i / rate);
      const end = Math.min(i + step, src.length);
      for (let j = i; j < end; j++) dst[j] = src[j] * g;
    }
    return dst;
  });
}

// ---------------------------------------------------------------- slow down, same pitch

/**
 * Time-stretch without changing pitch (WSOLA: waveform-similarity overlap-add).
 * speed < 1 slows down. All channels use the same splice points so the stereo image holds.
 * Good for practice speeds (50–100%); transients soften slightly at the slowest settings.
 */
export function timeStretch(channels: Float32Array[], rate: number, speed: number): Float32Array[] {
  if (Math.abs(speed - 1) < 1e-3 || !channels.length) return channels.map((c) => c.slice());
  const frame = Math.round(rate * 0.04) & ~1,
    hop = frame / 2,
    search = Math.round(rate * 0.012),
    input = channels[0].length,
    outLength = Math.ceil(input / speed),
    window = new Float32Array(frame);
  for (let i = 0; i < frame; i++) window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / frame);
  const mono = new Float32Array(input);
  for (const c of channels) for (let i = 0; i < input; i++) mono[i] += c[i] / channels.length;
  const out = channels.map(() => new Float32Array(outLength + frame)),
    norm = new Float32Array(outLength + frame);
  let previous = 0; // where the last frame was taken from in the input
  for (let o = 0; o < outLength; o += hop) {
    const nominal = Math.round(o * speed);
    let best = nominal;
    if (o > 0) {
      // Pick the input position near `nominal` whose start best continues the last frame:
      // a coarse pass every 8 samples, then a fine pass around the best coarse match.
      const target = previous + hop,
        lo = Math.max(0, nominal - search),
        hi = Math.min(input - frame, nominal + search);
      const similarity = (cand: number, stride: number) => {
        let score = 0;
        for (let k = 0; k < hop; k += stride) {
          const a = target + k < input ? mono[target + k] : 0;
          score += a * mono[cand + k];
        }
        return score;
      };
      let bestScore = -Infinity;
      for (let cand = lo; cand <= hi; cand += 8) {
        const score = similarity(cand, 16);
        if (score > bestScore) {
          bestScore = score;
          best = cand;
        }
      }
      const centre = best;
      bestScore = -Infinity;
      for (let cand = Math.max(lo, centre - 8); cand <= Math.min(hi, centre + 8); cand++) {
        const score = similarity(cand, 4);
        if (score > bestScore) {
          bestScore = score;
          best = cand;
        }
      }
    }
    if (best + frame > input) best = Math.max(0, input - frame);
    for (let c = 0; c < channels.length; c++) {
      const src = channels[c],
        dst = out[c];
      for (let k = 0; k < frame; k++) dst[o + k] += src[best + k] * window[k];
    }
    for (let k = 0; k < frame; k++) norm[o + k] += window[k];
    previous = best;
  }
  return out.map((dst) => {
    const r = new Float32Array(outLength);
    for (let i = 0; i < outLength; i++) r[i] = norm[i] > 1e-3 ? dst[i] / norm[i] : 0;
    return r;
  });
}
