import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { FileMusic, Play, Pause, Mic, Square, Repeat, Gauge, Timer, Headphones, Download, ClipboardPaste } from "lucide-react";
import * as alphaTab from "@coderline/alphatab";
import {
  excerpt,
  matchTuning,
  pickTrack,
  scoreToPiece,
  synthesize,
  type TabPiece,
} from "./tabScore";
import { parseTextTab, tuningName } from "./songApi";
import { addClicks, clickTimes, loadLatency, type LatencyResult } from "./practice";
import { estimateOffset, mixInto } from "./songAudio";
import { encodeWav } from "./engineApi";
import { captureError } from "./audioInputs";
import { Recorder } from "./recorder";
import LatencyCheck from "./LatencyCheck";
import type { BarMark } from "./feedback";
import { resolveInstrument, instruments, type InstrumentSettings } from "./instruments";
import { names } from "./analysis";
const Notation = lazy(() => import("./Notation"));

type Clip = { name: string; buffer: AudioBuffer };
export type TabSource = { name: string; musicxml?: string; bytes?: Uint8Array };
type Props = {
  settings: InstrumentSettings;
  onSettings: (next: InstrumentSettings) => void;
  /** A tab handed over from elsewhere in the app (e.g. the song breakdown's own tab). */
  incoming?: TabSource | null;
  onCompare: (
    reference: Clip,
    take: Clip,
    start: number,
    length: number,
    bars: BarMark[],
    notes: { time: number; duration: number; midi: number; string: number | null; fret: number | null }[],
  ) => void;
};
type Take = { buffer: AudioBuffer; from: number; to: number; speed: number; detail: string };

const SPEEDS = [1, 0.9, 0.8, 0.75, 0.7, 0.6, 0.5];
const GP = ".gp,.gp3,.gp4,.gp5,.gpx,.musicxml,.xml,.mxl,.txt,.tab";

