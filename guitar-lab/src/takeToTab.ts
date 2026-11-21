// Your take to tab: put the notes heard in a riff on a bar grid, and write plain-text tab.

export type HeardNote = { time: number; duration: number; midi: number };
export type FrettedNote = HeardNote & { string?: number | null; fret?: number | null };

/** Move notes so bar 1, beat 1 is at 0 s. Notes a little before it (a pickup played early) are kept at 0. */
export function onGrid(notes: HeardNote[], firstBeat: number, slack = 0.08): HeardNote[] {
  return notes
    .filter((n) => n.time >= firstBeat - slack)
    .map((n) => ({ time: Math.max(0, +(n.time - firstBeat).toFixed(4)), duration: Math.max(0.03, n.duration), midi: n.midi }));
}

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];

/** String labels, top line first (string 1 = highest); the top E is written lower-case as tabs do. */
export function stringLabels(openStrings: number[]) {
  const high = [...openStrings].reverse().map((m) => NAMES[m % 12]);
  if (high.length > 1 && high[0] === high[high.length - 1]) high[0] = high[0].toLowerCase();
  const width = Math.max(...high.map((h) => h.length));
  return high.map((h) => h.padEnd(width));
}

/**
 * Plain-text tab on a 16th-note grid: `bpm` quarter-note beats, `beatsPerBar` to the bar,
 * `barsPerLine` bars to a line. Notes without a string and fret are left out.
 */
export function tabText(notes: FrettedNote[], bpm: number, openStrings: number[], beatsPerBar = 4, barsPerLine = 4) {
  const strings = openStrings.length;
  const sixteenth = 60 / bpm / 4,
    perBar = beatsPerBar * 4;
  const slots = new Map<number, Map<number, number>>();
  let last = 0;
  for (const n of notes) {
    if (!n.string || n.fret == null || n.string > strings) continue;
    const at = Math.max(0, Math.round(n.time / sixteenth));
    last = Math.max(last, at);
    const column = slots.get(at) ?? new Map<number, number>();
    if (!column.has(n.string)) column.set(n.string, n.fret);
    slots.set(at, column);
  }
  if (!slots.size) return "";
  const bars = Math.floor(last / perBar) + 1,
    labels = stringLabels(openStrings),
    lines: string[] = [];
  for (let first = 0; first < bars; first += barsPerLine) {
    const rows = labels.map((l) => l + "|");
    for (let bar = first; bar < Math.min(bars, first + barsPerLine); bar++) {
      for (let k = 0; k < perBar; k++) {
        const column = slots.get(bar * perBar + k),
          width = column ? Math.max(...[...column.values()].map((f) => String(f).length)) : 1;
        for (let s = 1; s <= strings; s++) {
          const fret = column?.get(s);
          rows[s - 1] += (fret == null ? "-".repeat(width) : String(fret).padEnd(width, "-")) + "-";
        }
      }
      for (let s = 0; s < strings; s++) rows[s] += "|";
    }
    lines.push(rows.join("\n"));
  }
  return lines.join("\n\n") + "\n";
}
