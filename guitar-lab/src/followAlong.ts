import type { BoardNote } from "./Fretboard";

export type ChordSpan = { chord: string; start: number; end: number };
export type TakeMark = {
  take_time?: number | null;
  take_midi?: number | null;
  target_midi?: number | null;
  target_string?: number | null;
  target_fret?: number | null;
  target_duration?: number | null;
};

/** The chord sounding at `time` and the next different one. */
export function chordAt(chords: ChordSpan[], time: number) {
  const real = chords.filter((c) => c.chord !== "N");
  const i = real.findIndex((c) => time >= c.start && time < c.end);
  const now = i >= 0 ? real[i] : null;
  const after = real.filter((c) => c.start >= (now ? now.end : time) && c.chord !== now?.chord);
  return { now, next: after[0] ?? null };
}

/** The chords a song uses, most-played first. */
export function songChords(chords: ChordSpan[]) {
  const time = new Map<string, number>();
  for (const c of chords) if (c.chord !== "N") time.set(c.chord, (time.get(c.chord) ?? 0) + c.end - c.start);
  return [...time.entries()].sort((a, b) => b[1] - a[1]).map(([name]) => name);
}

/**
 * The notes you played, moved from the take's clock onto the song's: the take was recorded
 * from `start` with the song at `speed`. A note at the pitch the target asked for is drawn
 * where the target is fretted.
 */
export function takeOnSong(marks: TakeMark[], start: number, speed: number): BoardNote[] {
  return marks
    .filter((m) => m.take_time != null && m.take_midi != null)
    .map((m) => {
      const same = m.take_midi === m.target_midi;
      return {
        time: start + m.take_time! * speed,
        duration: Math.max(0.15, (m.target_duration ?? 0.25) * speed),
        midi: m.take_midi!,
        string: same ? m.target_string ?? null : null,
        fret: same ? m.target_fret ?? null : null,
      };
    });
}
