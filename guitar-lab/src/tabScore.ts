// Uploaded tab / notation -> timed notes the app can play, show and compare against.
// Reads alphaTab's score model (Guitar Pro 3-7, MusicXML, alphaTex). No DOM, no audio output.
import { midi as atMidi, type model } from "@coderline/alphatab";
import { applySound, type GuitarSound } from "./guitarTone";

type Score = model.Score;

export type TabNote = {
  time: number;
  duration: number;
  midi: number;
  /** Tab convention: 1 = highest string. Null for instruments without strings. */
  string: number | null;
  fret: number | null;
  bar: number;
  /** How the note is played, for the app's own playback. */
  palmMute?: boolean;
  letRing?: boolean;
  /** Pitch bend as [fraction of the note, semitones] points. */
  bend?: [number, number][];
};
export type TabTrack = { index: number; name: string; strings: number; percussion: boolean };
export type TabPiece = {
  title: string;
  artist: string;
  track: number;
  tracks: TabTrack[];
  notes: TabNote[];
  bars: { number: number; time: number; written?: number }[];
  /** Beat times (quarter notes) for a click track. */
  beats: number[];
  bpm: number;
  /** Open strings from the highest to the lowest, as written in the file. */
  tuning: number[];
  capo: number;
  duration: number;
  warnings: string[];
  /** General MIDI program of the track (29 overdriven, 30 distortion guitar...). */
  program?: number;
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

/**
 * The order bars are played in (repeats, alternate endings and jumps expanded, as a Guitar Pro
 * player does) with the tick each one starts at, and a tick -> seconds map with tempo changes.
 */
export function playbackOrder(score: Score) {
  const generator = new atMidi.MidiFileGenerator(score, null, new atMidi.AlphaSynthMidiFileHandler(new atMidi.MidiFile()));
  generator.generate();
  const played = generator.tickLookup.masterBars.map((m) => ({ index: m.masterBar.index, start: m.start, end: m.end }));
  const changes: { tick: number; bpm: number }[] = [];
  for (const m of generator.tickLookup.masterBars)
    for (const t of m.tempoChanges)
      if (!changes.length || changes[changes.length - 1].bpm !== t.tempo || t.tick < changes[changes.length - 1].tick)
        changes.push({ tick: t.tick, bpm: t.tempo });
  if (!changes.length || changes[0].tick > 0) changes.unshift({ tick: 0, bpm: score.tempo || 120 });
  changes.sort((x, y) => x.tick - y.tick);
  const marks: { tick: number; seconds: number; bpm: number }[] = [];
  let seconds = 0,
    last = changes[0];
  for (const c of changes) {
    seconds += ((c.tick - last.tick) / TICKS_PER_QUARTER) * (60 / last.bpm);
    marks.push({ tick: c.tick, seconds, bpm: c.bpm });
    last = c;
  }
  const toSeconds = (tick: number) => {
    let lo = 0,
      hi = marks.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (marks[mid].tick <= tick) lo = mid;
      else hi = mid - 1;
    }
    const m = marks[lo];
    return m.seconds + ((tick - m.tick) / TICKS_PER_QUARTER) * (60 / m.bpm);
  };
  return { played, toSeconds };
}

