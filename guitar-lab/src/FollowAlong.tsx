import { useEffect, useState } from "react";
import Fretboard, { ChordDiagram, type BoardNote } from "./Fretboard";
import { chordAt, songChords, takeOnSong, type ChordSpan, type TakeMark } from "./followAlong";

export type NoteSource = { id: string; label: string; notes: BoardNote[] };

/**
 * Follows playback: the chord now and next with its shape, and the neck with the notes of
 * the chosen part lit as they sound. Works without a tab (chords and the app's transcription).
 */
export default function FollowAlong({
  chords,
  trainedChords = false,
  time,
  sources,
  take,
  openStrings,
  maxFret = 22,
}: {
  chords: ChordSpan[];
  /** Chords from the trained chord model (better than the templates). */
  trainedChords?: boolean;
  time: number;
  sources: NoteSource[];
  take?: { marks: TakeMark[]; start: number; speed: number; label: string } | null;
  openStrings: number[];
  maxFret?: number;
}) {
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? "");
  const [showTake, setShowTake] = useState(true);
  useEffect(() => {
    if (!sources.some((s) => s.id === sourceId)) setSourceId(sources[0]?.id ?? "");
  }, [sources, sourceId]);
  const source = sources.find((s) => s.id === sourceId);
  const { now, next } = chordAt(chords, time);
  const used = songChords(chords);
  const mine = take && showTake ? takeOnSong(take.marks, take.start, take.speed) : undefined;
  return (
    <section className="follow-along" aria-label="Follow along">
      <h3 className="section-title">Follow along</h3>
      {used.length > 0 && (
        <div className="chord-now">
          <div className="chord-pair" aria-live="off">
            <div>
              <small>Now</small>
              <ChordDiagram name={now?.chord ?? "N"} size={1.25} />
            </div>
            <div className="chord-next">
              <small>Next</small>
              {next ? <ChordDiagram name={next.chord} /> : <div className="chord-diagram empty">–</div>}
            </div>
          </div>
          <details className="song-chords">
            <summary>All {used.length} chords in this song</summary>
            <div className="chord-shapes">
              {used.map((c) => (
                <ChordDiagram key={c} name={c} size={0.85} />
              ))}
            </div>
            <p className="helper">
              Chords are worked out from the recording, not read from a tab.{" "}
              {trainedChords
                ? "Measured on band recordings, the chord model gets about 6 beats in 10 fully right and the root right on 7 in 10."
                : "Measured on band recordings they are right roughly half the time (install the chord model for better chords)."}{" "}
              Shapes are the common ones, lowest on the neck; the song may use other voicings.
            </p>
          </details>
        </div>
      )}
      {openStrings.length > 0 && sources.length > 0 && (
        <>
          <div className="follow-controls">
            {sources.length > 1 && (
              <label>
                Notes from
                <select id="board-source" value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
                  {sources.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {take && (
              <label className="consent">
                <input id="board-take" type="checkbox" checked={showTake} onChange={(e) => setShowTake(e.target.checked)} />
                <span>Show what I played ({take.label})</span>
              </label>
            )}
          </div>
          {source && <Fretboard notes={source.notes} take={mine} time={time} openStrings={openStrings} maxFret={maxFret} label={source.label} />}
        </>
      )}
      {openStrings.length > 0 && sources.length === 0 && (
        <p className="helper">Load your tab below, or press "Show tab & notation", to see the notes on the neck as the song plays.</p>
      )}
    </section>
  );
}
