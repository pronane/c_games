// Uploaded tab / notation -> timed notes the app can play, show and compare against.
// Reads alphaTab's score model (Guitar Pro 3-7, MusicXML, alphaTex). Pure: no DOM, no audio.
import type { model } from "@coderline/alphatab";

type Score = model.Score;

export type TabNote = {
  time: number;
  duration: number;
  midi: number;
  /** Tab convention: 1 = highest string. Null for instruments without strings. */
  string: number | null;
  fret: number | null;
  bar: number;
};
export type TabTrack = { index: number; name: string; strings: number; percussion: boolean };
export type TabPiece = {
  title: string;
  artist: string;
  track: number;
  tracks: TabTrack[];
  notes: TabNote[];
  bars: { number: number; time: number }[];
  /** Beat times (quarter notes) for a click track. */
  beats: number[];
  bpm: number;
  /** Open strings from the highest to the lowest, as written in the file. */
  tuning: number[];
  capo: number;
  duration: number;
  warnings: string[];
};

const TICKS_PER_QUARTER = 960;

export function listTracks(score: Score): TabTrack[] {
  return score.tracks.map((t, index) => ({
    index,
    name: t.name || `Track ${index + 1}`,
    strings: t.staves[0]?.tuning.length ?? 0,
    percussion: !!t.staves[0]?.isPercussion,
  }));
}

/** Best track for an instrument: first non-drum track with the right number of strings. */
export function pickTrack(score: Score, strings: number) {
  const tracks = listTracks(score);
  return (
    tracks.find((t) => !t.percussion && t.strings === strings) ??
    tracks.find((t) => !t.percussion) ??
    tracks[0]
  ).index;
}

/** Seconds at a tick, from the score's tempo changes (written order; repeats not expanded). */
function tempoMap(score: Score) {
  const changes: { tick: number; bpm: number }[] = [{ tick: 0, bpm: score.tempo || 120 }];
  for (const mb of score.masterBars) {
    const length = (mb.timeSignatureNumerator * 4 * TICKS_PER_QUARTER) / mb.timeSignatureDenominator;
    for (const a of mb.tempoAutomations ?? [])
      changes.push({ tick: mb.start + a.ratioPosition * length, bpm: a.value });
  }
  changes.sort((x, y) => x.tick - y.tick);
  const marks: { tick: number; seconds: number; bpm: number }[] = [];
  let seconds = 0,
    last = changes[0];
  for (const c of changes) {
    seconds += ((c.tick - last.tick) / TICKS_PER_QUARTER) * (60 / last.bpm);
    marks.push({ tick: c.tick, seconds, bpm: c.bpm });
    last = c;
  }
  return (tick: number) => {
    let m = marks[0];
    for (const x of marks) if (x.tick <= tick) m = x;
    return m.seconds + ((tick - m.tick) / TICKS_PER_QUARTER) * (60 / m.bpm);
  };
}

export function scoreToPiece(score: Score, track = 0): TabPiece {
  const t = score.tracks[track];
  if (!t) throw Error("That track is not in the file.");
  const staff = t.staves[0];
  const tuning = staff.tuning.length ? [...staff.tuning] : [];
  const seconds = tempoMap(score);
  const warnings: string[] = [];
  const notes: TabNote[] = [];
  const ringing = new Map<number, TabNote>(); // string -> last note, for ties
  let repeats = false,
    skipped = 0;
  for (const bar of staff.bars) {
    const mb = score.masterBars[bar.index];
    if (mb.isRepeatStart || mb.repeatCount > 0) repeats = true;
    for (const voice of bar.voices)
      for (const beat of voice.beats) {
        if (beat.isRest) continue;
        const start = mb.start + beat.playbackStart,
          end = start + beat.playbackDuration;
        for (const n of beat.notes) {
          if (n.isDead || n.isPercussion) {
            skipped++;
            continue;
          }
          const s = tuning.length ? tuning.length - n.string + 1 : null;
          if (n.isTieDestination) {
            const prev = ringing.get(n.string);
            if (prev) {
              prev.duration = seconds(end) - prev.time;
              continue;
            }
          }
          const note: TabNote = {
            time: seconds(start),
            duration: Math.max(0.03, seconds(end) - seconds(start)),
            midi: n.realValueWithoutHarmonic,
            string: s,
            fret: tuning.length ? n.fret : null,
            bar: bar.index + 1,
          };
          notes.push(note);
          ringing.set(n.string, note);
        }
      }
  }
  notes.sort((a, b) => a.time - b.time || a.midi - b.midi);
  const bars = score.masterBars.map((mb) => ({ number: mb.index + 1, time: seconds(mb.start) }));
  const last = score.masterBars[score.masterBars.length - 1];
  const endTick = last
    ? last.start + (last.timeSignatureNumerator * 4 * TICKS_PER_QUARTER) / last.timeSignatureDenominator
    : 0;
  const beats: number[] = [];
  for (let tick = 0; tick < endTick; tick += TICKS_PER_QUARTER) beats.push(seconds(tick));
  if (repeats) warnings.push("Repeats are played once, in written order.");
  if (skipped) warnings.push(`${skipped} dead or percussive notes are shown but not checked.`);
  if (!notes.length) warnings.push("This track has no pitched notes.");
  return {
    title: score.title || "Untitled",
    artist: score.artist || "",
    track,
    tracks: listTracks(score),
    notes,
    bars,
    beats,
    bpm: score.tempo || 120,
    tuning,
    capo: staff.capo || 0,
    duration: seconds(endTick),
    warnings,
  };
}

