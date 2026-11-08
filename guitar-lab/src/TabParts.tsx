import { useEffect, useRef, useState } from "react";
import { FileMusic, Play, Square } from "lucide-react";
import * as alphaTab from "@coderline/alphatab";
import { api } from "./engineApi";
import { trackUrl } from "./songApi";
import { scoreToPiece, synthesize } from "./tabScore";
import { useGuitarSound } from "./guitarTone";

type Section = { start: number; end: number; first_bar: number | null; last_bar: number | null };
type Match = { tab_notes: number; heard_matched: number; precision: number; recall: number; f1: number };
type PlacedNote = { time: number; duration: number; midi: number; bar?: number };
type Part = { name: string; track: number | null; sections: Section[]; notes: PlacedNote[]; match: Match };
type Result = {
  alignment: { tempo_ratio: number; similarity: number; start: number; refined: boolean; attack_match: number | null };
  parts: Part[];
  unassigned: number;
  heard: number;
};
type Listen = { part: string; how: "record" | "tab" | "both" } | null;

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const percent = (x: number) => `${Math.round(x * 100)}%`;

/**
 * Name the song's guitar parts from the player's own tab file (Guitar Pro, MusicXML…): the tab
 * is lined up with the recording, each tab track becomes a named part with the stretches where
 * it plays, and every note the app heard is credited to the tab part it matches.
 */
