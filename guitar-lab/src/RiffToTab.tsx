import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Download, Mic, Play, Square, Upload, FileText } from "lucide-react";
import * as alphaTab from "@coderline/alphatab";
import { api, encodeWav, type EngineNote } from "./engineApi";
import { Recorder } from "./recorder";
import { addClicks, loadLatency } from "./practice";
import { captureError } from "./audioInputs";
import { MEDIA_ACCEPT, needsBrowserDecode, toWav } from "./audioFiles";
import { resolveInstrument, type InstrumentSettings } from "./instruments";
import { useTranscriber } from "./TranscriberSelect";
import { usePlayerSound } from "./liveTone";
import YourSound from "./YourSound";
import { synthesize } from "./tabScore";
import { tuningName } from "./songApi";
import { useGuitarSound } from "./guitarTone";
import { onGrid, tabText, type HeardNote } from "./takeToTab";
const Notation = lazy(() => import("./Notation"));

const MAX_SECONDS = 60;
type Heard = { notes: HeardNote[]; duration: number; bpm: number; first_beat: number; detector: string };
type Written = { notes: EngineNote[]; musicxml: string; unplayable_notes: number; key: { key?: string } | null };
type Take = { buffer: AudioBuffer; onClick: boolean; name: string };

/**
 * Your take to tab: record a riff (to a click, or freely) or load a recording of yourself,
 * and get it back as tab and notation to download: Guitar Pro, MusicXML or plain-text tab.
 */