export default function TabLab({ settings, onSettings, incoming, onCompare }: Props) {
  const profile = resolveInstrument(settings);
  const [source, setSource] = useState<TabSource | null>(null),
    [score, setScore] = useState<alphaTab.model.Score | null>(null),
    [track, setTrack] = useState(0),
    [text, setText] = useState(""),
    [pasting, setPasting] = useState(false),
    [textBpm, setTextBpm] = useState(90),
    [piece, setPiece] = useState<TabPiece | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [speed, setSpeed] = useState(1),
    [clickOn, setClickOn] = useState(true),
    [guide, setGuide] = useState(true),
    [loopOn, setLoopOn] = useState(false),
    [fromBar, setFromBar] = useState(1),
    [toBar, setToBar] = useState(4),
    [playing, setPlaying] = useState(false),
    [position, setPosition] = useState(0),
    [recording, setRecording] = useState(false),
    [take, setTake] = useState<Take | null>(null),
    [latency, setLatency] = useState<LatencyResult | null>(() => loadLatency()),
    [mixUrl, setMixUrl] = useState("");
  const ctx = useRef<AudioContext | null>(null),
    rec = useRef<Recorder | null>(null),
    current = useRef<AudioBufferSourceNode | null>(null),
    clock = useRef({ context: 0, from: 0, speed: 1, loop: null as null | { start: number; end: number } }),
    raf = useRef(0);
  const context = () => ctx.current ?? (ctx.current = new AudioContext({ latencyHint: "interactive" }));
  const recorder = () => rec.current ?? (rec.current = new Recorder(context()));

  useEffect(
    () => () => {
      stop();
      rec.current?.release();
      ctx.current?.close().catch(() => {});
    },
    [],
  );
  useEffect(() => {
    if (incoming) load(incoming);
  }, [incoming]);
  useEffect(() => () => {
    if (mixUrl) URL.revokeObjectURL(mixUrl);
  }, [mixUrl]);

  // ---------------------------------------------------------------- loading
  async function load(src: TabSource) {
    setError("");
    setTake(null);
    stop();
    try {
      const bytes = src.bytes ?? new TextEncoder().encode(src.musicxml ?? "");
      const s = alphaTab.importer.ScoreLoader.loadScoreFromBytes(bytes, new alphaTab.Settings());
      const t = pickTrack(s, profile.openStrings.length || 6);
      setSource({ name: src.name, bytes });
      setScore(s);
      setTrack(t);
      const p = scoreToPiece(s, t);
      setPiece(p);
      setFromBar(1);
      setToBar(Math.min(4, p.bars.length));
    } catch (e) {
      setError(
        "That file could not be read as a tab or score. Guitar Pro (.gp, .gp3–.gp5, .gpx), MusicXML and plain-text tab work. " +
          (e instanceof Error ? e.message : ""),
      );
    }
  }

  async function loadText(raw: string, name: string) {
    setError("");
    setTake(null);
    stop();
    setBusy(true);
    try {
      const r = await parseTextTab({
        text: raw,
        instrument: settings.instrument,
        tuning: settings.tuning,
        capo: settings.capo,
        bpm: textBpm,
        title: name.replace(/\.[^.]+$/, ""),
      });
      // Show the engine's notation; play and compare from the parsed notes.
      const bytes = new TextEncoder().encode(r.musicxml);
      const s = alphaTab.importer.ScoreLoader.loadScoreFromBytes(bytes, new alphaTab.Settings());
      setSource({ name, bytes });
      setScore(s);
      setTrack(0);
      const barTimes = r.bars;
      const barOf = (t: number) => Math.max(1, barTimes.filter((b) => b <= t + 1e-6).length);
      const last = r.beats[r.beats.length - 1] ?? 0;
      setPiece({
        title: name.replace(/\.[^.]+$/, ""),
        artist: "",
        track: 0,
        tracks: [{ index: 0, name: profile.name, strings: profile.openStrings.length, percussion: false }],
        notes: r.notes.map((n) => ({ ...n, bar: barOf(n.time) })),
        bars: barTimes.map((time, i) => ({ number: i + 1, time })),
        beats: r.beats,
        bpm: r.bpm,
        tuning: profile.openStrings.map((m) => m - settings.capo),
        capo: settings.capo,
        duration: last,
        warnings: r.warnings,
      });
      setText(raw);
      setFromBar(1);
      setToBar(Math.min(4, barTimes.length));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onFile(file: File) {
    if (/\.(txt|tab)$/i.test(file.name)) return loadText(await file.text(), file.name);
    load({ name: file.name, bytes: new Uint8Array(await file.arrayBuffer()) });
  }

  function chooseTrack(t: number) {
    if (!score) return;
    setTrack(t);
    setTake(null);
    const p = scoreToPiece(score, t);
    setPiece(p);
    setToBar(Math.min(toBar, p.bars.length));
  }

  // ---------------------------------------------------------------- tuning from the file
  const fileTuning = piece && piece.tuning.length ? matchTuning(piece.tuning, profile.tunings) : null;
  const tuningDiffers = !!piece && piece.tuning.length > 0 && JSON.stringify(piece.tuning) !== JSON.stringify(profile.openStrings.map((m) => m - settings.capo));
  const stringsDiffer = !!piece && piece.tuning.length > 0 && piece.tuning.length !== profile.openStrings.length;
  const suggestInstrument =
    stringsDiffer && piece ? instruments.find((i) => Object.values(i.tunings).some((t) => t.length === piece.tuning.length)) : undefined;
  const noteName = (m: number) => names[m % 12] + (Math.floor(m / 12) - 1);

  // ---------------------------------------------------------------- playback
  const bars = piece?.bars ?? [];
  const duration = piece?.duration ?? 0;
  const range = useMemo(() => {
    if (!piece || !loopOn) return { start: 0, end: duration };
    const start = bars[Math.max(0, fromBar - 1)]?.time ?? 0,
      end = bars[toBar]?.time ?? duration;
    return { start, end: Math.max(start + 0.5, end) };
  }, [piece, loopOn, fromBar, toBar, duration]);

  /** The app's rendition of [from, to) at `atSpeed`, optionally quieter, with clicks. */
  function render(from: number, to: number, opts: { level?: number; click?: boolean; atSpeed?: number } = {}) {
    const c = context(),
      rate = c.sampleRate,
      sp = opts.atSpeed ?? speed,
      part = excerpt(piece!, from, to, 1),
      audio = synthesize(part.notes, rate, (to - from) / sp + 0.05, sp, 0.3 * (opts.level ?? 1));
    if (opts.click) addClicks([audio], rate, clickTimes(piece!.beats, from, to), from, sp, 0.3);
    return audio;
  }
  function toBuffer(channels: Float32Array[]) {
    const c = context(),
      b = c.createBuffer(channels.length, Math.max(1, channels[0].length), c.sampleRate);
    channels.forEach((ch, i) => b.getChannelData(i).set(ch));
    return b;
  }
  function stop() {
    try {
      current.current?.stop();
    } catch {}
    current.current = null;
    cancelAnimationFrame(raf.current);
    setPlaying(false);
  }
  function start(buffer: AudioBuffer, when: number, from: number, sp: number, loop: null | { start: number; end: number }) {
    const c = context(),
      src = c.createBufferSource();
    src.buffer = buffer;
    src.loop = !!loop;
    src.connect(c.destination);
    src.start(when);
    src.onended = () => {
      if (current.current === src) stop();
    };
    current.current = src;
    clock.current = { context: when, from, speed: sp, loop };
  }
  function tick() {
    const c = ctx.current;
    if (!c) return;
    const { context: t0, from, speed: sp, loop } = clock.current;
    let t = from + Math.max(0, c.currentTime - t0) * sp;
    if (loop && t > loop.end) t = loop.start + ((t - loop.start) % (loop.end - loop.start));
    setPosition(Math.min(duration, t));
    raf.current = requestAnimationFrame(tick);
  }
  async function play() {
    if (!piece) return;
    stop();
    const c = context();
    await c.resume();
    const from = loopOn ? range.start : position >= duration - 0.2 ? 0 : position,
      to = loopOn ? range.end : duration;
    start(toBuffer([render(from, to, { click: clickOn })]), c.currentTime + 0.05, from, speed, loopOn ? range : null);
    setPlaying(true);
    tick();
  }
  useEffect(() => {
    if (playing && !recording) play();
  }, [speed, clickOn, track]);

  // ---------------------------------------------------------------- record along
  async function recordAlong() {
    if (!piece) return;
    setError("");
    setTake(null);
    setMixUrl("");
    stop();
    try {
      const c = context();
      await c.resume();
      await recorder().ensure();
      const from = range.start,
        to = range.end,
        backing = render(from, to, { level: guide ? 0.45 : 0, click: clickOn || !guide }),
        reference = render(from, to),
        beat = 60 / piece.bpm / speed,
        countIn = 4 * beat,
        now = c.currentTime + 0.15,
        songStart = now + countIn;
      for (let i = 0; i < 4; i++) {
        const osc = c.createOscillator(),
          g = c.createGain();
        osc.frequency.value = i === 0 ? 1500 : 1000;
        g.gain.setValueAtTime(0.0001, now + i * beat);
        g.gain.exponentialRampToValueAtTime(0.4, now + i * beat + 0.005);
        g.gain.exponentialRampToValueAtTime(0.0001, now + i * beat + 0.08);
        osc.connect(g).connect(c.destination);
        osc.start(now + i * beat);
        osc.stop(now + i * beat + 0.1);
      }
      const band = toBuffer([backing]);
      start(band, songStart, from, speed, null);
      setPlaying(true);
      tick();
      const recordFrom = c.currentTime,
        length = band.duration;
      setRecording(true);
      const raw = await recorder().capture(Math.ceil((songStart - recordFrom + length + 0.6) * c.sampleRate), length + countIn + 10);
      setRecording(false);
      stop();
      const delay = recorder().delay(latency),
        lead = Math.round((songStart - recordFrom + delay) * c.sampleRate),
        aligned = raw.subarray(Math.min(raw.length, Math.max(0, lead))),
        est = estimateOffset(reference, aligned.subarray(0, reference.length), c.sampleRate, 0.3),
        shift = est ? Math.round(est.seconds * c.sampleRate) : 0,
        final = aligned.subarray(Math.max(0, shift), Math.max(0, shift) + Math.round(length * c.sampleRate)),
        buffer = c.createBuffer(1, Math.max(1, final.length), c.sampleRate);
      buffer.getChannelData(0).set(final);
      setTake({
        buffer,
        from,
        to,
        speed,
        detail:
          `${Math.round(delay * 1000)} ms ${latency?.ok ? "measured" : "reported"} device delay removed` +
          (est ? `, then ${Math.round(est.seconds * 1000)} ms from matching your attacks to the tab.` : ".") +
          (speed !== 1 ? ` Played at ${Math.round(speed * 100)}% speed.` : ""),
      });
    } catch (e) {
      setRecording(false);
      stop();
      setError(captureError(e));
    }
  }

  function together(t: Take) {
    const tab = render(t.from, t.to, { atSpeed: t.speed, level: 0.8 }),
      out: [Float32Array, Float32Array] = [tab.slice(), tab.slice()];
    mixInto(out, [t.buffer.getChannelData(0)], 1);
    let peak = 0;
    for (const ch of out) for (const v of ch) peak = Math.max(peak, Math.abs(v));
    if (peak > 0.99) for (const ch of out) for (let i = 0; i < ch.length; i++) ch[i] *= 0.99 / peak;
    return out;
  }
  async function hearTogether() {
    if (!take) return;
    stop();
    const c = context();
    await c.resume();
    start(toBuffer(together(take)), c.currentTime + 0.05, take.from, take.speed, null);
    setPlaying(true);
    tick();
  }
  function compare() {
    if (!take || !piece) return;
    const part = excerpt(piece, take.from, take.to, take.speed),
      ref = toBuffer([render(take.from, take.to, { atSpeed: take.speed })]);
    onCompare(
      { name: `${piece.title} · the app's version of the tab`, buffer: ref },
      { name: "Your take from the tab", buffer: take.buffer },
      0,
      Math.min(60, take.buffer.duration, ref.duration),
      part.bars,
      part.notes.map(({ time, duration, midi, string, fret }) => ({ time, duration, midi, string, fret })),
    );
  }

  // ---------------------------------------------------------------- export
  const gpUrl = useMemo(() => {
    if (!score) return "";
    try {
      const data = new alphaTab.exporter.Gp7Exporter().export(score, new alphaTab.Settings());
      return URL.createObjectURL(new Blob([new Uint8Array(data)], { type: "application/octet-stream" }));
    } catch {
      return "";
    }
  }, [score]);
  useEffect(() => () => {
    if (gpUrl) URL.revokeObjectURL(gpUrl);
  }, [gpUrl]);

  const fmt = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  const barAt = (t: number) => Math.max(1, bars.filter((b) => b.time <= t + 1e-3).length);

  return (
    <section className="panel song-lab tab-lab" id="tab-lesson" aria-labelledby="tab-lab-title">
      <div className="eyebrow">LEARN FROM A TAB</div>
      <h2 id="tab-lab-title">Learn from a tab or score</h2>
      <p className="panel-desc">
        Upload a tab or notation file. We show it as notation and tab, play our own version of it, and check your
        recording against the exact notes written. This works for any song, even when we can't pull the{" "}
        {profile.name.toLowerCase()} out of the recording.
      </p>

      <label className={"drop " + (source ? "loaded" : "")}>
        <input id="tab-file" type="file" accept={GP} disabled={busy || recording} onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        <span className="upload-icon"><FileMusic size={22} /></span>
        <strong>{source ? source.name : "Choose a tab or score"}</strong>
        <span>Guitar Pro (.gp, .gp3–.gp5, .gpx), MusicXML (.musicxml, .xml, .mxl) or a text tab (.txt)</span>
      </label>
      <button className="link-button" onClick={() => setPasting(!pasting)} disabled={busy || recording}>
        <ClipboardPaste size={13} /> {pasting ? "Hide" : "Or paste a text tab"}
      </button>
      {pasting && (
        <div className="paste-tab">
          <textarea
            id="tab-text"
            rows={8}
            spellCheck={false}
            placeholder={"e|-------0-|\nB|-----1---|\nG|---2-----|\nD|-2-------|\nA|---------|\nE|---------|"}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="tab-text-row">
            <label>
              Tempo
              <input id="tab-bpm" type="number" min={30} max={300} value={textBpm} onChange={(e) => setTextBpm(Number(e.target.value) || 90)} />
              BPM
            </label>
            <button className="primary" disabled={busy || !text.trim()} onClick={() => loadText(text, "Pasted tab")}>
              {busy ? "Reading…" : "Use this tab"}
            </button>
          </div>
          <p className="helper">
            Read for {tuningName(settings.tuning)}{settings.capo ? `, capo ${settings.capo}` : ""}. Text tab has no rhythm, so
            notes are spaced by where they sit between bar lines.
          </p>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      {piece && (
        <div className="song-results">
          <div className="song-facts">
            <div><small>Piece</small><b>{piece.title}</b>{piece.artist && <span className="chip">{piece.artist}</span>}</div>
            <div><small>Tempo</small><b>{Math.round(piece.bpm)} BPM</b></div>
            <div><small>Length</small><b>{fmt(duration)}</b><span className="chip">{bars.length} bars</span></div>
          </div>
          {piece.tracks.length > 1 && (
            <label className="part-picker">
              Track
              <select id="tab-track" value={track} onChange={(e) => chooseTrack(Number(e.target.value))}>
                {piece.tracks.map((t) => (
                  <option key={t.index} value={t.index}>
                    {t.name}
                    {t.percussion ? " (drums)" : t.strings ? ` · ${t.strings} strings` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          {stringsDiffer && (
            <p className="notice-strong">
              This track is for a {piece.tuning.length}-string instrument; you've chosen {profile.name.toLowerCase()}.
              {suggestInstrument && <> Switch the instrument to {suggestInstrument.name} above, or pick another track.</>}
            </p>
          )}
          {tuningDiffers && !stringsDiffer && (
            <div className="tuning-card">
              <h3>Before you play: tune to the tab</h3>
              <p>
                This tab is written for <b>{fileTuning ? tuningName(fileTuning) : piece.tuning.map(noteName).join(" ")}</b>
                {piece.capo ? <>, capo {piece.capo}</> : null}.
              </p>
              {fileTuning ? (
                <button className="primary" onClick={() => onSettings({ ...settings, tuning: fileTuning, capo: piece.capo || 0 })}>
                  Tune to {tuningName(fileTuning)}
                </button>
              ) : (
                <p className="helper">Tune each string to those notes; this tuning isn't in the tuner's list yet.</p>
              )}
            </div>
          )}
          {piece.warnings.length > 0 && <ul className="helper">{piece.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}

          <Suspense fallback={<p className="helper">Loading the notation view…</p>}>
            {source?.bytes && <Notation bytes={source.bytes} track={track} tab={profile.openStrings.length > 0} />}
          </Suspense>
          {gpUrl && (
            <a className="download" href={gpUrl} download={`${piece.title}.gp`}>
              <Download size={14} /> Download as Guitar Pro (opens in Guitar Pro, TuxGuitar, MuseScore)
            </a>
          )}

          <h3 className="section-title">Hear it and play along</h3>
          <div className="transport">
            <button className="primary" disabled={recording || !piece.notes.length} onClick={() => (playing ? stop() : play())}>
              {playing ? <Pause size={15} /> : <Play size={15} />} {playing ? "Pause" : "Play the tab"}
            </button>
            <input
              aria-label="Position"
              type="range"
              min={0}
              max={duration}
              step={0.1}
              value={position}
              onChange={(e) => {
                setPosition(Number(e.target.value));
                if (playing) stop();
              }}
            />
            <span className="mono">{fmt(position)} · bar {barAt(position)}</span>
            <label className="speed">
              <input id="tab-click" type="checkbox" checked={clickOn} onChange={(e) => setClickOn(e.target.checked)} />
              <Timer size={13} /> Click
            </label>
            <label className="speed">
              <Gauge size={13} /> Speed
              <select id="tab-speed" value={speed} disabled={recording} onChange={(e) => setSpeed(Number(e.target.value))}>
                {SPEEDS.map((v) => <option key={v} value={v}>{Math.round(v * 100)}%</option>)}
              </select>
            </label>
          </div>
          <div className="loop">
            <label className="consent">
              <input id="tab-loop" type="checkbox" checked={loopOn} onChange={(e) => setLoopOn(e.target.checked)} />
              <span><Repeat size={12} /> Loop bars</span>
            </label>
            <input aria-label="Loop from bar" type="number" min={1} max={bars.length} value={fromBar} onChange={(e) => setFromBar(Math.max(1, Number(e.target.value)))} />
            <span>to</span>
            <input aria-label="Loop to bar" type="number" min={fromBar} max={bars.length} value={toBar} onChange={(e) => setToBar(Math.max(fromBar, Number(e.target.value)))} />
            <span className="helper">{fmt(range.start)}–{fmt(range.end)}</span>
          </div>

          <LatencyCheck recorder={recorder} latency={latency} disabled={recording} onBefore={stop} onMeasured={setLatency} />
          <label className="consent">
            <input id="tab-guide" type="checkbox" checked={guide} onChange={(e) => setGuide(e.target.checked)} />
            <span>Play the tab quietly in my headphones while I record (otherwise just the click)</span>
          </label>
          <div className="record-row">
            {!recording ? (
              <button className="primary" disabled={!piece.notes.length} onClick={recordAlong}>
                <Mic size={15} /> Record {loopOn ? `bars ${fromBar}–${toBar}` : "the whole piece"}
              </button>
            ) : (
              <button className="primary recording" onClick={() => rec.current?.stop()}>
                <Square size={15} /> Stop
              </button>
            )}
            {recording && <span className="job-stage"><span className="status-dot" /> Recording · bar {barAt(position)}</span>}
          </div>
          {take && (
            <div className="take-card">
              <p className="helper">{take.detail}</p>
              <div className="presets">
                <button onClick={hearTogether}><Headphones size={13} /> Hear me with the tab</button>
                <button onClick={() => setMixUrl(URL.createObjectURL(encodeWav(together(take), context().sampleRate)))}>
                  <Download size={13} /> Make a mix to keep
                </button>
                <button className="primary" onClick={compare}>Check my take against the tab</button>
              </div>
              {mixUrl && (
                <a className="download" href={mixUrl} download={`${piece.title} - with me.wav`}>
                  <Download size={14} /> Download (WAV)
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