export default function TabParts({ songId, songTitle }: { songId: string; songTitle: string }) {
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [result, setResult] = useState<Result | null>(null),
    [listening, setListening] = useState<Listen>(null),
    [sound] = useGuitarSound();
  const ctx = useRef<AudioContext | null>(null),
    source = useRef<AudioBufferSourceNode | null>(null),
    mix = useRef<AudioBuffer | null>(null);
  const context = () => (ctx.current ??= new AudioContext());
  useEffect(
    () => () => {
      try {
        source.current?.stop();
      } catch {}
      ctx.current?.close().catch(() => {});
    },
    [],
  );
  useEffect(() => {
    setResult(null);
    mix.current = null;
  }, [songId]);

  async function load(file: File) {
    setError("");
    setResult(null);
    setBusy("Reading the tab…");
    try {
      const settings = new alphaTab.Settings();
      const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(new Uint8Array(await file.arrayBuffer()), settings);
      const tracks = score.tracks
        .map((t, i) => ({ t, i }))
        .filter(({ t }) => !t.staves[0]?.isPercussion)
        .map(({ t, i }) => {
          const piece = scoreToPiece(score, i);
          return {
            name: t.name || `Track ${i + 1}`,
            track: i,
            notes: piece.notes.map(({ time, duration, midi, bar, string, fret }) => ({ time, duration, midi, bar, string, fret })),
          };
        })
        .filter((t) => t.notes.length);
      if (!tracks.length) throw Error("That file has no pitched tracks.");
      setBusy(`Lining ${tracks.length} tab parts up with the recording (about half a minute)…`);
      setResult(
        await api<Result>(`/api/songs/${songId}/tab-parts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tracks }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  function stop() {
    try {
      source.current?.stop();
    } catch {}
    source.current = null;
    setListening(null);
  }

  async function listen(part: Part, how: "record" | "tab" | "both") {
    if (listening?.part === part.name && listening.how === how) return stop();
    stop();
    const c = context();
    await c.resume();
    if (!mix.current) {
      const r = await fetch(trackUrl(songId, "mix"));
      if (!r.ok) return setError("Could not load the recording.");
      mix.current = await c.decodeAudioData(await r.arrayBuffer());
    }
    const rec = mix.current,
      rate = c.sampleRate,
      first = part.sections[0];
    // The part's first stretch, with a second either side.
    const from = Math.max(0, first.start - 1),
      to = Math.min(rec.duration, first.end + 1),
      frames = Math.ceil((to - from) * rate);
    const out = c.createBuffer(2, frames, rate);
    const tab = synthesize(
      part.notes.filter((n) => n.time >= from && n.time < to).map((n) => ({ ...n, time: n.time - from })),
      rate,
      to - from,
      1,
      0.3,
      sound,
    );
    const take = (ch: number) => {
      const data = rec.getChannelData(Math.min(ch, rec.numberOfChannels - 1));
      const a = Math.round(from * rec.sampleRate);
      const seg = new Float32Array(frames);
      // Plain resample by index (the recording is usually at the context's rate already).
      const step = rec.sampleRate / rate;
      for (let i = 0; i < frames; i++) seg[i] = data[a + Math.floor(i * step)] ?? 0;
      return seg;
    };
    if (how === "record") [0, 1].forEach((ch) => out.getChannelData(ch).set(take(ch)));
    else if (how === "tab") [0, 1].forEach((ch) => out.getChannelData(ch).set(tab.subarray(0, frames)));
    else {
      out.getChannelData(0).set(take(0));
      out.getChannelData(1).set(tab.subarray(0, frames));
    }
    const s = c.createBufferSource();
    s.buffer = out;
    s.connect(c.destination);
    s.onended = () => source.current === s && setListening(null);
    s.start();
    source.current = s;
    setListening({ part: part.name, how });
  }

  const button = (part: Part, how: "record" | "tab" | "both", label: string) => {
    const on = listening?.part === part.name && listening.how === how;
    return (
      <button className={on ? "on" : ""} onClick={() => listen(part, how)}>
        {on ? <Square size={13} /> : <Play size={13} />} {label}
      </button>
    );
  };

  return (
    <section className="tab-parts" aria-label="Name the parts from a tab">
      <h3>
        <FileMusic size={16} /> Name the guitar parts from a tab file
      </h3>
      <p className="helper">
        Load your own tab of {songTitle || "this song"} (Guitar Pro, MusicXML). Its tracks (Guitar 1, Riff A, Solo…) are lined up
        with the recording, even when the band plays at a different tempo from the chart, and every note the app heard is
        given to the part it belongs to. Two guitars in the same place in the mix can then still be told apart.
      </p>
      <input
        id="tab-parts-file"
        type="file"
        accept=".gp,.gp3,.gp4,.gp5,.gpx,.xml,.musicxml,.mxl,.tex"
        disabled={!!busy}
        onChange={(e) => e.target.files?.[0] && load(e.target.files[0])}
      />
      {busy && <p className="helper">{busy}</p>}
      {error && <p className="error">{error}</p>}
      {result && (
        <>
          <p className="helper">
            Tab starts at {fmt(result.alignment.start)} in the recording; the band plays at {percent(1 / result.alignment.tempo_ratio)} of the
            chart's tempo. {result.heard - result.unassigned} of the {result.heard} notes the app heard match a part of the tab.
          </p>
          <table className="tab-parts-table">
            <thead>
              <tr>
                <th>Part</th>
                <th>Where it plays</th>
                <th title="Share of the tab's notes the app heard in the recording">Heard</th>
                <th>Listen</th>
              </tr>
            </thead>
            <tbody>
              {result.parts.map((p) => (
                <tr key={p.name}>
                  <td>{p.name}</td>
                  <td>
                    {p.sections
                      .slice(0, 4)
                      .map((s) => `${fmt(s.start)}–${fmt(s.end)}${s.first_bar ? ` (bars ${s.first_bar}–${s.last_bar})` : ""}`)
                      .join(", ")}
                    {p.sections.length > 4 ? ` and ${p.sections.length - 4} more` : ""}
                  </td>
                  <td>
                    {percent(p.match.recall)} <small className="helper">of {p.match.tab_notes}</small>
                  </td>
                  <td className="presets">
                    {button(p, "record", "Record")}
                    {button(p, "tab", "Tab")}
                    {button(p, "both", "Both")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="helper">
            "Heard" is how much of each tab part the app's transcription found at the right time and pitch: a quick
            accuracy check against your tab. Listen plays the part's first passage (Both: record left, tab right).
          </p>
        </>
      )}
    </section>
  );
}
