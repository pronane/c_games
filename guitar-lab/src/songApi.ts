import { api } from "./engineApi";
import type { InstrumentSnapshot, EngineNote } from "./engineApi";
import type { BarRole } from "./songAudio";

export type SongPart = {
  id: string;
  label: string;
  position: "left" | "centre" | "right";
  share: number;
  role: "lead" | "rhythm" | "lead and rhythm" | "silent";
  roles: BarRole[];
  notes: number;
  doubled?: boolean;
};
export type InstrumentRow = {
  stem: string;
  label: string;
  energy_share: number;
  active_fraction: number;
  verdict: "present" | "trace" | "absent";
};
export type KeyInfo = {
  key: string;
  mode: "major" | "minor";
  fifths: number;
  confidence: "high" | "moderate" | "low";
  alternatives: string[];
};
export type TuningSuggestion = {
  suggested: string;
  options: string[];
  lowest_midi: number | null;
  reference_cents: number;
  reference_a4_hz: number;
  reasons: string[];
  confidence: string;
};
export type ChordSegment = { chord: string; start: number; end: number };
export type SongBreakdown = {
  duration: number;
  instruments: InstrumentRow[];
  selected_stem: string;
  parts: SongPart[];
  tempo: { bpm: number; beats: number[]; bars: number[]; time_signature: string };
  key: KeyInfo | null;
  chords: ChordSegment[];
  tuning: TuningSuggestion | null;
  reference_cents: number;
  warnings: string[];
};
export type Song = {
  id: string;
  name: string;
  instrument: string;
  status: "queued" | "decoding" | "separating" | "complete" | "failed";
  stage: string;
  error: string | null;
  result: SongBreakdown | null;
  expires_at: number;
};
export type TabNote = EngineNote & { part?: string };
export type Score = {
  part: string;
  role: string;
  label: string;
  instrument_profile: InstrumentSnapshot;
  notes: TabNote[];
  unplayable_notes: number;
  musicxml: string;
  chords: ChordSegment[];
  key: KeyInfo | null;
  tempo: { bpm: number; time_signature: string };
};

export function createSong(
  source: { file: File } | { url: string },
  instrument: string,
) {
  const body = new FormData();
  if ("file" in source) body.set("file", source.file);
  else body.set("url", source.url);
  body.set("consent", "true");
  body.set("instrument", instrument);
  return api<Song>("/api/songs", { method: "POST", body });
}
export const getSong = (id: string) => api<Song>(`/api/songs/${id}`);
export const deleteSong = (id: string) =>
  api<void>(`/api/songs/${id}`, { method: "DELETE", keepalive: true });
export const trackUrl = (id: string, track: string) =>
  `/api/songs/${id}/tracks/${encodeURIComponent(track)}`;
export function requestScore(
  id: string,
  body: { part: string; role: string; tuning: string; capo: number },
) {
  return api<Score>(`/api/songs/${id}/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Human name for a tuning id from the shared catalogue. */
export function tuningName(id: string) {
  const names: Record<string, string> = {
    standard: "Standard (E A D G B E)",
    half_step_down: "Half step down (E♭ standard)",
    drop_d: "Drop D",
    d_standard: "Whole step down (D standard)",
    drop_c_sharp: "Drop C♯",
    dadgad: "DADGAD",
    open_g: "Open G",
    none: "No tuning",
  };
  return names[id] ?? id.replaceAll("_", " ");
}
