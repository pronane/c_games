import { useEffect, useRef, useState } from "react";
import { Download, Music2, Square } from "lucide-react";
import { MidiCapture, midiFile, type MidiNote } from "./midiCapture";
import { note } from "./analysis";
export default function MidiInput({ duration }: { duration: number }) {
  const [inputs, setInputs] = useState<MIDIInput[]>([]),
    [selected, setSelected] = useState(""),
    [enabled, setEnabled] = useState(false),
    [working, setWorking] = useState(false),
    [recording, setRecording] = useState(false),
    [notes, setNotes] = useState<MidiNote[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [received, setReceived] = useState(0);
  const access = useRef<MIDIAccess | null>(null),
    source = useRef<MIDIInput | null>(null),
    session = useRef<MidiCapture | null>(null),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    began = useRef(0),
    limit = useRef(60),
    alive = useRef(true),
    active = useRef(false),
    generation = useRef(0);
  const supported =
    typeof navigator !== "undefined" &&
    "requestMIDIAccess" in navigator &&
    window.isSecureContext;
  function stop() {
    if (!active.current) return;
    active.current = false;
    if (timer.current) clearTimeout(timer.current);
    if (source.current) {
      source.current.onmidimessage = null;
      void source.current.close().catch(() => {});
      source.current = null;
    }
    const result =
      session.current?.finish(
        Math.min(
          limit.current,
          Math.max(0, (performance.now() - began.current) / 1000),
        ),
      ) ?? [];
    if (alive.current) {
      setNotes([...result]);
      setRecording(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      generation.current++;
      stop();
      if (access.current) access.current.onstatechange = null;
    };
  }, []);
  async function enable() {
    setWorking(true);
    setError("");
    const version = ++generation.current;
    try {
      const midi = await navigator.requestMIDIAccess({ sysex: false });
      if (!alive.current || version !== generation.current) return;
      access.current = midi;
      const refresh = () => {
        const list = [...midi.inputs.values()].filter(
          (i) => i.state === "connected",
        );
        setInputs(list);
        if (source.current?.state === "disconnected") {
          stop();
          setNotice(
            "MIDI input disconnected. Received notes were finalised; select an input and start a new take.",
          );
        }
      };
      refresh();
      midi.onstatechange = refresh;
      setEnabled(true);
    } catch {
      if (alive.current)
        setError(
          "MIDI access was denied or unavailable. Allow MIDI access in a supporting browser; no SysEx permission is requested.",
        );
    } finally {
      if (alive.current) setWorking(false);
    }
  }
  async function record() {
    if (active.current) {
      stop();
      return;
    }
    const input = inputs.find((i) => i.id === selected);
    if (!input) {
      setError("Select a connected MIDI input first.");
      return;
    }
    setWorking(true);
    setError("");
    setNotice("");
    const version = generation.current;
    try {
      await input.open();
      if (!alive.current || version !== generation.current) {
        await input.close();
        return;
      }
      source.current = input;
      session.current = new MidiCapture();
      limit.current = Math.min(60, Math.max(1, duration));
      began.current = performance.now();
      active.current = true;
      setNotes([]);
      setReceived(0);
      setRecording(true);
      input.onmidimessage = (event) => {
        if (!active.current || !event.data) return;
        const t = Math.min(
          limit.current,
          Math.max(0, (event.timeStamp - began.current) / 1000),
        );
        session.current?.message(event.data, t);
        setReceived((n) => n + 1);
      };
      timer.current = setTimeout(stop, limit.current * 1000);
    } catch {
      setError(
        "Could not open the MIDI input. Check the adapter and browser permission.",
      );
    } finally {
      if (alive.current) setWorking(false);
    }
  }
  function download() {
    const bytes = midiFile(notes);
    const url = URL.createObjectURL(
      new Blob([bytes.buffer as ArrayBuffer], { type: "audio/midi" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "fretwork-keyboard-take.mid";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <details className="midi-input">
      <summary>
        <Music2 size={15} /> USB MIDI keyboard / MIDI adapter
      </summary>
      <p className="caution">
        MIDI records keys, timing, velocity and sustain—not your instrument’s
        sound. This local capture exports a .mid file; MIDI comparison and
        piano-specific scoring are not implemented. Use an audio interface above
        if you want a sound recording.
      </p>
      {!supported ? (
        <p className="engine-warning">
          Web MIDI is not supported in this browser or context. Try a browser
          with Web MIDI support, such as desktop Chrome/Edge. Safari/iPhone/iPad
          MIDI capture is not available through this path; USB audio may still
          work.
        </p>
      ) : (
        <>
          <div className="input-actions">
            <button
              className="record-button"
              disabled={working || recording || enabled}
              onClick={enable}
            >
              {working && !recording
                ? "Requesting access…"
                : enabled
                  ? "MIDI access enabled"
                  : "Enable MIDI input"}
            </button>
            {enabled && (
              <select
                aria-label="MIDI input"
                value={selected}
                disabled={working || recording}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Select MIDI input</option>
                {inputs.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name || i.manufacturer || "MIDI input"}
                  </option>
                ))}
              </select>
            )}
          </div>
          {enabled && !inputs.length && (
            <p className="caution">
              No MIDI inputs detected. Connect a USB MIDI keyboard or
              class-compliant MIDI adapter.
            </p>
          )}
          {enabled && (
            <div className="input-actions">
              <button
                className="record-button"
                disabled={
                  working ||
                  !selected ||
                  (!recording && !inputs.some((i) => i.id === selected))
                }
                onClick={record}
              >
                {recording ? <Square size={14} /> : <Music2 size={14} />}{" "}
                {recording
                  ? "Stop MIDI take"
                  : `Record MIDI · up to ${duration}s`}
              </button>
              <button
                className="record-button"
                disabled={!notes.length || recording}
                onClick={download}
              >
                <Download size={14} /> Download MIDI
              </button>
            </div>
          )}
          {recording && (
            <p role="status" className="caution">
              Recording MIDI locally · {received} messages received. Play
              through your keyboard’s speakers or headphones.
            </p>
          )}
          {notes.length > 0 && (
            <>
              <p className="caution">
                {notes.length} note events captured. Sustain is baked into note
                durations; raw controller curves, pitch bend and aftertouch are
                not exported.
              </p>
              <div className="notes">
                {notes.slice(0, 16).map((n, i) => (
                  <div key={i}>
                    <small>{n.time.toFixed(2)}s</small>
                    <b>{note(n.midi)}</b>
                    <small>
                      {n.duration.toFixed(2)}s · ch {n.channel + 1}
                    </small>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
      {notice && (
        <p role="status" className="engine-warning">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </details>
  );
}
