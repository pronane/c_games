import { useEffect, useRef, useState } from "react";
import { detectPitch, tuningReading } from "./tuner";
import { note } from "./analysis";
import type { ResolvedInstrument } from "./instruments";
import { Mic, Square, Plug, RefreshCw } from "lucide-react";
import {
  captureError,
  inputConstraints,
  mergeCapture,
  selectedChannels,
  type InputMode,
} from "./audioInputs";

type Props = {
  duration: number;
  profile: ResolvedInstrument;
  onTake: (name: string, buffer: AudioBuffer) => void;
  onRecording: (value: boolean) => void;
};
type Connection = {
  context: AudioContext;
  stream: MediaStream;
  source: MediaStreamAudioSourceNode;
  splitter: ChannelSplitterNode;
  merger: ChannelMergerNode;
  analysers: AnalyserNode[];
  capture: AudioWorkletNode;
  muted: GainNode;
  channels: number;
  label: string;
};
export default function AudioInput({
  duration,
  profile,
  onTake,
  onRecording,
}: Props) {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]),
    [deviceId, setDeviceId] = useState(""),
    [mode, setMode] = useState<InputMode>("input1"),
    [connected, setConnected] = useState(false),
    [opening, setOpening] = useState(false),
    [recording, setRecording] = useState(false),
    [level, setLevel] = useState(0),
    [clipped, setClipped] = useState(false),
    [elapsed, setElapsed] = useState(0),
    [message, setMessage] = useState(""),
    [label, setLabel] = useState(""),
    [channels, setChannels] = useState(0),
    [tunerOn, setTunerOn] = useState(false),
    [target, setTarget] = useState<number | null>(null),
    [reading, setReading] = useState<ReturnType<typeof tuningReading> | null>(
      null,
    );
  const instrument = profile.name,
    tunerState = useRef({ on: tunerOn, target }),
    lastTuner = useRef(0);
  tunerState.current = { on: tunerOn, target };
  const connection = useRef<Connection | null>(null),
    generation = useRef(0),
    alive = useRef(true),
    frame = useRef(0),
    chunks = useRef<Float32Array[][]>([]),
    captureActive = useRef(false),
    callbacks = useRef({ onTake, onRecording }),
    began = useRef(0);
  callbacks.current = { onTake, onRecording };
  const supported =
    typeof window !== "undefined" &&
    window.isSecureContext &&
    !!navigator.mediaDevices?.getUserMedia;
  async function refresh() {
    try {
      if (navigator.mediaDevices) {
        const all = await navigator.mediaDevices.enumerateDevices();
        if (alive.current)
          setDevices(all.filter((d) => d.kind === "audioinput"));
      }
    } catch (e) {
      if (alive.current) setMessage(captureError(e));
    }
  }
  function release(update = true) {
    generation.current++;
    captureActive.current = false;
    chunks.current = [];
    cancelAnimationFrame(frame.current);
    const old = connection.current;
    connection.current = null;
    if (old) {
      old.stream.getTracks().forEach((t) => {
        t.onended = null;
        t.stop();
      });
      old.capture.port.onmessage = null;
      old.source.disconnect();
      old.splitter.disconnect();
      old.merger.disconnect();
      old.analysers.forEach((a) => a.disconnect());
      old.capture.disconnect();
      old.muted.disconnect();
      void old.context.close().catch(() => {});
    }
    if (update && alive.current) {
      setConnected(false);
      setRecording(false);
      setOpening(false);
      setLevel(0);
      setChannels(0);
      callbacks.current.onRecording(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    refresh();
    const changed = () => {
      void refresh();
      const current = connection.current,
        actual = current?.stream.getAudioTracks()[0]?.getSettings().deviceId;
      if (actual && actual !== "default")
        navigator.mediaDevices
          .enumerateDevices()
          .then((list) => {
            if (
              alive.current &&
              connection.current === current &&
              !list.some(
                (d) => d.kind === "audioinput" && d.deviceId === actual,
              )
            ) {
              release();
              setMessage(
                "The connected input was removed. Any unfinished take was discarded; reconnect and record again.",
              );
            }
          })
          .catch(() => {});
    };
    navigator.mediaDevices?.addEventListener("devicechange", changed);
    return () => {
      alive.current = false;
      release(false);
      navigator.mediaDevices?.removeEventListener("devicechange", changed);
    };
  }, []);
  async function connect() {
    if (!supported) {
      setMessage(
        "Audio capture requires a supported browser over HTTPS. You can still upload an audio recording.",
      );
      return;
    }
    release();
    setOpening(true);
    setMessage("");
    setClipped(false);
    const version = generation.current;
    let media: MediaStream | null = null,
      context: AudioContext | null = null;
    try {
      media = await navigator.mediaDevices.getUserMedia(
        inputConstraints(deviceId),
      );
      if (version !== generation.current || !alive.current) {
        media.getTracks().forEach((t) => t.stop());
        return;
      }
      context = new AudioContext({ latencyHint: "interactive" });
      await context.resume();
      if (!context.audioWorklet)
        throw Error(
          "This browser does not support AudioWorklet recording. Try a current browser or upload an audio file.",
        );
      await context.audioWorklet.addModule(
        new URL("./capture.worklet.js?no-inline", import.meta.url).href,
      );
      if (version !== generation.current || !alive.current) {
        media.getTracks().forEach((t) => t.stop());
        await context.close();
        return;
      }
      const source = context.createMediaStreamSource(media),
        available =
          media.getAudioTracks()[0].getSettings().channelCount ??
          source.channelCount;
      const indices = selectedChannels(mode);
      if (indices.some((c) => c >= available))
        throw Error(
          "This input exposes only one channel. Select input 1; the browser may not expose every physical interface channel.",
        );
      const splitter = context.createChannelSplitter(Math.max(2, available)),
        merger = context.createChannelMerger(indices.length),
        analysers = indices.map(() => context!.createAnalyser()),
        muted = context.createGain();
      const capture = new AudioWorkletNode(context, "fretwork-capture", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [indices.length],
        channelCount: indices.length,
        channelCountMode: "explicit",
      });
      source.connect(splitter);
      indices.forEach((input, output) =>
        splitter.connect(merger, input, output),
      );
      merger.connect(capture);
      indices.forEach((input, i) => splitter.connect(analysers[i], input));
      muted.gain.value = 0;
      capture.connect(muted).connect(context.destination);
      analysers.forEach((a) => {
        a.fftSize = 8192;
      });
      const inputLabel =
        media.getAudioTracks()[0].label || "Selected audio input";
      connection.current = {
        context,
        stream: media,
        source,
        splitter,
        merger,
        analysers,
        capture,
        muted,
        channels: indices.length,
        label: inputLabel,
      };
      media.getAudioTracks()[0].onended = () => {
        if (connection.current?.stream === media) {
          release();
          setMessage(
            "The audio input disconnected. Any unfinished take was discarded. Reconnect to continue.",
          );
        }
      };
      capture.onprocessorerror = () => {
        if (connection.current?.capture === capture) {
          release();
          setMessage(
            "The audio capture processor stopped. Any unfinished take was discarded; reconnect to record again.",
          );
        }
      };
      context.onstatechange = () => {
        if (
          connection.current?.context === context &&
          context!.state !== "running" &&
          captureActive.current
        ) {
          release();
          setMessage(
            "The browser suspended audio capture. Any unfinished take was discarded; keep the app active and reconnect.",
          );
        }
      };
      capture.port.onmessage = ({ data }) => {
        if (version !== generation.current || !captureActive.current) return;
        if (data.type === "chunk") chunks.current.push(data.channels);
        if (data.type === "done") {
          captureActive.current = false;
          setRecording(false);
          callbacks.current.onRecording(false);
          setElapsed(0);
          try {
            const samples = mergeCapture(
                chunks.current,
                indices.length,
                data.frames,
              ),
              buffer = context!.createBuffer(
                indices.length,
                data.frames,
                context!.sampleRate,
              );
            samples.forEach((values, i) =>
              buffer.copyToChannel(new Float32Array(values), i),
            );
            chunks.current = [];
            callbacks.current.onTake(
              `${instrument} · ${inputLabel} · ${mode === "stereo" ? "stereo" : mode === "input2" ? "input 2" : "input 1"}`,
              buffer,
            );
          } catch (e) {
            setMessage(captureError(e));
          }
        }
      };
      const values = new Float32Array(8192);
      const meter = () => {
        if (version !== generation.current || !connection.current) return;
        let peak = 0;
        let bestEnergy = 0;
        const doTuner =
          tunerState.current.on &&
          !captureActive.current &&
          performance.now() - lastTuner.current > 140;
        let pitchSamples: Float32Array | null = null;
        for (const analyser of analysers) {
          analyser.getFloatTimeDomainData(values);
          let energy = 0;
          for (const n of values) {
            peak = Math.max(peak, Math.abs(n));
            energy += n * n;
          }
          if (doTuner && energy > bestEnergy) {
            bestEnergy = energy;
            pitchSamples = new Float32Array(values);
          }
        }
        if (doTuner) {
          lastTuner.current = performance.now();
          const pitch = pitchSamples
            ? detectPitch(
                pitchSamples,
                context!.sampleRate,
                Math.max(20, 440 * 2 ** ((profile.midi_min - 72) / 12)),
                1500,
              )
            : null;
          setReading(
            pitch
              ? tuningReading(
                  pitch.hz,
                  profile.openStrings,
                  tunerState.current.target,
                )
              : null,
          );
        }
        setLevel(Math.min(1, peak));
        if (peak >= 0.98) setClipped(true);
        if (captureActive.current)
          setElapsed((performance.now() - began.current) / 1000);
        frame.current = requestAnimationFrame(meter);
      };
      meter();
      setConnected(true);
      setChannels(available);
      setLabel(`${inputLabel} · ${context.sampleRate.toLocaleString()} Hz`);
      await refresh();
    } catch (e) {
      media?.getTracks().forEach((t) => t.stop());
      if (context && context.state !== "closed")
        await context.close().catch(() => {});
      if (version === generation.current && alive.current) {
        setMessage(captureError(e));
        release();
      }
    } finally {
      if (version === generation.current && alive.current) setOpening(false);
    }
  }
  function record() {
    const current = connection.current;
    if (!current) return;
    if (captureActive.current) {
      current.capture.port.postMessage({ type: "stop" });
      return;
    }
    if (current.context.state !== "running") {
      setMessage(
        "Audio input was suspended. Disconnect and reconnect before recording.",
      );
      return;
    }
    chunks.current = [];
    captureActive.current = true;
    began.current = performance.now();
    setElapsed(0);
    setClipped(false);
    setRecording(true);
    callbacks.current.onRecording(true);
    current.capture.port.postMessage({
      type: "start",
      channels: current.channels,
      maxFrames: Math.round(
        Math.max(1, Math.min(60, duration)) * current.context.sampleRate,
      ),
    });
  }
  return (
    <div className="audio-input">
      <div className="input-heading">
        <Plug size={16} />
        <strong>Microphone / USB audio interface</strong>
        <button
          title="Refresh audio inputs"
          aria-label="Refresh audio inputs"
          disabled={recording || opening}
          onClick={refresh}
        >
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="input-settings">
        <label>
          Audio input
          <select
            aria-label="Audio input"
            value={deviceId}
            disabled={recording || opening}
            onChange={(e) => {
              release();
              setDeviceId(e.target.value);
              setMessage("");
            }}
          >
            <option value="">System default input</option>
            {devices
              .filter((d) => d.deviceId !== "default")
              .map((d, i) => (
                <option key={d.deviceId || i} value={d.deviceId}>
                  {d.label ||
                    `Audio input ${i + 1} — allow access to reveal name`}
                </option>
              ))}
          </select>
        </label>
        <label>
          Interface channel
          <select
            aria-label="Interface channel"
            value={mode}
            disabled={recording || opening}
            onChange={(e) => {
              release();
              setMode(e.target.value as InputMode);
            }}
          >
            <option value="input1">Input 1 · mono</option>
            <option value="input2">Input 2 · mono</option>
            <option value="stereo">Inputs 1 + 2 · stereo</option>
          </select>
        </label>
      </div>
      <p className="caution">
        Connect a class-compliant USB audio interface, then enable audio access
        to see device names. Select its instrument/Hi-Z input for guitar or
        bass, or line inputs for a keyboard’s audio outputs. USB MIDI-only
        cables do not carry sound.
      </p>
      <div className="live-tuner">
        <label className="consent">
          <input
            type="checkbox"
            checked={tunerOn}
            disabled={recording}
            onChange={(e) => {
              setTunerOn(e.target.checked);
              setReading(null);
            }}
          />
          <span>
            Optional: tune / check pitch before recording (A4 = 440 Hz)
          </span>
        </label>
        {tunerOn && (
          <>
            <p className="caution">
              {profile.id === "piano"
                ? "For checking single keys in the lower/middle register (up to 1,500 Hz) or a digital keyboard reference only. Acoustic piano tuning should be done by a qualified technician."
                : "Play one open string at a time. Tune before fitting a capo, or check the capo-adjusted targets shown here."}{" "}
              Connect the input above first. This is not a required gate, and no
              tuning result is uploaded.
            </p>
            {profile.openStrings.length > 0 && (
              <select
                aria-label="Tuner target"
                disabled={recording}
                value={target ?? "auto"}
                onChange={(e) => {
                  setTarget(
                    e.target.value === "auto" ? null : Number(e.target.value),
                  );
                  setReading(null);
                }}
              >
                <option value="auto">Auto · nearest open string</option>
                {profile.openStrings.map((m, i) => (
                  <option key={i} value={m}>
                    String {i + 1}: {note(m)}
                  </option>
                ))}
              </select>
            )}
            <div role="status" className="tuner-reading">
              {!connected
                ? "Connect an audio input to use the tuner."
                : recording
                  ? "Tuner paused during recording."
                  : reading
                    ? `${note(reading.target)} · ${reading.hz.toFixed(1)} Hz · ${reading.cents >= 0 ? "+" : ""}${reading.cents.toFixed(0)} cents · ${Math.abs(reading.cents) <= 5 ? "In tune" : reading.cents > 0 ? "Sharp — lower pitch" : "Flat — raise pitch"}`
                    : "Play a clear, sustained single note…"}
            </div>
            <p className="caution">
              Polyphony, harmonics, low signal or noise can confuse this
              experimental tuner. Verify uncertain readings with a dedicated
              tuner.
            </p>
          </>
        )}
      </div>
      <div className="input-actions">
        <button
          className="record-button"
          disabled={opening || recording || !supported}
          onClick={() => (connected ? release() : connect())}
        >
          <Plug size={15} />
          {opening
            ? "Opening input…"
            : connected
              ? "Disconnect input"
              : "Enable / connect input"}
        </button>
        <button
          className="record-button"
          disabled={!connected || opening}
          onClick={record}
        >
          {recording ? <Square size={15} /> : <Mic size={15} />}{" "}
          {recording
            ? `Stop · ${elapsed.toFixed(1)}s / ${duration}s`
            : "Record selected input"}
        </button>
      </div>
      {connected && (
        <>
          <p className="input-label">
            {label} · {channels} browser-reported channel(s)
          </p>
          <div
            className="input-level"
            role="meter"
            aria-label="Input level"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(level * 100)}
          >
            <span
              style={{
                width: `${Math.round(Math.sqrt(level) * 100)}%`,
                background: clipped ? "#b5654e" : undefined,
              }}
            />
          </div>
          <p className="caution">
            {clipped
              ? "Possible clipping detected. Lower hardware input gain; click Record to reset this warning."
              : "Watch the level meter before recording. Monitoring is silent to avoid feedback; use the interface’s direct-monitor feature and headphones."}{" "}
            No interface latency compensation is applied. Channel names are
            browser mappings, not guaranteed physical jack numbers.
          </p>
        </>
      )}
      {!supported && (
        <p className="engine-warning">
          Audio-device capture requires HTTPS and browser audio-input support.
          Upload an audio file if this device cannot expose your interface.
        </p>
      )}
      {message && (
        <p className="error" role="alert">
          {message}
        </p>
      )}
    </div>
  );
}
