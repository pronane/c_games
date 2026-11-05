import { useEffect, useRef, useState } from "react";
import {
  AlphaTabApi,
  FontFileFormat,
  importer,
  LayoutMode,
  model,
  Settings,
  StaveProfile,
} from "@coderline/alphatab";
// Bundled by Vite so the music font loads from our own origin (no CDN).
import bravuraWoff2 from "@coderline/alphatab/font/Bravura.woff2?url";
import bravuraWoff from "@coderline/alphatab/font/Bravura.woff?url";

// Renders a score as standard notation plus tablature (when the part has string/fret data).
// Accepts MusicXML text, or the bytes of any file alphaTab reads (Guitar Pro 3-7, MusicXML).
export type NoteMark = { bar: number; kind: string; target_midi?: number | null };

const MARK_COLOR: Record<string, [number, number, number]> = {
  wrong_pitch: [155, 47, 34],
  wrong_string: [155, 47, 34],
  missing: [154, 107, 18],
  early: [122, 84, 16],
  late: [122, 84, 16],
  wrong_duration: [122, 84, 16],
};

/** Color the written note heads and tab frets that the take got wrong, missed, or played off time. */
function paintMarks(score: model.Score, marks: NoteMark[], track: number) {
  const buckets = new Map<number, NoteMark[]>();
  for (const mark of marks) {
    if (mark.target_midi == null || mark.kind === "correct" || mark.kind === "extra") continue;
    const list = buckets.get(mark.bar) ?? [];
    list.push(mark);
    buckets.set(mark.bar, list);
  }
  const chosen = score.tracks[Math.min(track, Math.max(0, score.tracks.length - 1))];
  if (!chosen) return;
  for (const staff of chosen.staves)
    staff.bars.forEach((bar, index) => {
      const left = [...(buckets.get(index + 1) ?? [])];
      if (!left.length) return;
      for (const voice of bar.voices) {
        if (voice.isEmpty) continue;
        for (const beat of voice.beats) {
          if (beat.isRest) continue;
          for (const note of beat.notes) {
            if (note.isDead) continue;
            const at = left.findIndex((m) => m.target_midi === note.realValueWithoutHarmonic);
            if (at < 0) continue;
            const mark = left.splice(at, 1)[0];
            const rgb = MARK_COLOR[mark.kind];
            if (!rgb) continue;
            const style = note.style ?? new model.NoteStyle();
            note.style = style;
            style.colors ??= new Map();
            const color = new model.Color(rgb[0], rgb[1], rgb[2]);
            style.colors.set(model.NoteSubElement.StandardNotationNoteHead, color);
            style.colors.set(model.NoteSubElement.StandardNotationAccidentals, color);
            style.colors.set(model.NoteSubElement.GuitarTabFretNumber, color);
          }
        }
      }
    });
}

export default function Notation({
  musicxml,
  bytes,
  track = 0,
  tab,
  marks,
}: {
  musicxml?: string;
  bytes?: Uint8Array;
  track?: number;
  tab: boolean;
  /** Wrong, missing, early/late and short/long notes to color on the staff and tab. */
  marks?: NoteMark[];
}) {
  const host = useRef<HTMLDivElement>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (!host.current) return;
    setError("");
    const settings = new Settings();
    settings.core.useWorkers = false;
    settings.core.smuflFontSources = new Map([
      [FontFileFormat.Woff2, bravuraWoff2],
      [FontFileFormat.Woff, bravuraWoff],
    ]);
    settings.core.engine = "svg";
    settings.player.enablePlayer = false;
    settings.display.staveProfile = tab ? StaveProfile.ScoreTab : StaveProfile.Score;
    settings.display.layoutMode = LayoutMode.Page;
    settings.display.scale = 0.85;
    let api: AlphaTabApi | null = null;
    try {
      api = new AlphaTabApi(host.current, settings);
      api.error.on((e) => setError(e.message));
      const score = importer.ScoreLoader.loadScoreFromBytes(
        bytes ?? new TextEncoder().encode(musicxml ?? ""),
        settings,
      );
      // MusicXML tab staves import as tab-only; show notation above the tab as well.
      for (const t of score.tracks)
        for (const staff of t.staves) {
          staff.showStandardNotation = true;
          staff.showTablature = tab && staff.tuning.length > 0;
        }
      if (marks?.length) {
        try {
          paintMarks(score, marks, track);
        } catch {
          // Highlighting is optional; the staff still draws.
        }
      }
      api.renderScore(score, [Math.min(track, score.tracks.length - 1)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    return () => api?.destroy();
  }, [musicxml, bytes, track, tab, JSON.stringify(marks ?? [])]);
  return (
    <div className="notation">
      {error && (
        <p className="error">Notation could not be drawn: {error}</p>
      )}
      <div ref={host} className="notation-host" aria-label="Notation and tablature" />
    </div>
  );
}
