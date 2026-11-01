import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Play, Square, Download, Music2 } from "lucide-react";
import * as alphaTab from "@coderline/alphatab";
import { synthesize } from "./tabScore";
import { api, type EngineNote } from "./engineApi";
import type { ResolvedInstrument } from "./instruments";
import type { BarMark } from "./feedback";
const Notation = lazy(() => import("./Notation"));

type Listen = "heard" | "reference" | "both" | "recording" | "";
type Scored = { notes: EngineNote[]; musicxml: string; unplayable_notes: number };

/**
 * The app plays back what it understood from the player's recording, on its own guitar sound:
 * the notes the transcription found, nothing else. Next to the written/original part and the
 * raw recording, it makes clear which notes the app heard and which it didn't.
 */
export default function HeardTake({
  takeNotes,
  referenceNotes,
  recording,
  bars,
  profile,
  referenceLabel,
}: {
  takeNotes: EngineNote[];
  referenceNotes: { time: number; duration: number; midi: number }[];
  recording: AudioBuffer | null;
  bars?: BarMark[];
  profile: ResolvedInstrument;
  referenceLabel: string;
}) {
  const ctx = useRef<AudioContext | null>(null),
    source = useRef<AudioBufferSourceNode | null>(null),
    [playing, setPlaying] = useState<Listen>(""),
    [scored, setScored] = useState<Scored | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const context = () => ctx.current ?? (ctx.current = new AudioContext());
  // Tempo for the notation grid: from the bar lines when the take came from a song or tab.
  const bpm = useMemo(() => {
    if (bars && bars.length > 1) {
      const gap = bars[1].time - bars[0].time;
      if (gap > 0.3) return Math.round(240 / gap);
    }
    return 90;
  }, [bars]);
  const length = useMemo(
    () =>
      Math.max(
        1,
        ...takeNotes.map((n) => n.time + n.duration),
        ...referenceNotes.map((n) => n.time + n.duration),
        recording?.duration ?? 0,
      ) + 0.5,
    [takeNotes, referenceNotes, recording],
  );
  useEffect(() => {
    setScored(null);
  }, [takeNotes]);
  useEffect(
    () => () => {
      try {
        source.current?.stop();
      } catch {}
      ctx.current?.close().catch(() => {});
    },
    [],
  );

  function stop() {
    try {
      source.current?.stop();
    } catch {}
    source.current = null;
    setPlaying("");
  }
  async function listen(which: Listen) {
    stop();
    if (!which) return;
    const c = context();
    await c.resume();
    const rate = c.sampleRate;
    let buffer: AudioBuffer;
    if (which === "recording") {
      if (!recording) return;
      buffer = recording;
    } else {
      const heard = synthesize(takeNotes, rate, length, 1, 0.3),
        written = synthesize(referenceNotes, rate, length, 1, 0.3);
      buffer = c.createBuffer(2, heard.length, rate);
      if (which === "heard") {
        buffer.getChannelData(0).set(heard);
        buffer.getChannelData(1).set(heard);
      } else if (which === "reference") {
        buffer.getChannelData(0).set(written);
        buffer.getChannelData(1).set(written);
      } else {
        // Original in the left ear, what you played in the right.
        buffer.getChannelData(0).set(written);
        buffer.getChannelData(1).set(heard);
      }
    }
    const s = c.createBufferSource();
    s.buffer = buffer;
    s.connect(c.destination);
    s.onended = () => {
      if (source.current === s) setPlaying("");
    };
    s.start();
    source.current = s;
    setPlaying(which);
  }

  async function showNotation() {
    setBusy(true);
    setError("");
    try {
      setScored(
        await api<Scored>("/api/tabs/notation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            notes: takeNotes.map(({ time, duration, midi, string, fret }) => ({ time, duration, midi, string, fret })),
            instrument: profile.id,
            tuning: profile.settings.tuning,
            capo: profile.settings.capo,
            bpm,
            title: "My take",
          }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const gpUrl = useMemo(() => {
    if (!scored) return "";
    try {
      const settings = new alphaTab.Settings();
      const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(new TextEncoder().encode(scored.musicxml), settings);
      const data = new alphaTab.exporter.Gp7Exporter().export(score, settings);
      return URL.createObjectURL(new Blob([new Uint8Array(data)], { type: "application/octet-stream" }));
    } catch {
      return "";
    }
  }, [scored]);
  useEffect(() => () => {
    if (gpUrl) URL.revokeObjectURL(gpUrl);
  }, [gpUrl]);

  const button = (which: Exclude<Listen, "">, label: string, disabled = false) => (
    <button className={playing === which ? "on" : ""} disabled={disabled} onClick={() => (playing === which ? stop() : listen(which))}>
      {playing === which ? <Square size={13} /> : <Play size={13} />} {label}
    </button>
  );

  return (
    <div className="heard-take" aria-label="Your take as the app heard it">
      <h3>
        <Music2 size={16} /> Your take, as the app heard it
      </h3>
      <p className="helper">
        The app plays back the {takeNotes.length} notes it picked out of your recording, on its own {profile.name.toLowerCase()}{" "}
        sound. A note you played but can't hear here wasn't picked up; a note you hear but didn't play is a detection
        mistake. Compare it with {referenceLabel.toLowerCase()} and with your actual recording.
      </p>
      <div className="presets">
        {button("heard", "What the app heard", !takeNotes.length)}
        {button("reference", referenceLabel, !referenceNotes.length)}
        {button("both", "Both (original left, you right)", !takeNotes.length || !referenceNotes.length)}
        {button("recording", "My recording", !recording)}
      </div>
      <div className="presets">
        <button disabled={busy || !takeNotes.length} onClick={showNotation}>
          {busy ? "Writing it out…" : "Show my take as notation and tab"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {scored && (
        <>
          {scored.unplayable_notes > 0 && (
            <p className="helper">{scored.unplayable_notes} notes are outside this tuning, so they are left out of the tab and notation.</p>
          )}
          <Suspense fallback={<p className="helper">Loading the notation view…</p>}>
            <Notation musicxml={scored.musicxml} tab={profile.openStrings.length > 0} />
          </Suspense>
          {gpUrl && (
            <a className="download" href={gpUrl} download="my-take.gp">
              <Download size={14} /> Download my take as Guitar Pro
            </a>
          )}
        </>
      )}
    </div>
  );
}
