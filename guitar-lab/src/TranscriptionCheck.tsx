import { useEffect, useRef, useState } from "react";
import { Pause, Play, ScanSearch } from "lucide-react";
import { api } from "./engineApi";
import { trackUrl } from "./songApi";

type Stretch = { start: number; end: number; status: "gap" | "differs"; match?: number; missing: string[]; extra: string[] };
type Report = {
  part: string;
  recording_track: string;
  playback_track: string;
  summary: { typical_match: number; flagged_seconds: number; sounding_seconds: number; flagged_share: number; stretches: number };
  stretches: Stretch[];
  match_per_stretch: (number | null)[];
  stretch_s: number;
  most_missing: { note: string; seconds: number }[];
  most_extra: { note: string; seconds: number }[];
  roll: { fps: number; low_midi: number; bins: number; frames: number; level: string; missing: string; extra: string };
  notes: { time: number; duration: number; midi: number }[];
};
type Mode = "recording" | "playback" | "both";

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteName = (m: number) => NAMES[m % 12] + (Math.floor(m / 12) - 1);
const bytes = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const PX = 30, ROW = 6, TOP = 4, STRIP = 16, AXIS = 16, LABEL = 30;

/**
 * "Check this transcription": the part's notes played back against the audio they were
 * transcribed from, with the stretches where the two disagree marked. A stretch is marked
 * when the recording sounds but there is no note, or when the written notes leave out clearly
 * more of the recording's pitches than in the rest of this song (server/transcription_check.py).
 */
