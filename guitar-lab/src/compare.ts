// What the server's take-vs-target diff looks like, and the bits the screen renders.
// The engine does the alignment; this only turns that result into labels and note chips.

import { note as noteName } from "./analysis";

export type DiffKind =
  | "correct"
  | "wrong_pitch"
  | "wrong_string"
  | "early"
  | "late"
  | "missing"
  | "extra"
  | "wrong_duration";

export type DiffNote = {
  id: number;
  kind: DiffKind | string;
  bar: number;
  beat: number;
  message: string;
  target_midi?: number | null;
  target_string?: number | null;
  target_fret?: number | null;
  take_midi?: number | null;
};

export type DiffBar = {
  bar: number;
  score: number | null;
  messages: string[];
};

export type DiffSummary = {
  pitch_accuracy: number | null;
  timing_accuracy: number | null;
  completeness: number | null;
  overall: number | null;
  speed_ratio?: number | null;
};

export type CompareReport = {
  source: "stem" | "notation" | "file" | string;
  label: string;
  summary: DiffSummary;
  notes: DiffNote[];
  bars: DiffBar[];
  worst_bars: { bar: number; score: number | null; messages: string[] }[];
};

export type Comparison = {
  transcription?: string;
  reports: CompareReport[];
  combined: (DiffSummary & { detail?: string }) | null;
};

export type NoteChip = {
  id: string;
  className: string;
  title: string;
  bar: number;
  text: string;
  pitch: string;
};

/** Last N takes, newest at the end. */
export function rememberTake<T>(history: T[], next: T, limit = 5): T[] {
  return [...history, next].slice(-Math.max(1, limit));
}

export function markClass(kind: string) {
  return `diff-note diff-${kind.replaceAll("_", "-")}`;
}

export function percent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "–";
  return `${Math.round(value * 100)}%`;
}

export function scoreCards(comparison: Comparison) {
  const line = (summary: DiffSummary) =>
    `Pitch ${percent(summary.pitch_accuracy)} · timing ${percent(summary.timing_accuracy)} · completeness ${percent(summary.completeness)}`;
  const cards = comparison.reports.map((report) => ({
    key: report.source,
    label: report.label,
    overall: report.summary.overall == null ? "–" : `${report.summary.overall}%`,
    detail: line(report.summary),
  }));
  if (comparison.combined) {
    cards.push({
      key: "combined",
      label: "Combined",
      overall: comparison.combined.overall == null ? "–" : `${comparison.combined.overall}%`,
      detail: line(comparison.combined),
    });
  }
  return cards;
}

/** The written chart when we have one, otherwise whichever target was scored. */
export function shownReport(comparison: Comparison) {
  return (
    comparison.reports.find((r) => r.source === "notation") ??
    comparison.reports.find((r) => r.source === "file") ??
    comparison.reports[0]
  );
}

export function tempoNote(report: CompareReport) {
  const ratio = report.summary.speed_ratio;
  if (ratio == null || Math.abs(ratio - 1) < 0.08) return null;
  return `Played at about ${Math.round(ratio * 100)}% of the target tempo. That difference is already allowed for; the notes below are what was still wrong.`;
}

export function worstLines(report: CompareReport) {
  return report.worst_bars.flatMap((bar) => bar.messages);
}

export function barLines(report: CompareReport) {
  return report.bars.map((bar) => ({
    bar: bar.bar,
    score: bar.score == null ? "–" : `${bar.score}%`,
    className: bar.score == null ? "none" : bar.score >= 85 ? "good" : bar.score >= 60 ? "fair" : "poor",
    messages: bar.messages.length ? bar.messages : ["All the notes in this bar match."],
  }));
}

function pitchOf(midi: number | null | undefined) {
  return midi == null ? "" : noteName(midi);
}

/** One chip per compared note, colored by what was wrong. Fret number when the target is tab. */
export function noteChips(report: CompareReport): NoteChip[] {
  return report.notes.map((n) => {
    const missing = n.kind === "missing";
    const extra = n.kind === "extra";
    const pitch = missing ? pitchOf(n.target_midi) : pitchOf(n.take_midi ?? n.target_midi);
    const text = extra
      ? pitch || "extra"
      : n.target_fret != null
        ? String(n.target_fret)
        : pitchOf(n.target_midi) || pitch;
    return {
      id: String(n.id),
      className: markClass(n.kind),
      title: n.message || "Matches the target",
      bar: n.bar,
      text,
      pitch,
    };
  });
}