export default function RiffToTab({ settings }: { settings: InstrumentSettings }) {
  const profile = resolveInstrument(settings);
  const [transcriber] = useTranscriber();
  const [mySound, setMySound] = usePlayerSound();
  const [sound] = useGuitarSound();
  const [bpm, setBpm] = useState(90),
    [countIn, setCountIn] = useState(true),
    [click, setClick] = useState(true),
    [title, setTitle] = useState("My riff"),
    [consent, setConsent] = useState(false),
    [recording, setRecording] = useState(false),
    [trying, setTrying] = useState(false),
    [take, setTake] = useState<Take | null>(null),
    [heard, setHeard] = useState<Heard | null>(null),
    [grid, setGrid] = useState({ bpm: 90, first: 0 }),
    [written, setWritten] = useState<Written | null>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [playing, setPlaying] = useState<"" | "mine" | "heard">("");
  const ctx = useRef<AudioContext | null>(null),
    rec = useRef<Recorder | null>(null),
    clicks = useRef<AudioBufferSourceNode | null>(null),
    player = useRef<AudioBufferSourceNode | null>(null);
  const context = () => ctx.current ?? (ctx.current = new AudioContext());
  const recorder = () => rec.current ?? (rec.current = new Recorder(context()));
  useEffect(
    () => () => {
      rec.current?.release();
      ctx.current?.close().catch(() => {});
    },
    [],
  );

  async function trySound() {
    try {
      if (trying) {
        rec.current?.monitor(null);
        setTrying(false);
        return;
      }
      await context().resume();
      await recorder().ensure();
      recorder().monitor(mySound, mySound.level);
      setTrying(true);
    } catch (e) {
      setError(captureError(e));
    }
  }

  async function record() {
    setError("");
    setTake(null);
    setHeard(null);
    setWritten(null);
    try {
      const c = context();
      await c.resume();
      await recorder().ensure();
      if (mySound.monitor) recorder().monitor(mySound, mySound.level);
      const beat = 60 / bpm,
        lead = countIn ? 4 * beat : 0,
        now = c.currentTime + 0.15,
        rate = c.sampleRate;
      // The count-in and (if on) a click all the way through, as one buffer.
      const times = [
        ...(countIn ? [0, 1, 2, 3].map((i) => ({ time: i * beat, accent: i === 0 })) : []),
        ...(click ? Array.from({ length: Math.floor(MAX_SECONDS / beat) }, (_, i) => ({ time: lead + i * beat, accent: i % 4 === 0 })) : []),
      ];
      if (times.length) {
        const out = c.createBuffer(1, Math.ceil((lead + MAX_SECONDS + 1) * rate), rate);
        addClicks([out.getChannelData(0)], rate, times, 0, 1, 0.5);
        const s = c.createBufferSource();
        s.buffer = out;
        s.connect(c.destination);
        s.start(now);
        clicks.current = s;
      }
      const recordFrom = c.currentTime;
      setRecording(true);
      const raw = await recorder().capture(Math.ceil((now - recordFrom + lead + MAX_SECONDS) * rate), lead + MAX_SECONDS + 10);
      setRecording(false);
      stopClicks();
      if (!trying) recorder().monitor(null);
      const delay = recorder().delay(loadLatency()),
        from = Math.max(0, Math.round((now - recordFrom + lead + delay) * rate)),
        part = raw.subarray(Math.min(raw.length, from));
      if (part.length < rate) throw Error("That was under a second. Record a little longer.");
      const buffer = c.createBuffer(1, part.length, rate);
      buffer.getChannelData(0).set(part);
      setTake({ buffer, onClick: countIn || click, name: "Recorded riff" });
    } catch (e) {
      setRecording(false);
      stopClicks();
      setError(captureError(e));
    }
  }
  function stopClicks() {
    try {
      clicks.current?.stop();
    } catch {}
    clicks.current = null;
  }

  async function load(file: File) {
    setError("");
    setHeard(null);
    setWritten(null);
    try {
      const c = context();
      const wav = needsBrowserDecode(file.name) ? await toWav(file, c) : file;
      const decoded = await c.decodeAudioData(await wav.arrayBuffer());
      if (decoded.duration > MAX_SECONDS + 0.5) throw Error(`Use a recording of up to a minute (this one is ${Math.round(decoded.duration)} s). Trim it to the riff.`);
      const mono = c.createBuffer(1, decoded.length, decoded.sampleRate),
        out = mono.getChannelData(0);
      for (let ch = 0; ch < decoded.numberOfChannels; ch++) {
        const d = decoded.getChannelData(ch);
        for (let i = 0; i < d.length; i++) out[i] += d[i] / decoded.numberOfChannels;
      }
      setTake({ buffer: mono, onClick: false, name: file.name });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function transcribe() {
    if (!take) return;
    setBusy("Listening to your take…");
    setError("");
    try {
      const body = new FormData();
      body.set("take", encodeWav([take.buffer.getChannelData(0)], take.buffer.sampleRate), "take.wav");
      body.set("consent", String(consent));
      body.set("transcriber", transcriber);
      body.set("standard_tuning", String(profile.id === "guitar" && settings.tuning === "standard" && settings.capo === 0));
      const result = await api<Heard>("/api/takes/transcribe", { method: "POST", body });
      if (!result.notes.length) throw Error("No notes were heard. Check the input level and record again.");
      setHeard(result);
      const g = take.onClick ? { bpm, first: 0 } : { bpm: Math.round(result.bpm), first: result.first_beat };
      setGrid(g);
      await write(result, g);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function write(h = heard, g = grid) {
    if (!h) return;
    setBusy("Writing it out…");
    setError("");
    try {
      setWritten(
        await api<Written>("/api/tabs/notation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            notes: onGrid(h.notes, g.first),
            instrument: profile.id,
            tuning: settings.tuning,
            capo: settings.capo,
            bpm: g.bpm,
            title: title.trim() || "My riff",
          }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function listen(which: "mine" | "heard") {
    try {
      player.current?.stop();
    } catch {}
    player.current = null;
    if (playing === which || !take) return setPlaying("");
    const c = context();
    await c.resume();
    let buffer = take.buffer;
    if (which === "heard" && written) {
      const shifted = written.notes.map((n) => ({ ...n, time: n.time + grid.first })),
        data = synthesize(shifted, c.sampleRate, take.buffer.duration + 1, 1, 0.3, sound);
      buffer = c.createBuffer(1, data.length, c.sampleRate);
      buffer.getChannelData(0).set(data);
    }
    const s = c.createBufferSource();
    s.buffer = buffer;
    s.connect(c.destination);
    s.onended = () => player.current === s && setPlaying("");
    s.start();
    player.current = s;
    setPlaying(which);
  }

  const text = useMemo(
    () => (written && profile.openStrings.length ? tabText(written.notes, grid.bpm, profile.openStrings) : ""),
    [written, grid.bpm, profile.openStrings],
  );
  const name = (title.trim() || "My riff").replace(/[\\/:*?"<>|]+/g, "-");
  const files = useMemo(() => {
    if (!written) return null;
    const xml = URL.createObjectURL(new Blob([written.musicxml], { type: "application/vnd.recordare.musicxml+xml" }));
    const txt = text ? URL.createObjectURL(new Blob([text], { type: "text/plain" })) : "";
    let gp = "";
    try {
      const s = new alphaTab.Settings();
      const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(new TextEncoder().encode(written.musicxml), s);
      gp = URL.createObjectURL(new Blob([new Uint8Array(new alphaTab.exporter.Gp7Exporter().export(score, s))], { type: "application/octet-stream" }));
    } catch {}
    return { xml, txt, gp };
  }, [written, text]);
  useEffect(
    () => () => {
      if (files) Object.values(files).forEach((u) => u && URL.revokeObjectURL(u));
    },
    [files],
  );

  const heardStrings = !!heard?.notes.some((n) => n.string_probs);
  const fretted = written ? written.notes.filter((n) => n.string != null && n.fret != null).length : 0;
  return (
    <section className="panel song-lab riff-to-tab" id="riff-to-tab" aria-labelledby="riff-title-heading">
      <div className="eyebrow">YOUR TAKE TO TAB</div>
      <h2 id="riff-title-heading">
        <FileText size={18} /> Turn your playing into tab
      </h2>
      <p className="panel-desc">
        Play a riff or phrase (up to a minute) and get it back as tab and notation, to keep or open in Guitar Pro or MuseScore. Playing to the
        click gives the cleanest rhythm. The app writes what it hears: single notes and simple chords come out best; bends, slides and
        heavy distortion do not.
      </p>
      <div className="riff-setup">
        <label>
          Name <input id="riff-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label>
          Tempo <input id="riff-bpm" type="number" min={40} max={240} value={bpm} onChange={(e) => setBpm(Math.max(40, Math.min(240, Number(e.target.value) || 90)))} /> BPM
        </label>
        <label className="consent">
          <input id="riff-count-in" type="checkbox" checked={countIn} onChange={(e) => setCountIn(e.target.checked)} />
          <span>One bar count-in</span>
        </label>
        <label className="consent">
          <input id="riff-click" type="checkbox" checked={click} onChange={(e) => setClick(e.target.checked)} />
          <span>Click while I play (headphones, so the mic doesn't hear it)</span>
        </label>
        <span className="helper">
          {profile.name}, {tuningName(settings.tuning)}
          {settings.capo ? `, capo ${settings.capo}` : ""}
        </span>
      </div>
      {profile.id === "guitar" && (
        <YourSound
          sound={mySound}
          onChange={(next) => {
            setMySound(next);
            if (trying) rec.current?.monitor(next, next.level);
          }}
          trying={trying}
          onTry={trySound}
          disabled={recording}
        />
      )}
      <div className="presets">
        {recording ? (
          <button className="primary" onClick={() => recorder().stop()}>
            <Square size={14} /> Stop recording
          </button>
        ) : (
          <button className="primary" id="riff-record" onClick={record} disabled={!!busy}>
            <Mic size={14} /> Record a riff
          </button>
        )}
        <label className="riff-file">
          <Upload size={14} /> Or load a recording of yourself{" "}
          <input id="riff-file" type="file" accept={MEDIA_ACCEPT} disabled={recording} onChange={(e) => e.target.files?.[0] && load(e.target.files[0])} />
        </label>
      </div>
      {recording && <p className="helper">Recording{countIn ? " after the count-in" : ""}… press Stop when you're done (stops by itself after a minute).</p>}
      {take && (
        <div className="riff-take">
          <p className="helper">
            {take.name}: {take.buffer.duration.toFixed(1)} s
            {take.onClick ? `, played to ${bpm} BPM.` : ". The tempo and where bar 1 starts are worked out from your playing; adjust them after."}
          </p>
          <label className="consent">
            <input id="riff-consent" type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            <span>Send this take to the engine to be transcribed (deleted straight after).</span>
          </label>
          <div className="presets">
            <button className="primary" id="riff-write" disabled={!consent || !!busy} onClick={transcribe}>
              {busy || "Write it out as tab"}
            </button>
            <button className={playing === "mine" ? "on" : ""} onClick={() => listen("mine")}>
              {playing === "mine" ? <Square size={13} /> : <Play size={13} />} My recording
            </button>
            {written && (
              <button className={playing === "heard" ? "on" : ""} onClick={() => listen("heard")}>
                {playing === "heard" ? <Square size={13} /> : <Play size={13} />} The tab played back
              </button>
            )}
          </div>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {heard && written && (
        <div className="riff-result">
          <div className="riff-grid">
            <label>
              Tempo <input id="riff-grid-bpm" type="number" min={40} max={240} value={grid.bpm} onChange={(e) => setGrid({ ...grid, bpm: Number(e.target.value) || grid.bpm })} /> BPM
            </label>
            {!take?.onClick && (
              <label>
                Bar 1 starts at <input id="riff-grid-first" type="number" min={0} step={0.01} value={grid.first} onChange={(e) => setGrid({ ...grid, first: Math.max(0, Number(e.target.value)) })} /> s
              </label>
            )}
            <button disabled={!!busy} onClick={() => write()}>
              Rewrite with this tempo
            </button>
            {!take?.onClick && (
              <span className="tempo-fixes" aria-label="Quick tempo fixes">
                {([["½×", 0.5], ["⅔×", 2 / 3], ["1.5×", 1.5], ["2×", 2]] as const).map(([label, k]) => {
                  const next = Math.round(grid.bpm * k);
                  return (
                    <button
                      key={label}
                      disabled={!!busy || next < 40 || next > 240}
                      title={`Rewrite at ${next} BPM`}
                      onClick={() => {
                        const g = { ...grid, bpm: next };
                        setGrid(g);
                        write(heard, g);
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </span>
            )}
            <span className="helper">
              {heard.notes.length} notes heard ({heard.detector}){written.key?.key ? `, key ${written.key.key}` : ""}
              {written.unplayable_notes ? `; ${written.unplayable_notes} outside this tuning, left out` : ""}.
              {take?.onClick
                ? " Written on the click you played to."
                : " Without a click the tempo is a guess (about 7 times in 10 it is right or exactly double or half). If the rhythm looks too busy or too slow, try the quick fixes."}{" "}
              {heardStrings
                ? "Strings and frets come from listening to which string each note was played on (in tests about 9 notes in 10 land where they were played)."
                : "Frets are the app's choice of where to play each note (it only listens for the string in standard tuning without a capo); you may have played some elsewhere on the neck."}
            </span>
          </div>
          <Suspense fallback={<p className="helper">Loading the notation view…</p>}>
            <Notation musicxml={written.musicxml} tab={profile.openStrings.length > 0} />
          </Suspense>
          {text && (
            <details className="riff-text" open>
              <summary>Text tab</summary>
              <pre aria-label="Text tab">{text}</pre>
              <button onClick={() => navigator.clipboard?.writeText(text)}>Copy text tab</button>
            </details>
          )}
          {files && (
            <div className="presets downloads">
              {files.gp && (
                <a className="download" href={files.gp} download={`${name}.gp`}>
                  <Download size={14} /> Guitar Pro (.gp)
                </a>
              )}
              <a className="download" href={files.xml} download={`${name}.musicxml`}>
                <Download size={14} /> MusicXML (MuseScore, Sibelius, Guitar Pro)
              </a>
              {files.txt && (
                <a className="download" href={files.txt} download={`${name}.txt`}>
                  <Download size={14} /> Text tab (.txt)
                </a>
              )}
            </div>
          )}
          {!fretted && <p className="helper">None of the notes fit this tuning, so the tab is empty. Check the tuning above.</p>}
        </div>
      )}
    </section>
  );
}
