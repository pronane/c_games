// Practice history and the speed trainer: pure functions, plus browser storage for history.

/** One reviewed take. */
export type ProgressEntry = {
  at: number; // ms since epoch
  from: number; // first bar
  to: number; // last bar
  speed: number; // 0.5..1
  score: number | null; // overall %
  against: string; // "tab: Acoustic guitar" or "transcription"
};

/** A song's key in history: its name and length, so a re-upload of the same song is found again. */
export function songKey(name: string, seconds: number) {
  return `${name.replace(/\.[^.]+$/, "").trim().toLowerCase()}|${Math.round(seconds)}`;
}

export function addEntry(history: ProgressEntry[], entry: ProgressEntry, limit = 300) {
  return [...history, entry].slice(-limit);
}

export type RangeProgress = {
  from: number;
  to: number;
  takes: number;
  best: number | null;
  /** Best score at full speed. */
  bestFull: number | null;
  /** Fastest speed with a score at or above `pass`. */
  fastestPass: number | null;
  last: ProgressEntry;
  /** Scores in order, oldest first (for a sparkline). */
  scores: (number | null)[];
};

/** Per bar range: how many takes, best score, best at full speed, fastest clean speed. */
export function summarise(history: ProgressEntry[], pass = 85): RangeProgress[] {
  const groups = new Map<string, ProgressEntry[]>();
  for (const e of history) {
    const k = `${e.from}-${e.to}`;
    groups.set(k, [...(groups.get(k) ?? []), e]);
  }
  const max = (xs: (number | null)[]) => {
    const v = xs.filter((x): x is number => x != null);
    return v.length ? Math.max(...v) : null;
  };
  return [...groups.values()]
    .map((es) => ({
      from: es[0].from,
      to: es[0].to,
      takes: es.length,
      best: max(es.map((e) => e.score)),
      bestFull: max(es.filter((e) => e.speed >= 0.999).map((e) => e.score)),
      fastestPass: max(es.filter((e) => e.score != null && e.score >= pass).map((e) => e.speed)),
      last: es[es.length - 1],
      scores: es.map((e) => e.score),
    }))
    .sort((a, b) => b.last.at - a.last.at);
}

// ------------------------------------------------------------------ speed trainer
export type Trainer = { on: boolean; start: number; step: number; pass: number; top: number };
export const DEFAULT_TRAINER: Trainer = { on: false, start: 0.6, step: 0.05, pass: 85, top: 1 };

/** The speed for the next attempt: up a step after a pass, the same after a miss. */
export function nextSpeed(trainer: Trainer, speed: number, score: number | null) {
  const passed = score != null && score >= trainer.pass;
  const next = passed ? speed + trainer.step : speed;
  return Math.round(Math.min(trainer.top, Math.max(0.25, next)) * 100) / 100;
}

/** Whether the trainer has reached its goal: passed at its top speed. */
export function trainerDone(trainer: Trainer, speed: number, score: number | null) {
  return score != null && score >= trainer.pass && speed >= trainer.top - 1e-6;
}

// ------------------------------------------------------------------ storage
const KEY = "guitar-lab.progress";
type Store = Record<string, ProgressEntry[]>;

function read(): Store {
  try {
    return JSON.parse(localStorage.getItem(KEY) || "{}") as Store;
  } catch {
    return {};
  }
}

export function loadProgress(song: string): ProgressEntry[] {
  return read()[song] ?? [];
}

export function saveProgress(song: string, history: ProgressEntry[]) {
  try {
    const all = read();
    all[song] = history;
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {}
}

export function clearProgress(song: string) {
  saveProgress(song, []);
}