export function scoreToPiece(score: Score, track = 0): TabPiece {
  const t = score.tracks[track];
  if (!t) throw Error("That track is not in the file.");
  const staff = t.staves[0];
  const tuning = staff.tuning.length ? [...staff.tuning] : [];
  const { played, toSeconds: seconds } = playbackOrder(score);
  const warnings: string[] = [];
  const notes: TabNote[] = [];
  const ringing = new Map<number, TabNote>(); // string -> last note, for ties
  let skipped = 0;
  played.forEach((pb, n_th) => {
    const bar = staff.bars[pb.index];
    if (!bar) return;
    for (const voice of bar.voices)
      for (const beat of voice.beats) {
        if (beat.isRest) continue;
        const start = pb.start + beat.playbackStart,
          end = start + beat.playbackDuration;
        for (const n of beat.notes) {
          if (n.isDead || n.isPercussion) {
            if (n_th === 0 || !played.slice(0, n_th).some((x) => x.index === pb.index)) skipped++;
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
            bar: n_th + 1,
          };
          if (n.isPalmMute) note.palmMute = true;
          if (n.isLetRing) note.letRing = true;
          // Bend points: offset 0-60 along the note, value in quarter tones.
          if (n.hasBend && n.bendPoints?.length)
            note.bend = n.bendPoints.map((b) => [b.offset / 60, b.value / 2] as [number, number]);
          notes.push(note);
          ringing.set(n.string, note);
        }
      }
  });
  notes.sort((a, b) => a.time - b.time || a.midi - b.midi);
  const bars = played.map((pb, i) => ({ number: i + 1, time: seconds(pb.start), written: pb.index + 1 }));
  const endTick = played.length ? played[played.length - 1].end : 0;
  const beats: number[] = [];
  for (let tick = 0; tick < endTick; tick += TICKS_PER_QUARTER) beats.push(seconds(tick));
  if (played.some((pb, i) => pb.index !== i))
    warnings.push(
      `Repeats are played out as written: ${played.length} bars in playing order (${score.masterBars.length} written). Bar numbers count the bars as played.`,
    );
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
    program: t.playbackInfo?.program ?? 25,
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
 * be heard and played along with. Pitch is exact; palm mutes, let-ring and bends are played
 * when the notes carry them, and `sound` puts the guitar through an amp and pedals.
 */
export function synthesize(
  notes: { time: number; duration: number; midi: number; palmMute?: boolean; letRing?: boolean; bend?: [number, number][] }[],
  rate: number,
  length: number,
  speed = 1,
  level = 0.3,
  sound?: GuitarSound,
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
      held = n.duration / speed,
      ring = n.palmMute ? Math.min(0.25, held + 0.05) : Math.min(n.letRing ? 6 : 4, Math.max(0.15, held + (n.letRing ? 1.5 : 0.15))),
      total = Math.min(out.length - start, Math.round(ring * rate));
    if (start >= out.length || total <= 0) continue;
    const bendMax = n.bend ? Math.max(0, ...n.bend.map((b) => b[1])) : 0,
      y = new Float32Array(Math.ceil(total * 2 ** (bendMax / 12)) + N + 4);
    // Pluck: a lightly low-passed noise burst fills the string (darker when palm muted).
    let prev = 0;
    const pick = n.palmMute ? 0.85 : 0.6;
    for (let i = 0; i <= N + 1; i++) {
      prev = pick * prev + (1 - pick) * noise();
      y[i] = prev;
    }
    // Low strings ring longer than high ones; a palm on the strings kills them quickly.
    const loss = n.palmMute ? 0.985 : Math.min(0.9995, 0.9985 - 0.0000012 * hz);
    let apX = 0,
      apY = 0;
    for (let i = N + 1; i < y.length; i++) {
      const v = loss * 0.5 * (y[i - N] + y[i - N - 1]),
        a = C * v + apX - C * apY;
      apX = v;
      apY = a;
      y[i] = a;
    }
    const release = Math.round(held * rate),
      gain = level * (n.palmMute ? 1.3 : 1);
    // A bend reads the string faster as it is pushed up: pitch follows the bend curve.
    const bend = n.bend && n.bend.length > 1 ? n.bend : null;
    let pos = 0;
    for (let i = 0; i < total; i++) {
      const damp = !n.letRing && i > release ? Math.exp(-(i - release) / (0.04 * rate)) : 1,
        fadeIn = Math.min(1, i / 32);
      let v: number;
      if (bend) {
        const f = Math.min(1, i / Math.max(1, release));
        let k = 0;
        while (k < bend.length - 2 && bend[k + 1][0] < f) k++;
        const [f0, s0] = bend[k],
          [f1, s1] = bend[k + 1],
          semis = f1 > f0 ? s0 + ((s1 - s0) * Math.min(1, Math.max(0, (f - f0) / (f1 - f0)))) : s1,
          j = Math.floor(pos),
          frac = pos - j;
        v = j + 1 < y.length ? y[j] * (1 - frac) + y[j + 1] * frac : 0;
        pos += 2 ** (semis / 12);
      } else v = y[i];
      out[start + i] += v * gain * damp * fadeIn;
    }
  }
  if (sound) applySound(out, rate, sound);
  return out;
}
