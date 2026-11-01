import React, { useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AudioLines,
  ArrowUpRight,
  Upload,
  Play,
  Pause,
  Headphones,
  ChevronRight,
  Check,
  Music2,
  RotateCcw,
  Info,
  SlidersHorizontal,
} from "lucide-react";
import { compare, note, type Features } from "./analysis";
import "./style.css";
import EngineSession from "./EngineSession";
import AudioInput from "./AudioInput";
import MidiInput from "./MidiInput";
import InstrumentSetup from "./InstrumentSetup";
import SongLab from "./SongLab";
import type { BarMark } from "./feedback";
import {
  defaultSettings,
  resolveInstrument,
  tabPosition,
  type InstrumentSettings,
} from "./instruments";
type Clip = { name: string; buffer: AudioBuffer };
type Result = {
  reference: Features;
  take: Features;
  match: ReturnType<typeof compare>;
  chords: { time: number; name: string }[];
};
function App() {
  const [settings, setSettings] =
    useState<InstrumentSettings>(defaultSettings());
  const profile = resolveInstrument(settings);
  const [reference, setReference] = useState<Clip | null>(null),
    [take, setTake] = useState<Clip | null>(null),
    [kind, setKind] = useState("mix"),
    [start, setStart] = useState(0),
    [length, setLength] = useState(20),
    [speed, setSpeed] = useState(0.8),
    [view, setView] = useState("Tablature"),
    [result, setResult] = useState<Result | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [recording, setRecording] = useState(false),
    [playing, setPlaying] = useState(""),
    [demo, setDemo] = useState(false),
    [bars, setBars] = useState<BarMark[] | undefined>(undefined);
  const ctx = useRef<AudioContext | null>(null),
    sources = useRef<AudioBufferSourceNode[]>([]);

  const getCtx = () => ctx.current ?? (ctx.current = new AudioContext());
  const invalidate = () => {
    setResult(null);
    setError("");
  };
  async function load(file: File, target: "reference" | "take") {
    try {
      setError("");
      if (file.size > 100 * 1024 * 1024)
        throw Error("Please choose a file smaller than 100 MB.");
      const buffer = await getCtx().decodeAudioData(await file.arrayBuffer());
      (target === "reference" ? setReference : setTake)({
        name: file.name,
        buffer,
      });
      setBars(undefined);
      setDemo(false);
      invalidate();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not decode this audio file.",
      );
    }
  }
  function stop() {
    sources.current.forEach((s) => {
      try {
        s.stop();
      } catch {}
    });
    sources.current = [];
    setPlaying("");
  }
  async function play(which: string) {
    stop();
    try {
      const context = getCtx();
      await context.resume();
      const clips =
        which === "Together"
          ? [reference, take]
          : [which === "Original" ? reference : take];
      const realDuration = Math.min(
        length,
        take?.buffer.duration ?? length,
        (reference?.buffer.duration ?? length) - start,
      );
      if (realDuration <= 0)
        throw Error("Choose a start time within the original track.");
      clips.forEach((clip) => {
        if (!clip) return;
        const source = context.createBufferSource(),
          gain = context.createGain();
        source.buffer = clip.buffer;
        source.playbackRate.value = speed;
        gain.gain.value = which === "Together" ? 0.5 : 1;
        source.connect(gain).connect(context.destination);
        source.start(
          context.currentTime + 0.05,
          clip === reference ? start : 0,
          realDuration,
        );
        sources.current.push(source);
        source.onended = () => {
          if (
            sources.current.every((s) => s === source) ||
            sources.current.at(-1) === source
          )
            setPlaying("");
        };
      });
      setPlaying(which);
    } catch (e) {
      setError(String(e));
    }
  }
  async function mono(clip: Clip, offset: number, duration: number) {
    const offline = new OfflineAudioContext(
        1,
        Math.ceil(duration * 16000),
        16000,
      ),
      source = offline.createBufferSource();
    source.buffer = clip.buffer;
    source.connect(offline.destination);
    source.start(0, offset, duration);
    return (await offline.startRendering()).getChannelData(0);
  }
  async function analyse() {
    if (!reference || !take) return;
    setBusy(true);
    setError("");
    try {
      const duration = Math.min(
        length,
        take.buffer.duration,
        reference.buffer.duration - start,
      );
      if (duration < 1)
        throw Error("Select at least one second of overlapping audio.");
      const [a, b] = await Promise.all([
        mono(reference, start, duration),
        mono(take, 0, duration),
      ]);
      const analysed = await new Promise<Result>((resolve, reject) => {
        const worker = new Worker(
          new URL("./analysis.worker.ts", import.meta.url),
          { type: "module" },
        );
        worker.onmessage = (e) => {
          worker.terminate();
          e.data.error ? reject(Error(e.data.error)) : resolve(e.data);
        };
        worker.onerror = () => {
          worker.terminate();
          reject(Error("Analysis failed. Try a shorter passage."));
        };
        worker.postMessage(
          {
            a,
            b,
            duration,
            midi_min: profile.midi_min,
            midi_max: profile.midi_max,
            chords: profile.feedback.includes("chord_estimates"),
          },
          [a.buffer, b.buffer],
        );
      });
      setResult(analysed);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  function demoClips() {
    setSettings(defaultSettings("guitar"));
    setView("Tablature");
    stop();
    const context = getCtx();
    function make(imperfect: boolean) {
      const b = context.createBuffer(
          1,
          context.sampleRate * 12,
          context.sampleRate,
        ),
        data = b.getChannelData(0);
      const sequence = [
        52, 55, 59, 55, 48, 52, 55, 52, 50, 54, 57, 54, 55, 59, 62, 59,
      ];
      sequence.forEach((m, i) => {
        const t = i * 0.7 + (imperfect && i % 4 === 0 ? 0.12 : 0),
          freq = 440 * 2 ** (((imperfect && i === 9 ? m + 1 : m) - 69) / 12);
        for (let j = 0; j < context.sampleRate * 0.6; j++) {
          const k = Math.floor(t * context.sampleRate) + j;
          if (k < data.length)
            data[k] +=
              0.28 *
              Math.exp((-j / context.sampleRate) * 7) *
              Math.sin((2 * Math.PI * freq * j) / context.sampleRate);
        }
      });
      return b;
    }
    setReference({ name: "Studio exercise · E–C–D–G", buffer: make(false) });
    setBars(undefined);
    setTake({ name: "Practice take · a few rough edges", buffer: make(true) });
    setKind("isolated");
    setStart(0);
    setLength(12);
    setDemo(true);
    invalidate();
  }
  const events = result?.take.events.slice(0, 16) ?? [];
  return (
    <div className="app">
      <aside>
        <a className="brand" href="#">
          <span className="brand-icon">
            <AudioLines size={23} />
          </span>
          fretwork<span className="brand-dot">.</span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <a className="nav active" href="#studio">
          <AudioLines size={18} /> Practice studio <span>01</span>
        </a>
        <div className="side-note">
          <Music2 size={18} />
          <h4>A little better, every take.</h4>
          <p>
            Listen closely. Find your focus.
            <br />
            Make the next take count.
          </p>
        </div>
        <div className="local">
          <span /> Private by design <p>Local until you consent to upload.</p>
        </div>
      </aside>
      <main id="studio">
        <header>
          <span>
            Workspace <ChevronRight size={14} /> Practice studio
          </span>
          <div className="version">
            GUITAR LAB <span>EARLY ACCESS</span>
          </div>
        </header>
        <section className="heading">
          <div className="eyebrow">LESS GUESSWORK. MORE PROGRESS.</div>
          <h1>
            Hear the difference.
            <br />
            <span>Find your next breakthrough.</span>
          </h1>
          <p>
            Your instrument, alongside the original. Turn a practice take into a
            clear next step.
          </p>
          <button
            className="demo"
            disabled={recording || busy}
            onClick={demoClips}
          >
            Try a sample session <ArrowUpRight size={16} />
          </button>
        </section>
        <InstrumentSetup
          settings={settings}
          disabled={recording || busy}
          onChange={(next) => {
            stop();
            setSettings(next);
            setTake(null);
            setDemo(false);
            invalidate();
            setView(next.notation === "tablature" ? "Tablature" : "Notes");
          }}
        />
        <SongLab
          settings={settings}
          onSettings={(next) => {
            setSettings(next);
            setView(next.notation === "tablature" ? "Tablature" : "Notes");
          }}
          onCompare={(ref, takeClip, at, seconds, barMarks) => {
            stop();
            setBars(barMarks);
            setReference(ref);
            setTake(takeClip);
            setKind("isolated");
            setStart(Number(at.toFixed(2)));
            setLength(Number(seconds.toFixed(2)));
            setDemo(false);
            invalidate();
            document
              .getElementById("compare")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
        <div className="step-line" id="compare">
          <span className="step selected">
            1 <b>Set up your session</b>
          </span>
          <i />
          <span className={"step " + (result ? "selected" : "")}>
            2 <b>Listen & compare</b>
          </span>
          <i />
          <span className={"step " + (result ? "selected" : "")}>
            3 <b>Find your focus</b>
          </span>
        </div>
        <div className="studio-grid">
          <section className="panel reference">
            <div className="panel-title">
              <span className="number">01</span>
              <h2>The original</h2>
              <span className="small-tag">REFERENCE TRACK</span>
            </div>
            <p className="panel-desc">Start with the song you’re learning.</p>
            <label className={"drop " + (reference ? "loaded" : "")}>
              <input
                type="file"
                accept="audio/*"
                onChange={(e) =>
                  e.target.files?.[0] && load(e.target.files[0], "reference")
                }
              />
              <span className="upload-icon">
                {reference ? <Check size={22} /> : <Upload size={22} />}
              </span>
              <strong>
                {reference ? reference.name : "Drop in your original track"}
              </strong>
              <span>
                {reference
                  ? `${reference.buffer.duration.toFixed(1)} seconds · click to replace`
                  : "Choose an audio file from your device"}
              </span>
              <small>
                MP3, WAV, M4A and browser-supported audio · up to 100 MB
              </small>
            </label>
            <div className="field-label">
              What’s in this recording? <Info size={13} />
            </div>
            <div className="segmented">
              <button
                className={kind === "mix" ? "chosen" : ""}
                onClick={() => {
                  setKind("mix");
                  invalidate();
                }}
              >
                Full band / song
              </button>
              <button
                className={kind === "isolated" ? "chosen" : ""}
                onClick={() => {
                  setKind("isolated");
                  invalidate();
                }}
              >
                Isolated {profile.name}
              </button>
            </div>
            <div className="notice">
              <Headphones size={17} />
              <p>
                {kind === "mix"
                  ? "A full mix includes bass, drums and vocals. We can explore timing, but instrument-specific pitch comparison needs an isolated reference stem. Use the specialist engine below to extract and review the selected instrument before comparison."
                  : "Best for comparison. Use a clean instrument stem or a teacher’s reference. Note and chord detection is still experimental."}
              </p>
            </div>
          </section>
          <section className="panel">
            <div className="panel-title">
              <span className="number">02</span>
              <h2>Your take</h2>
              <span className="small-tag">PLAY IT YOUR WAY</span>
            </div>
            <p className="panel-desc">
              Record a passage, or bring a take you already have.
            </p>
            <AudioInput
              key={JSON.stringify(settings)}
              profile={profile}
              duration={length}
              onRecording={(active) => {
                setRecording(active);
                if (active) stop();
              }}
              onTake={(name, buffer) => {
                setTake({ name, buffer });
                setBars(undefined);
                setDemo(false);
                invalidate();
              }}
            />
            {take && (
              <p className="helper" role="status">
                Take ready: {take.name} · {take.buffer.duration.toFixed(1)}s ·{" "}
                {take.buffer.numberOfChannels === 1 ? "mono" : "stereo"}
              </p>
            )}
            <MidiInput duration={length} />
            <label className="upload-take">
              <Upload size={15} /> Or upload a recording
              <input
                type="file"
                accept="audio/*"
                onChange={(e) =>
                  e.target.files?.[0] && load(e.target.files[0], "take")
                }
              />
            </label>
            <div className="alignment">
              <div>
                <label>Original starts at</label>
                <div className="input-wrap">
                  <input
                    aria-label="Reference start in seconds"
                    type="number"
                    min="0"
                    step="0.1"
                    value={start}
                    onChange={(e) => {
                      setStart(Math.max(0, Number(e.target.value)));
                      invalidate();
                    }}
                  />
                  <span>sec</span>
                </div>
              </div>
              <div>
                <label>Passage length</label>
                <select
                  value={length}
                  disabled={recording}
                  onChange={(e) => {
                    setLength(Number(e.target.value));
                    invalidate();
                  }}
                >
                  {[...new Set([10, 12, 20, 60, length])]
                    .sort((a, b) => a - b)
                    .map((n) => (
                      <option key={n} value={n}>
                        {Number(n.toFixed(1))} seconds
                      </option>
                    ))}
                </select>
              </div>
            </div>
            <small className="helper">
              Match the start of your take to this point in the original.
            </small>
          </section>
        </div>
        <div className="analyse-bar">
          <div>
            <span className="status-dot" />
            <span>
              {reference && take
                ? "Both tracks ready. Let’s listen closer."
                : "Two recordings. One clearer picture."}
            </span>
          </div>
          <button
            className="primary"
            disabled={!reference || !take || busy || recording}
            onClick={analyse}
          >
            {busy ? "Listening to your take…" : "Local preview comparison"}{" "}
            <ArrowUpRight size={17} />
          </button>
        </div>
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        <EngineSession
          profile={profile}
          reference={reference}
          take={take}
          kind={kind}
          start={start}
          length={length}
          recording={recording}
          bars={bars}
        />
        <section className="results">
          <div className="results-heading">
            <div>
              <div className="eyebrow">LOCAL PREVIEW · SIMPLIFIED ANALYSIS</div>
              <h2>Browser-only preview.</h2>
            </div>
            <span className="outline-tag">
              {result
                ? demo
                  ? "SYNTHETIC DEMO · REAL ANALYSIS"
                  : "LOCAL AUDIO ANALYSIS"
                : "READY WHEN YOU ARE"}
            </span>
          </div>
          {!result ? (
            <div className="empty-results">
              <span>
                <SlidersHorizontal size={26} />
              </span>
              <div>
                <h3>Small details. Real progress.</h3>
                <p>
                  This local preview uses the original lightweight detector, not
                  specialist models.
                  <br />
                  Add your tracks above, or explore the sample session.
                </p>
              </div>
              <button onClick={demoClips}>
                Load sample <ArrowUpRight size={16} />
              </button>
            </div>
          ) : (
            <>
              <div className="metrics">
                <div>
                  <label>Reference alignment</label>
                  <strong>
                    Manual <small>timestamp</small>
                  </strong>
                  <p>
                    Original at {start.toFixed(1)}s ·{" "}
                    {result.take.duration.toFixed(1)}s passage
                  </p>
                </div>
                <div>
                  <label>Pitch-class overlap</label>
                  <strong>
                    {kind === "mix"
                      ? "Not graded"
                      : Math.round(result.match.similarity * 100) + "%"}{" "}
                    <small>
                      {kind === "mix" ? "full mix" : "experimental"}
                    </small>
                  </strong>
                  <p>
                    {kind === "mix"
                      ? "Separate the selected instrument before pitch comparison."
                      : "Spectral overlap, not a playing accuracy score."}
                  </p>
                </div>
                <div>
                  <label>Onset difference</label>
                  <strong>
                    {result.match.error === null
                      ? "Unavailable"
                      : Math.round(result.match.error * 1000) + " ms"}
                  </strong>
                  <p>
                    {kind === "mix"
                      ? "Against mixed-track attacks, not instrument-specific."
                      : "Nearest attack distance; includes input latency."}
                  </p>
                </div>
              </div>
              <div className="playback">
                <div>
                  <Headphones size={19} />
                  <b>Listen side by side</b>
                </div>
                <div className="play-buttons">
                  {["Original", "Your take", "Together"].map((x) => (
                    <button
                      key={x}
                      className={playing === x ? "chosen" : ""}
                      onClick={() => (playing === x ? stop() : play(x))}
                    >
                      {playing === x ? <Pause size={14} /> : <Play size={14} />}{" "}
                      {x}
                    </button>
                  ))}
                </div>
                <label>
                  {Math.round(speed * 100)}%{" "}
                  <input
                    aria-label="Playback speed"
                    type="range"
                    min=".5"
                    max="1"
                    step=".05"
                    value={speed}
                    onChange={(e) => {
                      stop();
                      setSpeed(Number(e.target.value));
                    }}
                  />
                </label>
              </div>
              <p className="caution">
                Playback speed currently changes pitch too. Pitch-preserving
                time stretch and automatic song-position matching are planned,
                not enabled.
              </p>
              <div className="transcription-head">
                <h3>
                  Inside your take <span>ESTIMATED</span>
                </h3>
                <div className="segmented">
                  {(profile.openStrings.length
                    ? profile.feedback.includes("chord_estimates")
                      ? ["Tablature", "Notes", "Chords"]
                      : ["Tablature", "Notes"]
                    : ["Notes"]
                  ).map((x) => (
                    <button
                      key={x}
                      className={view === x ? "chosen" : ""}
                      onClick={() => setView(x)}
                    >
                      {x}
                    </button>
                  ))}
                </div>
              </div>
              {view === "Tablature" ? (
                <div className="tab-scroll">
                  <div className="tab">
                    {profile.openStrings
                      .map((m) => note(m))
                      .map((s, i) => (
                        <div className="tab-row" key={i}>
                          <b>{s}</b>
                          {events.map((e, j) => (
                            <span key={j}>
                              {tabPosition(e.midi, profile)?.string === i + 1
                                ? tabPosition(e.midi, profile)?.fret
                                : "—"}
                            </span>
                          ))}
                        </div>
                      ))}
                  </div>
                </div>
              ) : (
                <div className="notes">
                  {(view === "Notes"
                    ? events.map((e) => ({ time: e.time, name: note(e.midi) }))
                    : result.chords
                  ).map((e, i) => (
                    <div key={i}>
                      <small>{e.time.toFixed(1)}s</small>
                      <b>{e.name}</b>
                    </div>
                  ))}
                </div>
              )}
              <p className="caution">
                Candidate dominant notes only; chords are two-second major/minor
                guesses. Tab uses the selected tuning and capo to suggest
                positions, not detected finger placement. Dense chords and
                harmonics can be misread.
              </p>
              <div className="focus">
                <div className="focus-icon">
                  <RotateCcw size={21} />
                </div>
                <div>
                  <h3>Your next practice focus</h3>
                  <p>
                    {kind === "mix"
                      ? "Start by supplying an isolated instrument reference. Full-band attacks and pitch energy cannot reliably tell us which instrument notes you missed."
                      : result.match.error !== null && result.match.error > 0.09
                        ? "Loop this passage slowly and listen for late transitions. Check recording latency before treating the measured offset as a timing mistake."
                        : "Listen for consistent sustain and clean transitions. This prototype cannot yet diagnose buzzing, fretting pressure or individual missing chord tones."}
                  </p>
                </div>
              </div>
            </>
          )}
        </section>
        <footer>
          <span>
            <AudioLines size={15} /> Built for the practice, not the perfect
            take.
          </span>
          <span>Local-first · Guitar prototype v0.2</span>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