export default function TranscriptionCheck({ songId, parts }: { songId: string; parts: { id: string; label: string }[] }) {
  const [part, setPart] = useState(parts[0]?.id ?? ""),
    [report, setReport] = useState<Report | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mode, setMode] = useState<Mode>("both"),
    [playing, setPlaying] = useState(false),
    [now, setNow] = useState(0);
  const canvas = useRef<HTMLCanvasElement | null>(null),
    scroller = useRef<HTMLDivElement | null>(null),
    audio = useRef<{ ctx: AudioContext; buffers: AudioBuffer[]; gains: { g: GainNode; p: StereoPannerNode }[] } | null>(null),
    sources = useRef<AudioBufferSourceNode[]>([]),
    clock = useRef({ startedAt: 0, offset: 0 }),
    base = useRef<ImageData | null>(null),
    modeRef = useRef<Mode>("both");
  modeRef.current = mode;

  useEffect(() => () => stop(true), []);
  useEffect(() => {
    stop(true);
    setReport(null);
    audio.current = null;
  }, [songId, part]);

  async function run() {
    setBusy(true);
    setError("");
    try {
      setReport(await api<Report>(`/api/songs/${songId}/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ part }),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const duration = report ? report.roll.frames / report.roll.fps : 0;
  const x = (t: number) => LABEL + t * PX;

  // Draw the timeline once per report; the playhead is drawn over a saved copy.
  useEffect(() => {
    const cv = canvas.current;
    if (!report || !cv) return;
    const css = (n: string) => getComputedStyle(cv).getPropertyValue(n).trim() || "#888";
    const { fps, low_midi: low, bins, frames } = report.roll;
    const level = bytes(report.roll.level), missing = bytes(report.roll.missing), extra = bytes(report.roll.extra);
    const dpr = window.devicePixelRatio || 1;
    const w = LABEL + Math.ceil(duration * PX) + 8, h = TOP + bins * ROW + 4 + STRIP + AXIS;
    cv.style.width = `${w}px`;
    cv.style.height = `${h}px`;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    const g = cv.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const y = (m: number) => TOP + (bins - 1 - (m - low)) * ROW;
    g.fillStyle = css("--check-bg");
    g.fillRect(0, 0, w, h);
    g.font = "9px ui-monospace, monospace";
    g.textBaseline = "middle";
    for (let m = low; m < low + bins; m++)
      if (m % 12 === 4 || m % 12 === 9) {
        g.fillStyle = css("--check-muted");
        g.fillText(noteName(m), 2, y(m) + ROW / 2);
        g.fillStyle = css("--check-rule");
        g.fillRect(LABEL, y(m) + ROW - 0.5, w - LABEL, 1);
      }
    const cw = PX / fps, ink = css("--check-ink");
    for (let f = 0; f < frames; f++)
      for (let b = 0; b < bins; b++) {
        const i = b * frames + f, v = level[i] / 255;
        if (missing[i]) g.fillStyle = css("--check-missing");
        else if (extra[i]) g.fillStyle = css("--check-extra");
        else if (v > 0.25) {
          g.globalAlpha = ((v - 0.25) / 0.75) * 0.55;
          g.fillStyle = `rgb(${ink})`;
        } else continue;
        g.fillRect(x(f / fps), y(low + b), cw + 0.5, ROW);
        g.globalAlpha = 1;
      }
    g.strokeStyle = css("--check-note");
    g.lineWidth = 1.2;
    for (const n of report.notes)
      if (n.midi >= low && n.midi < low + bins) g.strokeRect(x(n.time) + 0.5, y(n.midi) + 0.5, Math.max(3, n.duration * PX) - 1, ROW - 1);
    const sy = TOP + bins * ROW + 4;
    for (const s of report.stretches) {
      g.fillStyle = css(s.status === "gap" ? "--check-gap" : "--check-differs");
      g.fillRect(x(s.start), sy, (s.end - s.start) * PX, STRIP - 6);
    }
    g.fillStyle = css("--check-muted");
    g.textBaseline = "alphabetic";
    for (let s = 0; s <= duration; s += 10) g.fillText(fmt(s), x(s) + 2, h - 3);
    base.current = g.getImageData(0, 0, cv.width, cv.height);
    head(clock.current.offset);
  }, [report]);

  function head(t: number) {
    const cv = canvas.current;
    if (!cv || !base.current) return;
    const g = cv.getContext("2d")!;
    g.putImageData(base.current, 0, 0);
    const dpr = window.devicePixelRatio || 1;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = getComputedStyle(cv).getPropertyValue("--check-note").trim() || "#0a7";
    g.fillRect(x(t) - 1, 0, 2, cv.height / dpr - AXIS);
    const sc = scroller.current;
    if (sc && (x(t) < sc.scrollLeft + 30 || x(t) > sc.scrollLeft + sc.clientWidth - 60)) sc.scrollLeft = Math.max(0, x(t) - sc.clientWidth * 0.25);
    setNow(t);
  }

  async function ready() {
    if (audio.current || !report) return audio.current;
    const ctx = new AudioContext();
    const load = async (track: string) => {
      const r = await fetch(trackUrl(songId, track));
      if (!r.ok) throw Error("Could not load the audio.");
      return ctx.decodeAudioData(await r.arrayBuffer());
    };
    const buffers = await Promise.all([load(report.recording_track), load(report.playback_track)]);
    const gains = buffers.map(() => {
      const g = ctx.createGain(), p = ctx.createStereoPanner();
      g.connect(p).connect(ctx.destination);
      return { g, p };
    });
    audio.current = { ctx, buffers, gains };
    return audio.current;
  }

  function route(m: Mode) {
    const a = audio.current;
    if (!a) return;
    const [rec, pb] = a.gains;
    rec.g.gain.value = m === "playback" ? 0 : 1;
    pb.g.gain.value = m === "recording" ? 0 : 1;
    rec.p.pan.value = m === "both" ? -1 : 0;
    pb.p.pan.value = m === "both" ? 1 : 0;
  }

  const position = () => {
    const a = audio.current;
    return a && sources.current.length ? Math.min(duration, clock.current.offset + a.ctx.currentTime - clock.current.startedAt) : clock.current.offset;
  };

  function stop(close = false) {
    sources.current.forEach((s) => {
      try {
        s.stop();
      } catch {}
    });
    sources.current = [];
    setPlaying(false);
    if (close) audio.current?.ctx.close().catch(() => {});
  }

  async function play(from?: number) {
    try {
      const a = await ready();
      if (!a) return;
      await a.ctx.resume();
      if (from === undefined && sources.current.length) {
        clock.current.offset = position();
        stop();
        return;
      }
      stop();
      if (from !== undefined) clock.current.offset = Math.max(0, Math.min(duration - 0.1, from));
      route(modeRef.current);
      sources.current = a.buffers.map((b, i) => {
        const s = a.ctx.createBufferSource();
        s.buffer = b;
        s.connect(a.gains[i].g);
        return s;
      });
      clock.current.startedAt = a.ctx.currentTime;
      sources.current.forEach((s) => s.start(0, clock.current.offset));
      setPlaying(true);
      const tick = () => {
        if (!sources.current.length) return;
        const t = position();
        head(t);
        if (t >= duration - 0.05) {
          clock.current.offset = 0;
          stop();
          return;
        }
        requestAnimationFrame(tick);
      };
      tick();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const share = report ? Math.round(report.summary.flagged_share * 100) : 0;
  return (
    <section className="transcription-check" aria-label="Check this transcription">
      <h3>
        <ScanSearch size={16} /> Check this transcription
      </h3>
      <p className="helper">
        Plays the notes the app wrote back against the audio they came from, and marks where the two disagree: the guitar
        is sounding with no note written, or the written notes leave out clearly more of what is heard than in the rest of
        the song. Listen to the marked places to judge the tab.
      </p>
      <div className="presets">
        {parts.length > 1 && (
          <label className="speed">
            Part
            <select id="check-part" value={part} onChange={(e) => setPart(e.target.value)}>
              {parts.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </label>
        )}
        <button className="primary" disabled={busy || !part} onClick={run}>
          {busy ? "Playing it back and comparing…" : report ? "Check again" : "Check this transcription"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {report && (
        <>
          <p>
            {report.stretches.length === 0
              ? "No major disagreements detected; this does not verify every note."
              : `${report.stretches.length} stretch${report.stretches.length > 1 ? "es" : ""} marked, ${report.summary.flagged_seconds.toFixed(0)} s of ${report.summary.sounding_seconds.toFixed(0)} s of playing (${share}%).`}
            {report.most_missing.length > 0 && ` Most often heard but not written: ${report.most_missing.slice(0, 3).map((m) => m.note).join(", ")}.`}
          </p>
          <div className="presets" role="group" aria-label="What to hear">
            <button className="primary" onClick={() => play()}>
              {playing ? <Pause size={13} /> : <Play size={13} />} {playing ? "Pause" : "Play"}
            </button>
            {(["recording", "playback", "both"] as Mode[]).map((m) => (
              <button key={m} className={mode === m ? "on" : ""} aria-pressed={mode === m} onClick={() => { setMode(m); route(m); }}>
                {m === "recording" ? "Recording" : m === "playback" ? "Tab played back" : "Both (recording left, tab right)"}
              </button>
            ))}
            <span className="helper">{fmt(now)} / {fmt(duration)}</span>
          </div>
          <div className="check-scroller" ref={scroller}>
            <canvas
              ref={canvas}
              className="check-canvas"
              role="img"
              aria-label="Timeline of the recording with the written notes drawn over it and the disagreements marked"
              onClick={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                play((e.clientX - r.left - LABEL) / PX);
              }}
            />
          </div>
          <p className="helper">
            Grey: the recording. Outlined: the notes written. Orange: heard but not written. Purple: written but not heard.
            Bar under the timeline: marked stretches (orange: no note written, red: the notes differ).
          </p>
          {report.stretches.length > 0 && (
            <ul className="check-list">
              {report.stretches.slice(0, 12).map((s) => (
                <li key={s.start}>
                  <button className="link-button" onClick={() => play(Math.max(0, s.start - 1))}>
                    {fmt(s.start)}–{fmt(s.end)}
                  </button>{" "}
                  {s.status === "gap" ? "the guitar is sounding but no note is written" : "the written notes differ from the recording"}
                  {s.missing.length > 0 && ` (heard but not written: ${s.missing.join(", ")})`}
                  {s.extra.length > 0 && ` (written but not heard: ${s.extra.join(", ")})`}
                </li>
              ))}
              {report.stretches.length > 12 && <li className="helper">and {report.stretches.length - 12} more on the timeline</li>}
            </ul>
          )}
          <p className="helper">
            The playback uses a plain guitar sound, so it never sounds exactly like the recording. Even a note-perfect tab
            plays back differently; the marks compare each stretch with how well the rest of this song matches.
          </p>
        </>
      )}
    </section>
  );
}
