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
import { estimateOffset, mixInto, timeStretch } from "./songAudio";
import { renderFile, driveForProgram } from "./fileSound";
import { applySound, useGuitarSound } from "./guitarTone";
import GuitarSoundPicker from "./GuitarSoundPicker";
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
    [mixUrl, setMixUrl] = useState(""),
    // Whose sound plays the tab: the instruments the file asks for, or the app's own guitar.
    [voice, setVoice] = useState<"file" | "app">("file"),
    [band, setBand] = useState(true),
    [rendering, setRendering] = useState(false),
    [textTab, setTextTab] = useState(false),
    [sound, setSound] = useGuitarSound();
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
      setVoice("file");
      setTextTab(false);
      const drive = driveForProgram(p.program);
      if (drive) setSound({ ...sound, drive });
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
      setVoice("app");
      setTextTab(true);
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
    const drive = driveForProgram(p.program);
    if (drive) setSound({ ...sound, drive });
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

  /** The app's own guitar playing this track over [from, to) at `atSpeed`, with the chosen amp. */
  function synthTrack(from: number, to: number, sp: number, level = 1, withSound = true) {
    const rate = context().sampleRate,
      part = excerpt(piece!, from, to, 1);
    return synthesize(part.notes, rate, (to - from) / sp + 0.05, sp, 0.3 * level, withSound ? sound : undefined);
  }
  /**
   * What "Play" sounds like over [from, to): the file's own instruments (this track at `level`,
   * the rest of the band when chosen) or the app's guitar, then clicks. Stereo.
   */
  async function render(
    from: number,
    to: number,
    opts: { level?: number; click?: boolean; atSpeed?: number; band?: boolean; voice?: "file" | "app" } = {},
  ): Promise<[Float32Array, Float32Array]> {
    const rate = context().sampleRate,
      sp = opts.atSpeed ?? speed,
      level = opts.level ?? 1,
      withBand = opts.band ?? band,
      how = opts.voice ?? (score && source && !textTab ? voice : "app");
    let out: [Float32Array, Float32Array];
    if (how === "file" && score) {
      setRendering(true);
      try {
        const plain = sound.drive === "clean" && !sound.chorus && !sound.delay && !sound.reverb;
        let audio: [Float32Array, Float32Array];
        if (plain) audio = await renderFile(score, from, to, rate, (i) => (i === track ? level : withBand ? 1 : 0));
        else {
          // Many tabs ask for a clean electric even when the record is distorted: put this track
          // through the chosen amp and pedals, and leave the rest of the band as the file has it.
          const mine = await renderFile(score, from, to, rate, (i) => (i === track ? level : 0));
          mine.forEach((ch) => applySound(ch, rate, sound));
          audio = withBand ? await renderFile(score, from, to, rate, (i) => (i === track ? 0 : 1)) : [new Float32Array(mine[0].length), new Float32Array(mine[0].length)];
          mixInto(audio, mine, 1);
        }
        out = sp === 1 ? audio : (timeStretch(audio, rate, sp) as [Float32Array, Float32Array]);
      } finally {
        setRendering(false);
      }
    } else {
      const mono = synthTrack(from, to, sp, level);
      out = [mono, mono.slice()];
      if (withBand && score && source && !textTab) {
        // The rest of the band from the file, under the app's guitar.
        setRendering(true);
        try {
          const others = await renderFile(score, from, to, rate, (i) => (i === track ? 0 : 1));
          mixInto(out, sp === 1 ? others : timeStretch(others, rate, sp), 1);
        } finally {
          setRendering(false);
        }
      }
    }
    if (opts.click) addClicks(out, rate, clickTimes(piece!.beats, from, to), from, sp, 0.3);
    return out;
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
    const audio = await render(from, to, { click: clickOn });
    start(toBuffer(audio), c.currentTime + 0.05, from, speed, loopOn ? range : null);
    setPlaying(true);
    tick();
  }
  useEffect(() => {
    if (playing && !recording) play();
  }, [speed, clickOn, track, voice, band, sound]);

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
        backing = await render(from, to, { level: guide ? 0.45 : 0, click: clickOn || !(guide || band) }),
        // Attacks to line the take up with: the plain notes of this track.
        reference = synthTrack(from, to, speed, 1, false),
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
      const backingBuffer = toBuffer(backing);
      start(backingBuffer, songStart, from, speed, null);
      setPlaying(true);
      tick();
      const recordFrom = c.currentTime,
        length = backingBuffer.duration;
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

  async function together(t: Take) {
    const out = await render(t.from, t.to, { atSpeed: t.speed, level: 0.8 });
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
    start(toBuffer(await together(take)), c.currentTime + 0.05, take.from, take.speed, null);
    setPlaying(true);
    tick();
  }
  async function compare() {
    if (!take || !piece) return;
    const part = excerpt(piece, take.from, take.to, take.speed),
      ref = toBuffer(await render(take.from, take.to, { atSpeed: take.speed, band: false }));
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
          <div className="sound-choice">
            {score && source && !textTab && (
              <div className="segmented" role="radiogroup" aria-label="Who plays the tab">
                <button className={voice === "file" ? "chosen" : ""} onClick={() => setVoice("file")}>
                  The file's instruments
                </button>
                <button className={voice === "app" ? "chosen" : ""} onClick={() => setVoice("app")}>
                  The app's guitar
                </button>
              </div>
            )}
            {score && source && !textTab && piece.tracks.length > 1 && (
              <label className="speed">
                <input id="tab-band" type="checkbox" checked={band} onChange={(e) => setBand(e.target.checked)} />
                Whole band (every track in the file)
              </label>
            )}
            <GuitarSoundPicker
              sound={sound}
              onChange={setSound}
              note={
                driveForProgram(piece.program)
                  ? `The file asks for a ${driveForProgram(piece.program)} guitar${voice === "file" && !textTab ? "; the amp setting goes on top of this track" : ""}.`
                  : undefined
              }
            />
            {voice === "file" && score && !textTab && (
              <p className="helper">
                Played with the instruments the file names (General MIDI sounds), with repeats played out. Set the amp
                to match the record: many tabs ask for a clean guitar even when the record is distorted.
              </p>
            )}
          </div>
          <div className="transport">
            <button className="primary" disabled={recording || rendering || !piece.notes.length} onClick={() => (playing ? stop() : play())}>
              {playing ? <Pause size={15} /> : <Play size={15} />} {playing ? "Pause" : rendering ? "Preparing the sound…" : "Play the tab"}
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
            <span>Play my track quietly in my headphones while I record (the rest of the band plays at full level when "Whole band" is on)</span>
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
                <button onClick={hearTogether}><Headphones size={13} /> Hear me with the {band && score && !textTab ? "band" : "tab"}</button>
                <button onClick={async () => setMixUrl(URL.createObjectURL(encodeWav(await together(take), context().sampleRate)))}>
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
