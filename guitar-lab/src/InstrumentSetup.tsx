import {
  instruments,
  defaultSettings,
  resolveInstrument,
  type InstrumentSettings,
} from "./instruments";
import { note } from "./analysis";
export default function InstrumentSetup({
  settings,
  onChange,
  disabled,
}: {
  settings: InstrumentSettings;
  onChange: (s: InstrumentSettings) => void;
  disabled: boolean;
}) {
  const profile = resolveInstrument(settings);
  return (
    <section className="panel instrument-setup">
      <div className="eyebrow">BEFORE YOU PLAY</div>
      <h2>Choose your instrument</h2>
      <div className="profile-fields">
        <label>
          Instrument
          <select
            aria-label="Instrument profile"
            disabled={disabled}
            value={settings.instrument}
            onChange={(e) =>
              onChange(
                defaultSettings(
                  e.target.value as InstrumentSettings["instrument"],
                ),
              )
            }
          >
            {instruments.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        {profile.openStrings.length > 0 && (
          <label>
            Tuning
            <select
              aria-label="Instrument tuning"
              disabled={disabled}
              value={settings.tuning}
              onChange={(e) =>
                onChange({ ...settings, tuning: e.target.value })
              }
            >
              {Object.keys(profile.tunings).map((t) => (
                <option key={t} value={t}>
                  {t.replaceAll("_", " ").toUpperCase()}
                </option>
              ))}
            </select>
          </label>
        )}
        {profile.supports_capo && (
          <label>
            Capo fret
            <select
              aria-label="Capo fret"
              disabled={disabled}
              value={settings.capo}
              onChange={(e) =>
                onChange({ ...settings, capo: Number(e.target.value) })
              }
            >
              {Array.from({ length: 13 }, (_, i) => (
                <option key={i} value={i}>
                  {i === 0 ? "No capo" : i}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Preferred notation
          <select
            aria-label="Preferred notation"
            disabled={disabled}
            value={settings.notation}
            onChange={(e) =>
              onChange({
                ...settings,
                notation: e.target.value as InstrumentSettings["notation"],
              })
            }
          >
            {profile.notations.map((n) => (
              <option key={n} value={n}>
                {n === "tablature" ? "Tablature" : "Note events"}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="caution">
        Range: {note(profile.midi_min)}–{note(profile.midi_max)} · Reference
        stem: {profile.separation_stem} · Transcription: Basic Pitch ONNX.
        <br />
        {profile.openStrings.length
          ? `Open strings (high → low, including capo): ${profile.openStrings.map(note).join(" · ")}. `
          : ""}
        {profile.status}
      </p>
      <p className="caution">
        Feedback enabled: pitch, timing and sustain candidates
        {profile.feedback.includes("chord_estimates")
          ? ", plus approximate chord labels in the local preview"
          : ""}
        . No pressure/buzz diagnosis or calibrated accuracy score. Piano uses
        note events; staff engraving is not available. Changing the profile
        resets the current take and comparison to prevent mismatched settings.
      </p>
    </section>
  );
}
