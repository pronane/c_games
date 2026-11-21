// Guitar chord shapes for chord names, standard tuning: open shapes where the common one is
// open, otherwise the E-shape or A-shape barre that sits lower on the neck.

/** Frets from the low E string (index 0) to the high e (index 5); null = not played. */
export type Shape = { frets: (number | null)[]; barre: number | null; name: string };

const ROOTS: Record<string, number> = {
  C: 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11,
};

export function parseChord(name: string): { root: number; quality: string } | null {
  if (!name || name === "N") return null;
  const root = name.slice(0, 2) in ROOTS ? name.slice(0, 2) : name.slice(0, 1);
  if (!(root in ROOTS)) return null;
  return { root: ROOTS[root], quality: name.slice(root.length) };
}

const x = null;
// Common open shapes, by name.
const OPEN: Record<string, (number | null)[]> = {
  C: [x, 3, 2, 0, 1, 0],
  D: [x, x, 0, 2, 3, 2],
  G: [3, 2, 0, 0, 0, 3],
  Dm: [x, x, 0, 2, 3, 1],
  D7: [x, x, 0, 2, 1, 2],
  G7: [3, 2, 0, 0, 0, 1],
  C7: [x, 3, 2, 3, 1, 0],
  Cmaj7: [x, 3, 2, 0, 0, 0],
  Dmaj7: [x, x, 0, 2, 2, 2],
  Fmaj7: [x, x, 3, 2, 1, 0],
  B7: [x, 2, 1, 2, 0, 2],
  Dm7: [x, x, 0, 2, 1, 1],
  Dsus2: [x, x, 0, 2, 3, 0],
  Dsus4: [x, x, 0, 2, 3, 3],
  Csus2: [x, 3, 0, 0, 1, 3],
  Gsus4: [3, 3, 0, 0, 1, 3],
  D5: [x, x, 0, 2, 3, x],
};
// Movable shapes as offsets from the barre fret; the root is on the low E (E-shape) or A string (A-shape).
const E_SHAPE: Record<string, (number | null)[]> = {
  "": [0, 2, 2, 1, 0, 0],
  m: [0, 2, 2, 0, 0, 0],
  "7": [0, 2, 0, 1, 0, 0],
  m7: [0, 2, 0, 0, 0, 0],
  sus4: [0, 2, 2, 2, 0, 0],
  "5": [0, 2, 2, x, x, x],
};
const A_SHAPE: Record<string, (number | null)[]> = {
  "": [x, 0, 2, 2, 2, 0],
  m: [x, 0, 2, 2, 1, 0],
  "7": [x, 0, 2, 0, 2, 0],
  m7: [x, 0, 2, 0, 1, 0],
  maj7: [x, 0, 2, 1, 2, 0],
  sus2: [x, 0, 2, 2, 0, 0],
  sus4: [x, 0, 2, 2, 3, 0],
  "5": [x, 0, 2, 2, x, x],
};

const shift = (offsets: (number | null)[], by: number) => offsets.map((f) => (f == null ? null : f + by));

export function chordShape(name: string): Shape | null {
  const parsed = parseChord(name);
  if (!parsed) return null;
  if (name in OPEN) return { frets: OPEN[name], barre: null, name };
  const { root, quality } = parsed;
  const options: Shape[] = [];
  if (quality in E_SHAPE) {
    const r = (root - 4 + 12) % 12;
    options.push({ frets: shift(E_SHAPE[quality], r), barre: r || null, name });
  }
  if (quality in A_SHAPE) {
    const r = (root - 9 + 12) % 12;
    options.push({ frets: shift(A_SHAPE[quality], r), barre: r || null, name });
  }
  if (!options.length) return null;
  // Lowest on the neck wins; open (fret 0) shapes first.
  return options.sort((a, b) => (a.barre ?? 0) - (b.barre ?? 0))[0];
}

/** The notes a shape sounds (MIDI), for checking. */
export function shapeNotes(shape: Shape, tuning = [40, 45, 50, 55, 59, 64]) {
  return shape.frets.flatMap((f, i) => (f == null ? [] : [tuning[i] + f]));
}
