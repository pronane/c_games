import { Sliders } from "lucide-react";
import { DRIVES, type GuitarSound, type ToneEstimate } from "./guitarTone";

/** Amp and pedals for the app's own guitar sound. Changes the sound only, never the notes. */
export default function GuitarSoundPicker({
  sound,
  onChange,
  detected,
  note,
}: {
  sound: GuitarSound;
  onChange: (s: GuitarSound) => void;
  detected?: ToneEstimate | null;
  note?: string;
}) {
  const pedal = (key: "chorus" | "delay" | "reverb", label: string) => (
    <label className="speed">
      <input id={`sound-${key}`} type="checkbox" checked={sound[key]} onChange={(e) => onChange({ ...sound, [key]: e.target.checked })} />
      {label}
    </label>
  );
  return (
    <div className="guitar-sound" aria-label="Guitar sound">
      <label className="speed">
        <Sliders size={13} /> Amp
        <select id="sound-drive" value={sound.drive} onChange={(e) => onChange({ ...sound, drive: e.target.value as GuitarSound["drive"] })}>
          {DRIVES.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
        </select>
      </label>
      {pedal("chorus", "Chorus")}
      {pedal("delay", "Delay")}
      {pedal("reverb", "Reverb")}
      {detected && (
        <span className="helper">
          Heard in the song: <b>{detected.tone === "uncertain" ? "not sure" : detected.tone}</b>
          {detected.tone !== "uncertain" && detected.tone !== sound.drive && (
            <>
              {" "}
              <button className="link-button" onClick={() => onChange({ ...sound, drive: detected.tone as GuitarSound["drive"] })}>
                use it
              </button>
            </>
          )}
        </span>
      )}
      {note && <span className="helper">{note}</span>}
    </div>
  );
}
