import { useEffect, useRef, useState } from "react";
import {
  AlphaTabApi,
  FontFileFormat,
  importer,
  LayoutMode,
  Settings,
  StaveProfile,
} from "@coderline/alphatab";
// Bundled by Vite so the music font loads from our own origin (no CDN).
import bravuraWoff2 from "@coderline/alphatab/font/Bravura.woff2?url";
import bravuraWoff from "@coderline/alphatab/font/Bravura.woff?url";

// Renders MusicXML as standard notation plus tablature (when the part has string/fret data).
export default function Notation({
  musicxml,
  tab,
}: {
  musicxml: string;
  tab: boolean;
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
        new TextEncoder().encode(musicxml),
        settings,
      );
      // MusicXML tab staves import as tab-only; show notation above the tab as well.
      for (const track of score.tracks)
        for (const staff of track.staves) {
          staff.showStandardNotation = true;
          staff.showTablature = tab && staff.tuning.length > 0;
        }
      api.renderScore(score, [0]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    return () => api?.destroy();
  }, [musicxml, tab]);
  return (
    <div className="notation">
      {error && (
        <p className="error">Notation could not be drawn: {error}</p>
      )}
      <div ref={host} className="notation-host" aria-label="Notation and tablature" />
    </div>
  );
}
