import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  Upload,
  Link2,
  Play,
  Pause,
  Mic,
  Square,
  Download,
  Headphones,
  Music2,
  Repeat,
  SlidersHorizontal,
  Gauge,
  Timer,
  Search,
} from "lucide-react";
import {
  createSong,
  deleteSong,
  getSong,
  requestScore,
  locateTake,
  trackUrl,
  tuningName,
  type LocateResult,
  type Score,
  type Song,
  type SongPart,
} from "./songApi";
import {
  estimateOffset,
  loopRange,
  mixInto,
  buildTargets,
  targetSchedule,
  applySchedule,
  timeStretch,
  type Target,
} from "./songAudio";
import { encodeWav } from "./engineApi";
import { synthesize } from "./tabScore";
import { soundFromEstimate, useGuitarSound } from "./guitarTone";
import GuitarSoundPicker from "./GuitarSoundPicker";
import { addClicks, clickTimes, loadLatency, type LatencyResult } from "./practice";
import { Recorder } from "./recorder";
import LatencyCheck from "./LatencyCheck";
import type { TabSource } from "./TabLab";
import type { BarMark } from "./feedback";
import { captureError } from "./audioInputs";
import { MEDIA_ACCEPT, needsBrowserDecode, toWav } from "./audioFiles";
import { names } from "./analysis";
import {
  resolveInstrument,
  type InstrumentSettings,
} from "./instruments";
// alphaTab is large; load it only when someone opens the tab view.
const Notation = lazy(() => import("./Notation"));

type Clip = { name: string; buffer: AudioBuffer };
type Props = {
  settings: InstrumentSettings;
  onSettings: (next: InstrumentSettings) => void;
  onCompare: (reference: Clip, take: Clip, start: number, length: number, bars?: BarMark[]) => void;
  processing?: "cpu" | "gpu";
  /** Open the generated tab in the tab lesson, e.g. after correcting it in a tab editor. */
  onPracticeTab?: (source: TabSource) => void;
};
type Track = { id: string; label: string; verdict: string; isPart: boolean };
/** A recorded take; `speed` is the playback speed it was played along to. */
type Take = { buffer: AudioBuffer; start: number; end: number; speed: number; target: string; detail: string };
/** What the speakers play: the mixer as set, only the chosen part, or the band without it. */
type Listen = "mixer" | "only" | "without";

const GUIDE_LEVEL = 0.25;
const SPEEDS = [1, 0.9, 0.8, 0.75, 0.7, 0.6, 0.5];

