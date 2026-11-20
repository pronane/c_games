import { Headphones, Sliders } from "lucide-react";
import { DRIVES } from "./guitarTone";
import type { PlayerSound } from "./liveTone";

/**
 * Your amp and pedals for recording. Changes what you hear (live, and when your take plays
 * back), never what is marked: the take is recorded and checked dry.
 */
export default function YourSound({
  sound,
  onChange,
  latencyMs,
  trying,
  onTry,
  disabled,
}: {
  sound: PlayerSound;
  onChange: (s: PlayerSound) => void;
  latencyMs?: number | null;
  trying: boolean;
  onTry: () => void;
  disabled?: boolean;
}) {
  const pedal = (key: "chorus" | "delay" | "reverb", label: string) => (
    <label className="speed">
      <input id={`your-${key}`} type="checkbox" checked={sound[key]} onChange={(e) => onChange({ ...sound, [key]: e.target.checked })} />
      {label}
    </label>
  );
  return (
    <div className="guitar-sound your-sound" aria-label="Your sound">
      <span className="processing-label">Your sound</span>
      <label className="speed">
        <Sliders size={13} /> Amp
        <select id="your-drive" value={sound.drive} onChange={(e) => onChange({ ...sound, drive: e.target.value as PlayerSound["drive"] })}>
          {DRIVES.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
      </label>
      {pedal("chorus", "Chorus")}
      {pedal("delay", "Delay")}
      {pedal("reverb", "Reverb")}
      <label className="speed">
        <input id="your-monitor" type="checkbox" checked={sound.monitor} onChange={(e) => onChange({ ...sound, monitor: e.target.checked })} />
        <Headphones size={13} /> Hear myself while recording
      </label>
      {sound.monitor && (
        <label className="speed">
          Level
          <input
            id="your-level"
            type="range"
            min={0}
            max={1.5}
            step={0.05}
            value={sound.level}
            onChange={(e) => onChange({ ...sound, level: Number(e.target.value) })}
          />
        </label>
      )}
      <button className="secondary" disabled={disabled} onClick={onTry}>
        <Headphones size={14} /> {trying ? "Stop listening" : "Try the sound"}
      </button>
      <small className="helper">
        Your take is recorded clean and checked clean (that is what the note detector reads best); the amp and pedals only
        change what you hear, so you can change them after recording too.
        {sound.monitor && " Use headphones: through speakers the microphone picks the sound up again."}
        {sound.monitor &&
          (latencyMs != null
            ? ` On this device you will hear yourself about ${latencyMs} ms late${latencyMs > 30 ? ", which can feel laggy; an audio interface with its own direct monitoring is better" : ""}.`
            : " Run the delay check below to see how late you will hear yourself.")}
      </small>
    </div>
  );
}