/** Name of a catalogue tuning whose strings match the file's, if any. */
export function matchTuning(tuning: number[], tunings: Record<string, number[]>) {
  return (
    Object.entries(tunings).find(
      ([, strings]) => strings.length === tuning.length && strings.every((m, i) => m === tuning[i]),
    )?.[0] ?? null
  );
}

/** Notes and bars inside [from, to), shifted to start at 0 and slowed to `speed`. */
export function excerpt(piece: Pick<TabPiece, "notes" | "bars">, from: number, to: number, speed = 1) {
  const notes = piece.notes
    .filter((n) => n.time >= from - 1e-6 && n.time < to)
    .map((n) => ({
      ...n,
      time: (n.time - from) / speed,
      duration: Math.min(n.duration, to - n.time) / speed,
    }));
  const bars = piece.bars
    .filter((b) => b.time >= from - 1e-6 && b.time < to)
    .map((b) => ({ number: b.number, time: (b.time - from) / speed }));
  return { notes, bars };
}

// ---------------------------------------------------------------- the app's own rendition

/**
 * Plucked-string synthesis (Karplus-Strong) of a note list, at `speed` (0.5-1), so the tab can
 * be heard and played along with. Pitch is exact; tone is a generic clean guitar.
 */
export function synthesize(
  notes: { time: number; duration: number; midi: number }[],
  rate: number,
  length: number,
  speed = 1,
  level = 0.3,
) {
  const out = new Float32Array(Math.max(1, Math.ceil(length * rate)));
  let seed = 12345;
  const noise = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff) * 2 - 1;
  for (const n of notes) {
    const hz = 440 * 2 ** ((n.midi - 69) / 12),
      period = rate / hz,
      // Loop delay = N samples + 0.5 (two-point average) + d (all-pass) = one period.
      N = Math.max(2, Math.floor(period - 0.5)),
      d = period - 0.5 - N,
      C = (1 - d) / (1 + d),
      start = Math.round((n.time / speed) * rate),
      ring = Math.min(4, Math.max(0.15, n.duration / speed + 0.15)),
      total = Math.min(out.length - start, Math.round(ring * rate));
    if (start >= out.length || total <= 0) continue;
    const y = new Float32Array(total + N + 2);
    // Pluck: a lightly low-passed noise burst fills the string.
    let prev = 0;
    for (let i = 0; i <= N + 1; i++) {
      prev = 0.6 * prev + 0.4 * noise();
      y[i] = prev;
    }
    // Low strings ring longer than high ones.
    const loss = Math.min(0.9995, 0.9985 - 0.0000012 * hz);
    let apX = 0,
      apY = 0;
    for (let i = N + 1; i < y.length; i++) {
      const v = loss * 0.5 * (y[i - N] + y[i - N - 1]),
        a = C * v + apX - C * apY;
      apX = v;
      apY = a;
      y[i] = a;
    }
    const release = Math.round((n.duration / speed) * rate);
    for (let i = 0; i < total; i++) {
      const damp = i > release ? Math.exp(-(i - release) / (0.04 * rate)) : 1,
        fadeIn = Math.min(1, i / 32);
      out[start + i] += y[i] * level * damp * fadeIn;
    }
  }
  return out;
}