export default function SongLab({ settings, onSettings, onCompare, processing = "cpu", onPracticeTab }: Props) {
  const profile = resolveInstrument(settings);
  const [mode, setMode] = useState<"file" | "url">("file"),
    [file, setFile] = useState<File | null>(null),
    [url, setUrl] = useState(""),
    [consent, setConsent] = useState(false),
    [song, setSong] = useState<Song | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [buffers, setBuffers] = useState<Record<string, AudioBuffer>>({}),
    [loading, setLoading] = useState(false),
    [solo, setSolo] = useState<string | null>(null),
    [muted, setMuted] = useState<string[]>([]),
    [listen, setListen] = useState<Listen>("mixer"),
    [targetId, setTargetId] = useState(""),
    [speed, setSpeed] = useState(1),
    [preparing, setPreparing] = useState(false),
    [playing, setPlaying] = useState(false),
    [position, setPosition] = useState(0),
    [loopOn, setLoopOn] = useState(false),
    [fromBar, setFromBar] = useState(1),
    [toBar, setToBar] = useState(4),
    [guide, setGuide] = useState(false),
    [scorePart, setScorePart] = useState("all"),
    [scoreRole, setScoreRole] = useState("any"),
    [score, setScore] = useState<Score | null>(null),
    [scoreBusy, setScoreBusy] = useState(false),
    [recording, setRecording] = useState(false),
    [take, setTake] = useState<Take | null>(null),
    [mixUrl, setMixUrl] = useState(""),
    [clickOn, setClickOn] = useState(false),
    [latency, setLatency] = useState<LatencyResult | null>(() => loadLatency()),
    [locating, setLocating] = useState(false),
    [located, setLocated] = useState<(LocateResult & { buffer: AudioBuffer }) | null>(null),
    [songTone, setSongTone] = useState<"auto" | "clean" | "crunch" | "distorted">("auto"),
    [scorePlaying, setScorePlaying] = useState<"" | "part" | "written" | "both">(""),
    [sound, setSound] = useGuitarSound();
  const ctx = useRef<AudioContext | null>(null),
    current = useRef<AudioBufferSourceNode | null>(null),
    clock = useRef({ context: 0, song: 0, speed: 1, loop: null as null | { start: number; end: number } }),
    raf = useRef(0),
    songId = useRef<string | null>(null),
    rec = useRef<Recorder | null>(null);

  const result = song?.status === "complete" ? song.result : null;
  const parts: SongPart[] = result?.parts ?? [];
  const bars = result?.tempo.bars ?? [];
  const duration = result?.duration ?? 0;
  const targets: Target[] = useMemo(
    () => (result ? buildTargets(result.parts, profile.name) : []),
    [result, profile.name],
  );
  const target = targets.find((t) => t.id === targetId) ?? targets[0];
  const tracks: Track[] = useMemo(() => {
    if (!result) return [];
    const list: Track[] = [];
    for (const row of result.instruments) {
      if (row.verdict === "absent") continue;
      if (row.stem === result.selected_stem && result.parts.length > 1)
        result.parts.forEach((p) =>
          list.push({ id: p.id, label: p.label, verdict: p.role === "silent" ? "trace" : row.verdict, isPart: true }),
        );
      else
        list.push({
          id: row.stem,
          label: row.label,
          verdict: row.verdict,
          isPart: row.stem === result.selected_stem,
        });
    }
    return list;
  }, [result]);
  const range = loopOn
    ? loopRange(bars, fromBar, toBar, duration)
    : { start: 0, end: duration };

  const context = () =>
    ctx.current ??
    (ctx.current = new AudioContext({ latencyHint: "interactive" }));

  // ---------------------------------------------------------------- lifecycle
  useEffect(
    () => () => {
      stop();
      rec.current?.release();
      if (songId.current) deleteSong(songId.current).catch(() => {});
      ctx.current?.close().catch(() => {});
    },
    [],
  );
  useEffect(() => () => {
    if (mixUrl) URL.revokeObjectURL(mixUrl);
  }, [mixUrl]);
  // The tab view follows the part the player takes over.
  useEffect(() => {
    if (!target) return;
    setScorePart(target.parts.length === 1 ? target.parts[0] : "all");
    setScoreRole(target.role);
  }, [target?.id]);

  async function breakDown() {
    setError("");
    setBusy(true);
    stop();
    try {
      if (songId.current) await deleteSong(songId.current).catch(() => {});
      songId.current = null;
      setSong(null);
      setBuffers({});
      setScore(null);
      setTake(null);
      // WebM, MP4, M4A and similar: decode the sound here so the engine doesn't need ffmpeg.
      let upload = file;
      if (mode === "file" && file && needsBrowserDecode(file.name)) {
        setSong({ id: "", name: file.name, instrument: settings.instrument, status: "queued", stage: "Reading the sound from your file", error: null, result: null, expires_at: 0 });
        upload = await toWav(file, context()).catch(() => file);
      }
      const created = await createSong(
        mode === "file" ? { file: upload! } : { url: url.trim() },
        settings.instrument,
        processing,
        profile.openStrings.length ? songTone : "auto",
      );
      songId.current = created.id;
      setSong(created);
      let latest = created;
      while (!["complete", "failed"].includes(latest.status)) {
        await new Promise((r) => setTimeout(r, 1500));
        if (songId.current !== created.id) return;
        latest = await getSong(created.id);
        setSong(latest);
      }
      if (latest.status === "failed")
        throw Error(latest.error ?? "The breakdown stopped.");
      const r = latest.result!;
      setTargetId(buildTargets(r.parts, profile.name)[0]?.id ?? "");
      setSound(soundFromEstimate(r.tone, sound));
      setSolo(null);
      setMuted([]);
      setListen("mixer");
      setFromBar(1);
      setToBar(Math.min(4, r.tempo.bars.length));
      await loadTracks(latest);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadTracks(s: Song) {
    setLoading(true);
    try {
      const r = s.result!;
      const ids = new Set<string>();
      r.instruments.forEach((row) => row.verdict !== "absent" && ids.add(row.stem));
      r.parts.forEach((p) => ids.add(p.id));
      const decoded: Record<string, AudioBuffer> = {};
      await Promise.all(
        [...ids].map(async (id) => {
          const response = await fetch(trackUrl(s.id, id));
          if (!response.ok) throw Error(`Could not load the ${id} track.`);
          decoded[id] = await context().decodeAudioData(await response.arrayBuffer());
        }),
      );
      setBuffers(decoded);
    } finally {
      setLoading(false);
    }
  }

  // ---------------------------------------------------------------- rendering
  function mixerGain(id: string) {
    if (solo) return solo === id ? 1 : 0;
    return muted.includes(id) ? 0 : 1;
  }

  /**
   * Render [from, to) of the song to stereo channel data, as heard in `how`, then slow it
   * down without changing pitch. The guitar parts follow the chosen target; other
   * instruments play in full (or are silent when only the target is wanted).
   */
  function render(
    how: Listen,
    from: number,
    to: number,
    rate: number,
    opts: { guide?: boolean; speed?: number; click?: boolean } = {},
  ) {
    const atSpeed = opts.speed ?? speed;
    const frames = Math.max(1, Math.ceil((to - from) * rate)),
      out: [Float32Array, Float32Array] = [new Float32Array(frames), new Float32Array(frames)];
    const shift = (pts: { time: number; gain: number }[]) => pts.map((p) => ({ time: p.time - from, gain: p.gain }));
    for (const t of tracks) {
      const buffer = buffers[t.id];
      if (!buffer) continue;
      const startFrame = Math.round(from * buffer.sampleRate);
      const chans = Array.from({ length: buffer.numberOfChannels }, (_, c) =>
        buffer.getChannelData(c).subarray(startFrame, startFrame + frames),
      );
      const part = parts.find((p) => p.id === t.id);
      if (how === "mixer") {
        const g = mixerGain(t.id);
        if (g) mixInto(out, chans, g);
        continue;
      }
      if (!part || !target) {
        // Drums, bass, vocals...: the band keeps them; "only my part" drops them.
        if (how === "without") mixInto(out, chans, 1);
        continue;
      }
      const sched = targetSchedule(target, part, parts, how);
      if (!sched) mixInto(out, chans, 1);
      else if (!(sched.length === 1 && sched[0].gain === 0)) mixInto(out, applySchedule(chans, buffer.sampleRate, shift(sched)), 1);
      if (how === "without" && opts.guide) {
        const only = targetSchedule(target, part, parts, "only");
        if (!only) mixInto(out, chans, GUIDE_LEVEL);
        else if (!(only.length === 1 && only[0].gain === 0))
          mixInto(out, applySchedule(chans, buffer.sampleRate, shift(only)), GUIDE_LEVEL);
      }
    }
    const result = atSpeed === 1 ? out : (timeStretch(out, rate, atSpeed) as [Float32Array, Float32Array]);
    // Clicks go in after stretching so they stay short and crisp at any speed.
    if (opts.click) addClicks(result, rate, clickTimes(result_beats(), from, to), from, atSpeed);
    return result;
  }

  function result_beats() {
    return result?.tempo.beats ?? [];
  }

  function toBuffer(channels: Float32Array[], rate: number) {
    const c = context(),
      b = c.createBuffer(channels.length, Math.max(1, channels[0].length), rate);
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
    setScorePlaying("");
  }

  /** Start one rendered buffer at `when`; the clock maps context time back to song time. */
  function start(buffer: AudioBuffer, when: number, songFrom: number, playSpeed: number, loop: null | { start: number; end: number }) {
    const c = context(),
      source = c.createBufferSource();
    source.buffer = buffer;
    source.loop = !!loop;
    source.connect(c.destination);
    source.start(when);
    source.onended = () => {
      if (current.current === source) stop();
    };
    current.current = source;
    clock.current = { context: when, song: songFrom, speed: playSpeed, loop };
  }

  function tick() {
    const c = ctx.current;
    if (!c) return;
    const { context: t0, song: s0, speed: sp, loop } = clock.current;
    let t = s0 + Math.max(0, c.currentTime - t0) * sp;
    if (loop && t > loop.end) t = loop.start + ((t - loop.start) % (loop.end - loop.start));
    setPosition(Math.max(0, Math.min(duration, t)));
    raf.current = requestAnimationFrame(tick);
  }

  async function play(how: Listen = listen) {
    stop();
    const c = context();
    await c.resume();
    const from = loopOn ? range.start : position >= duration - 0.2 ? 0 : position;
    const to = loopOn ? range.end : duration;
    setPreparing(speed !== 1);
    await new Promise((r) => setTimeout(r, 0));
    try {
      const audio = toBuffer(render(how, from, to, c.sampleRate, { click: clickOn }), c.sampleRate);
      start(audio, c.currentTime + 0.05, from, speed, loopOn ? range : null);
      setPlaying(true);
      tick();
    } finally {
      setPreparing(false);
    }
  }

  function choose(next: Listen) {
    setListen(next);
    if (next !== "mixer") {
      setSolo(null);
      setMuted([]);
    }
  }
  // Re-render when what is heard changes mid-playback.
  useEffect(() => {
    if (playing && !recording) play();
  }, [solo, muted, listen, targetId, speed, clickOn]);

  // ---------------------------------------------------------------- play along + record
  const recorder = () => rec.current ?? (rec.current = new Recorder(context()));

  // ---------------------------------------------------------------- an earlier recording
  /** Upload a recording made elsewhere; find where in the song it belongs, then use it as a take. */
  async function findTake(file: File) {
    if (!song || !target) return;
    setError("");
    setLocated(null);
    setLocating(true);
    stop();
    try {
      const c = context(),
        decoded = await c.decodeAudioData(await file.arrayBuffer()),
        mono = new Float32Array(decoded.length);
      for (let ch = 0; ch < decoded.numberOfChannels; ch++) {
        const d = decoded.getChannelData(ch);
        for (let i = 0; i < d.length; i++) mono[i] += d[i] / decoded.numberOfChannels;
      }
      const buffer = c.createBuffer(1, mono.length, c.sampleRate);
      buffer.getChannelData(0).set(mono);
      const found = await locateTake(song.id, encodeWav([mono], c.sampleRate), target.parts, target.role);
      setLocated({ ...found, buffer });
      if (found.candidates[0]) useLocated(buffer, found.candidates[0].start);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLocating(false);
    }
  }

  function useLocated(buffer: AudioBuffer, start: number) {
    if (!target) return;
    const end = Math.min(duration, start + buffer.duration);
    setTake({
      buffer,
      start,
      end,
      speed: 1,
      target: target.id,
      detail: `Placed at ${Math.floor(start / 60)}:${String(Math.floor(start % 60)).padStart(2, "0")} (bar ${barAt(start)}) by matching its notes to the original.`,
    });
    setMixUrl("");
  }

  async function recordAlong() {
    if (!target) return;
    setError("");
    setTake(null);
    setMixUrl("");
    stop();
    try {
      const c = context();
      await c.resume();
      await recorder().ensure();
      setPreparing(speed !== 1);
      await new Promise((r) => setTimeout(r, 0));
      const band = toBuffer(render("without", range.start, range.end, c.sampleRate, { guide, click: clickOn }), c.sampleRate);
      const reference = render("only", range.start, range.end, c.sampleRate);
      setPreparing(false);
      const beat = 60 / (result!.tempo.bpm || 100) / speed,
        countIn = 4 * beat,
        length = band.duration,
        now = c.currentTime + 0.15,
        songStart = now + countIn;
      // Count-in clicks at the practice tempo, accented on beat one.
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
      start(band, songStart, range.start, speed, null);
      setPlaying(true);
      tick();
      const recordFrom = c.currentTime;
      const totalFrames = Math.ceil((songStart - recordFrom + length + 0.6) * c.sampleRate);
      setRecording(true);
      const raw = await recorder().capture(totalFrames, length + countIn + 10);
      setRecording(false);
      stop();
      // Trim to the song start, then remove the delay: the measured one if this device has
      // been calibrated, otherwise what the browser reports (often an underestimate).
      const reported = recorder().delay(latency);
      const lead = Math.round((songStart - recordFrom + reported) * c.sampleRate);
      const aligned = raw.subarray(Math.min(raw.length, Math.max(0, lead)));
      // Refine against the music being replaced: attack-envelope cross-correlation.
      const refMono = new Float32Array(Math.min(aligned.length, reference[0].length));
      for (let i = 0; i < refMono.length; i++) refMono[i] = (reference[0][i] + reference[1][i]) / 2;
      const est = estimateOffset(refMono, aligned.subarray(0, refMono.length), c.sampleRate, 0.3);
      const shiftFrames = est ? Math.round(est.seconds * c.sampleRate) : 0;
      const final = aligned.subarray(Math.max(0, shiftFrames), Math.max(0, shiftFrames) + Math.round(length * c.sampleRate));
      const buffer = c.createBuffer(1, Math.max(1, final.length), c.sampleRate);
      buffer.getChannelData(0).set(final);
      setTake({
        buffer,
        start: range.start,
        end: range.end,
        speed,
        target: target.id,
        detail:
          (est
            ? `Lined up automatically: ${Math.round(reported * 1000)} ms ${latency?.ok ? "measured" : "reported"} device delay + ${Math.round(est.seconds * 1000)} ms from matching your attacks to the original.`
            : `Lined up using the ${Math.round(reported * 1000)} ms delay ${latency?.ok ? "measured on this device" : "your device reports"}. Your take did not match the original closely enough to fine-tune.`) +
          (speed !== 1 ? ` Recorded at ${Math.round(speed * 100)}% speed.` : ""),
      });
    } catch (e) {
      setRecording(false);
      setPreparing(false);
      stop();
      setError(captureError(e));
    }
  }

  /** The band without the replaced music, with the player's take dropped in its place. */
  function bandWithTake(t: Take) {
    // Render at the speed the take was played at, so both line up.
    const band = render("without", t.start, t.end, context().sampleRate, { speed: t.speed });
    mixInto(band, [t.buffer.getChannelData(0)], 1);
    let peak = 0;
    for (const ch of band) for (const v of ch) peak = Math.max(peak, Math.abs(v));
    if (peak > 0.99) for (const ch of band) for (let i = 0; i < ch.length; i++) ch[i] *= 0.99 / peak;
    return band;
  }

  async function hearTake() {
    if (!take) return;
    stop();
    const c = context();
    await c.resume();
    start(toBuffer(bandWithTake(take), c.sampleRate), c.currentTime + 0.05, take.start, take.speed, null);
    setPlaying(true);
    tick();
  }

  function exportMix() {
    if (!take) return;
    const sr = context().sampleRate;
    setMixUrl(URL.createObjectURL(encodeWav(bandWithTake(take), sr)));
  }

  function compareTake() {
    if (!take || !song) return;
    const c = context(),
      replaced = targets.find((t) => t.id === take.target) ?? target;
    const reference = render("only", take.start, take.end, c.sampleRate, { speed: take.speed });
    onCompare(
      { name: `${song.name} · ${replaced?.label ?? "isolated part"}`, buffer: toBuffer(reference, c.sampleRate) },
      { name: "Play-along take", buffer: take.buffer },
      0,
      Math.min(60, take.buffer.duration),
      // Bar numbers in the take's own time (it may have been played slower).
      bars
        .map((b, i) => ({ number: i + 1, time: (b - take.start) / take.speed }))
        .filter((b) => b.time > -0.05 && b.time < take.buffer.duration - 0.1)
        .map((b) => ({ ...b, time: Math.max(0, b.time) })),
    );
  }

  // ---------------------------------------------------------------- tab + notation
  async function showScore() {
    if (!song) return;
    setScoreBusy(true);
    setError("");
    try {
      setScore(
        await requestScore(song.id, {
          part: scorePart,
          role: scoreRole,
          tuning: settings.tuning,
          capo: settings.capo,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setScoreBusy(false);
    }
  }
  const xmlUrl = useMemo(
    () =>
      score
        ? URL.createObjectURL(new Blob([score.musicxml], { type: "application/vnd.recordare.musicxml+xml" }))
        : "",
    [score],
  );
  useEffect(() => () => {
    if (xmlUrl) URL.revokeObjectURL(xmlUrl);
  }, [xmlUrl]);

  /**
   * Hear the written-out part: the separated audio the app transcribed, the notes as written
   * (on the app's guitar, through the chosen amp), or both (separated left, written right).
   */
  async function playScore(which: "part" | "written" | "both") {
    if (!score || !result) return;
    if (scorePlaying === which) return stop();
    stop();
    const c = context();
    await c.resume();
    const rate = c.sampleRate,
      from = position >= duration - 0.2 ? 0 : position,
      frames = Math.max(1, Math.ceil((duration - from) * rate));
    const ids = score.part === "all" ? (parts.length ? parts.map((p) => p.id) : [result.selected_stem]) : [score.part];
    const separated: [Float32Array, Float32Array] = [new Float32Array(frames), new Float32Array(frames)];
    for (const id of ids) {
      const b = buffers[id] ?? buffers[result.selected_stem];
      if (!b) continue;
      const at = Math.round(from * b.sampleRate);
      mixInto(separated, Array.from({ length: b.numberOfChannels }, (_, ch) => b.getChannelData(ch).subarray(at, at + frames)), 1);
    }
    const notes = score.notes
      .filter((n) => n.string != null && n.time + n.duration > from)
      .map((n) => ({ ...n, time: n.time - from }));
    const written = synthesize(notes, rate, duration - from, 1, 0.3, sound);
    const left = which === "written" ? written : separated[0],
      right = which === "part" ? separated[1] : which === "written" ? written : written;
    if (which === "both") {
      // Separated part in the left ear, the notes as written in the right.
      const mono = separated[0].map((v, i) => 0.5 * (v + separated[1][i]));
      left.set(mono.subarray(0, left.length));
    }
    start(toBuffer([left, right], rate), c.currentTime + 0.05, from, 1, null);
    setPlaying(true);
    setScorePlaying(which);
    tick();
  }

  const tuning = result?.tuning;
  const songInstrumentMismatch = song && song.instrument !== settings.instrument;
  const fmt = (t: number) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}`;
  const flatNames = ["C", "D♭", "D", "E♭", "E", "F", "G♭", "G", "A♭", "A", "B♭", "B"];
  const noteName = (m: number) =>
    ((result?.key?.fifths ?? 0) < 0 || settings.tuning.includes("half_step") || settings.tuning.includes("c_sharp") ? flatNames : names)[m % 12] +
    (Math.floor(m / 12) - 1);
  const barAt = (t: number) => Math.max(1, bars.filter((b) => b <= t + 1e-3).length);

  return (
    <section className="panel song-lab" aria-labelledby="song-lab-title">
      <div className="eyebrow">LEARN A SONG</div>
      <h2 id="song-lab-title">Break a song into its instruments</h2>
      <p className="panel-desc">
        Add a song you want to learn. We separate every instrument, find your{" "}
        {profile.name.toLowerCase()} part, suggest the tuning, and write out tab and notation. Then play along
        with the band while your part is muted.
      </p>

      <div className="segmented" role="tablist" aria-label="Song source">
        <button className={mode === "file" ? "chosen" : ""} onClick={() => setMode("file")} disabled={busy}>
          <Upload size={13} /> Upload a file
        </button>
        <button className={mode === "url" ? "chosen" : ""} onClick={() => setMode("url")} disabled={busy}>
          <Link2 size={13} /> Link to an audio file
        </button>
      </div>
      {mode === "file" ? (
        <label className={"drop " + (file ? "loaded" : "")}>
          <input
            id="song-file"
            type="file"
            accept={MEDIA_ACCEPT}
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <span className="upload-icon"><Music2 size={22} /></span>
          <strong>{file ? file.name : "Choose the song"}</strong>
          <span>MP3, WAV, FLAC, OGG, M4A, or the sound of a WebM/MP4 video · up to 10 minutes</span>
        </label>
      ) : (
        <div className="song-url">
          <input
            id="song-url"
            type="url"
            inputMode="url"
            placeholder="https://example.com/my-song.mp3"
            value={url}
            disabled={busy}
            onChange={(e) => setUrl(e.target.value)}
          />
          <small>
            A direct link to an audio file you have the right to use. YouTube, Spotify and other streaming links
            can't be used: their terms forbid downloading and the audio is protected.
          </small>
        </div>
      )}
      {profile.openStrings.length > 0 && (
        <label className="speed song-tone">
          Guitar sound in this song
          <select id="song-tone" value={songTone} disabled={busy} onChange={(e) => setSongTone(e.target.value as typeof songTone)}>
            <option value="auto">Work it out for me</option>
            <option value="clean">Clean</option>
            <option value="crunch">Crunch / light overdrive</option>
            <option value="distorted">Distorted / high gain</option>
          </select>
          <small className="helper">Distortion hides note starts; telling us helps the transcription catch more notes.</small>
        </label>
      )}
      <label className="consent">
        <input
          id="song-consent"
          type="checkbox"
          checked={consent}
          disabled={busy}
          onChange={(e) => setConsent(e.target.checked)}
        />
        <span>
          Upload this song to the analysis server. It is kept for one hour, then deleted, and is never shared or
          used for training.
        </span>
      </label>
      <button
        className="primary"
        disabled={busy || !consent || (mode === "file" ? !file : !url.trim())}
        onClick={breakDown}
      >
        {busy ? "Working…" : `Break it down for ${profile.name.toLowerCase()}`} <SlidersHorizontal size={15} />
      </button>
      {song && !result && (
        <p className="job-stage" role="status">
          <span className="status-dot" /> {song.stage}
          {song.status === "separating" && " · a 4-minute song takes a few minutes on a CPU"}
        </p>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      {result && (
        <div className="song-results">
          {songInstrumentMismatch && (
            <p className="notice-strong">
              This breakdown was made for {song!.instrument}. Break it down again to get the {profile.name.toLowerCase()} part.
            </p>
          )}

          <div className="song-facts">
            <div><small>Key</small><b>{result.key?.key ?? "Unclear"}</b>{result.key && <span className={"chip " + result.key.confidence}>{result.key.confidence}</span>}</div>
            <div><small>Tempo</small><b>{result.tempo.bpm} BPM</b><span className="chip">{result.tempo.time_signature}</span></div>
            <div><small>Length</small><b>{fmt(duration)}</b><span className="chip">{bars.length} bars</span></div>
          </div>
          {result.key && result.key.confidence !== "high" && (
            <p className="helper">Could also be {result.key.alternatives.join(" or ")}.</p>
          )}

          {tuning && profile.openStrings.length > 0 && (
            <div className="tuning-card">
              <h3>Before you play: tune to the song</h3>
              <p>
                Suggested: <b>{tuningName(tuning.suggested)}</b>
                {Math.abs(tuning.reference_cents) >= 15 && <> at A4 = {tuning.reference_a4_hz} Hz</>}
              </p>
              <ul>{tuning.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <div className="tuning-actions">
                <button
                  className="primary"
                  disabled={settings.tuning === tuning.suggested && (settings.referenceCents ?? 0) === (Math.abs(tuning.reference_cents) >= 15 ? tuning.reference_cents : 0)}
                  onClick={() =>
                    onSettings({
                      ...settings,
                      tuning: tuning.suggested,
                      referenceCents: Math.abs(tuning.reference_cents) >= 15 ? tuning.reference_cents : 0,
                    })
                  }
                >
                  {settings.tuning === tuning.suggested ? "Tuning set" : `Tune to ${tuningName(tuning.suggested)}`}
                </button>
                {tuning.options.length > 1 && (
                  <select
                    aria-label="Other tunings that fit"
                    value=""
                    onChange={(e) => e.target.value && onSettings({ ...settings, tuning: e.target.value })}
                  >
                    <option value="">Other tunings that fit…</option>
                    {tuning.options.slice(1).map((t) => <option key={t} value={t}>{tuningName(t)}</option>)}
                  </select>
                )}
              </div>
              <p className="helper">
                Then switch on the tuner under "Your take" and play each open string: {profile.openStrings.map((m) => noteName(m)).join(" · ")}.
              </p>
            </div>
          )}

          <h3 className="section-title">What's in this song</h3>
          {loading && <p className="helper">Loading the separated tracks…</p>}
          <div className="mixer" role="group" aria-label="Instrument mixer">
            {tracks.map((t) => {
              const part = parts.find((p) => p.id === t.id);
              const audible = listen !== "mixer" || mixerGain(t.id) > 0;
              const inTarget = !!target?.parts.includes(t.id);
              return (
                <div key={t.id} className={"mixer-row " + (audible ? "" : "silent ") + (inTarget ? "mine" : "")}>
                  <div className="mixer-name">
                    <b>{t.label}</b>
                    <small>
                      {t.verdict === "trace" ? "faint / mostly bleed" : "detected"}
                      {part && part.role !== "silent" && ` · ${part.role}`}
                      {part?.doubled && " · same part double-tracked"}
                    </small>
                  </div>
                  <button
                    aria-pressed={listen === "mixer" && solo === t.id}
                    className={listen === "mixer" && solo === t.id ? "on" : ""}
                    onClick={() => { setListen("mixer"); setSolo(solo === t.id ? null : t.id); }}
                  >
                    Solo
                  </button>
                  <button
                    aria-pressed={listen === "mixer" && muted.includes(t.id)}
                    className={listen === "mixer" && muted.includes(t.id) ? "on" : ""}
                    onClick={() => { setListen("mixer"); setMuted(muted.includes(t.id) ? muted.filter((m) => m !== t.id) : [...muted, t.id]); }}
                  >
                    Mute
                  </button>
                </div>
              );
            })}
          </div>
          {targets.length > 0 && (
            <div className="part-picker">
              <label>
                What I'll play
                <select id="my-part" value={target?.id ?? ""} onChange={(e) => setTargetId(e.target.value)}>
                  {targets.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.label} · {t.detail}
                    </option>
                  ))}
                </select>
              </label>
              {parts.length > 1 && (
                <p className="helper">
                  We found {parts.filter((p) => p.role !== "silent").length} {profile.name.toLowerCase()} parts by where they sit in the stereo
                  mix, and marked each bar as lead or rhythm. Pick one guitar, or every lead passage whichever guitar plays it.
                  Two parts at the same spot playing at the same time can't be pulled apart.
                </p>
              )}
            </div>
          )}
          <div className="presets" role="group" aria-label="What to hear">
            <button className={listen === "mixer" && !solo && !muted.length ? "on" : ""} onClick={() => choose("mixer")}>Full song</button>
            <button className={listen === "only" ? "on" : ""} onClick={() => choose("only")}>Only what I'll play</button>
            <button className={listen === "without" ? "on" : ""} onClick={() => choose("without")}>Band without it</button>
          </div>

          <div className="transport">
            <button className="primary" disabled={loading || recording || preparing || !Object.keys(buffers).length} onClick={() => (playing ? stop() : play())}>
              {playing ? <Pause size={15} /> : <Play size={15} />} {preparing ? "Preparing…" : playing ? "Pause" : "Play"}
            </button>
            <input
              aria-label="Song position"
              type="range"
              min={0}
              max={duration}
              step={0.1}
              value={position}
              onChange={(e) => { setPosition(Number(e.target.value)); if (playing) stop(); }}
            />
            <span className="mono">{fmt(position)} · bar {barAt(position)}</span>
            <label className="speed">
              <input id="click-on" type="checkbox" checked={clickOn} onChange={(e) => setClickOn(e.target.checked)} />
              <Timer size={13} /> Click
            </label>
            <label className="speed">
              <Gauge size={13} /> Speed
              <select id="speed" value={speed} disabled={recording} onChange={(e) => setSpeed(Number(e.target.value))}>
                {SPEEDS.map((v) => <option key={v} value={v}>{Math.round(v * 100)}%</option>)}
              </select>
            </label>
          </div>
          {speed !== 1 && (
            <p className="helper">
              Slowed to {Math.round(speed * 100)}% without changing pitch, so you can still tune and play along in key.
            </p>
          )}
          <div className="loop">
            <label className="consent">
              <input id="loop-on" type="checkbox" checked={loopOn} onChange={(e) => setLoopOn(e.target.checked)} />
              <span><Repeat size={12} /> Loop bars</span>
            </label>
            <input aria-label="Loop from bar" type="number" min={1} max={bars.length} value={fromBar} onChange={(e) => setFromBar(Math.max(1, Number(e.target.value)))} />
            <span>to</span>
            <input aria-label="Loop to bar" type="number" min={fromBar} max={bars.length} value={toBar} onChange={(e) => setToBar(Math.max(fromBar, Number(e.target.value)))} />
            <span className="helper">{fmt(range.start)}–{fmt(range.end)}</span>
          </div>

          <div className="chord-strip" aria-label="Chords">
            {result.chords.filter((c) => c.chord !== "N").map((c, i) => (
              <button key={i} className={position >= c.start && position < c.end ? "now" : ""} onClick={() => setPosition(c.start)}>
                <b>{c.chord}</b><small>bar {barAt(c.start)}</small>
              </button>
            ))}
          </div>

          <h3 className="section-title">Tab and notation</h3>
          <div className="score-controls">
            {parts.length > 1 && (
              <label>
                Part
                <select id="score-part" value={scorePart} onChange={(e) => setScorePart(e.target.value)}>
                  <option value="all">All {profile.name.toLowerCase()} parts</option>
                  {parts.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </label>
            )}
            <label>
              Passages
              <select id="score-role" value={scoreRole} onChange={(e) => setScoreRole(e.target.value)}>
                <option value="any">Everything</option>
                <option value="lead">Lead passages only (any {profile.name.toLowerCase()})</option>
                <option value="rhythm">Rhythm / chords only</option>
              </select>
            </label>
            <span className="helper">Tab for {tuningName(settings.tuning)}{settings.capo ? `, capo ${settings.capo}` : ""}</span>
            <button className="primary" disabled={scoreBusy} onClick={showScore}>
              {scoreBusy ? "Writing it out…" : "Show tab & notation"}
            </button>
          </div>
          {score && (
            <div className="score">
              <p className="helper">
                {score.label} · {score.notes.length} notes · {score.key?.key ?? ""} · {score.tempo.bpm} BPM. Automatic transcription:
                check it by ear and against a trusted source before relying on it.
              </p>
              {score.unplayable_notes > 0 && (
                <p className="notice-strong">
                  {score.unplayable_notes} {score.unplayable_notes === 1 ? "note is" : "notes are"} below the lowest string in{" "}
                  {tuningName(settings.tuning)}, so {score.unplayable_notes === 1 ? "it is" : "they are"} left out of the tab and
                  notation. Often that's bass bleeding into the guitar part; if the song really goes that low, use the
                  suggested tuning above.
                </p>
              )}
              <div className="score-listen">
                <p className="helper">
                  Listen from {fmt(position >= duration - 0.2 ? 0 : position)}: compare what the app separated with what it wrote down.
                </p>
                <div className="presets">
                  {(["part", "written", "both"] as const).map((w) => (
                    <button key={w} className={scorePlaying === w ? "on" : ""} disabled={loading} onClick={() => playScore(w)}>
                      {scorePlaying === w ? <Square size={13} /> : <Play size={13} />}{" "}
                      {w === "part" ? "What it heard (separated part)" : w === "written" ? "The tab as written" : "Both (heard left, written right)"}
                    </button>
                  ))}
                </div>
                <GuitarSoundPicker sound={sound} onChange={setSound} detected={result.tone} />
              </div>
              <Suspense fallback={<p className="helper">Loading the notation view…</p>}>
                <Notation musicxml={score.musicxml} tab={profile.openStrings.length > 0} />
              </Suspense>
              <a className="download" href={xmlUrl} download={`${song!.name.replace(/\.[^.]+$/, "")} - ${score.label}.musicxml`}>
                <Download size={14} /> Download MusicXML (opens in MuseScore, Guitar Pro, Sibelius)
              </a>
              {onPracticeTab && (
                <div className="presets">
                  <button
                    onClick={() =>
                      onPracticeTab({ name: `${song!.name.replace(/\.[^.]+$/, "")} - ${score.label}`, musicxml: score.musicxml })
                    }
                  >
                    Practise from this tab
                  </button>
                </div>
              )}
              <p className="helper">
                Notes look wrong? Download the MusicXML, fix it in MuseScore or Guitar Pro, then load it under "Learn from a tab
                or score" below. Or use a tab you already have.
              </p>
            </div>
          )}

          <h3 className="section-title">Play along and record</h3>
          <p className="panel-desc">
            Wear headphones. You get a four-beat count-in, then the band plays without{" "}
            <b>{target ? target.label.toLowerCase() : "your part"}</b>
            {loopOn ? ` for bars ${fromBar}–${toBar}` : " for the whole song"}
            {speed !== 1 ? ` at ${Math.round(speed * 100)}% speed` : ""} while we record you. Afterwards your take
            drops into the song in its place.
          </p>
          <LatencyCheck
            recorder={recorder}
            latency={latency}
            disabled={recording}
            onBefore={stop}
            onMeasured={setLatency}
          />
          <label className="consent">
            <input id="guide" type="checkbox" checked={guide} onChange={(e) => setGuide(e.target.checked)} />
            <span>Keep the original quietly in my headphones as a guide</span>
          </label>
          <div className="record-row">
            {!recording ? (
              <button className="primary" disabled={loading || preparing || !target || !Object.keys(buffers).length} onClick={recordAlong}>
                <Mic size={15} /> Play along & record
              </button>
            ) : (
              <button className="primary recording" onClick={() => rec.current?.stop()}>
                <Square size={15} /> Stop
              </button>
            )}
            {recording && <span className="job-stage"><span className="status-dot" /> Recording · bar {barAt(position)}</span>}
          </div>
          <label className="drop compact">
            <input
              id="earlier-take"
              type="file"
              accept={MEDIA_ACCEPT}
              disabled={locating || recording}
              onChange={(e) => e.target.files?.[0] && findTake(e.target.files[0])}
            />
            <Search size={15} />
            <span>{locating ? "Finding where it fits…" : "Or upload a recording you made earlier and we'll find where it fits"}</span>
          </label>
          {located && (
            <div className="located" role="status">
              <p className="helper">
                {located.confidence === "repeated"
                  ? "This part repeats in the song. Pick the right place:"
                  : located.confidence === "low"
                    ? "Not a confident match. Check the place, or pick another:"
                    : "Found it:"}
              </p>
              <div className="presets">
                {located.candidates.map((c, i) => (
                  <button
                    key={i}
                    className={take?.buffer === located.buffer && Math.abs(take.start - c.start) < 0.01 ? "on" : ""}
                    onClick={() => useLocated(located.buffer, c.start)}
                  >
                    Bar {c.bar ?? "?"} · {fmt(c.start)} · {Math.round(c.similarity * 100)}%
                  </button>
                ))}
              </div>
            </div>
          )}
          {take && (
            <div className="take-card">
              <p className="helper">{take.detail}</p>
              <div className="presets">
                <button onClick={hearTake}>
                  <Headphones size={13} /> Hear yourself in the band
                </button>
                <button onClick={exportMix}><Download size={13} /> Make a mix to keep</button>
                <button onClick={compareTake}>Compare with the original part</button>
              </div>
              {mixUrl && (
                <a className="download" href={mixUrl} download={`${song!.name.replace(/\.[^.]+$/, "")} - with me.wav`}>
                  <Download size={14} /> Download your version (WAV)
                </a>
              )}
            </div>
          )}
          <details className="provenance">
            <summary>How reliable is this?</summary>
            <ul>{result.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </details>
        </div>
      )}
    </section>
  );
}
