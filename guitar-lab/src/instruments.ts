import catalogue from "../shared/instruments.json";
export type InstrumentId = "guitar" | "bass" | "piano";
export type Notation = "tablature" | "notes";
export type InstrumentProfile = {
  id: InstrumentId;
  name: string;
  midi_min: number;
  midi_max: number;
  separation_stem: string;
  transcription_method: string;
  default_notation: Notation;
  notations: Notation[];
  supports_capo: boolean;
  tunings: Record<string, number[]>;
  feedback: string[];
  status: string;
};
export type InstrumentSettings = {
  instrument: InstrumentId;
  tuning: string;
  capo: number;
  notation: Notation;
};
export const instruments = catalogue as InstrumentProfile[];
export function defaultSettings(
  instrument: InstrumentId = "guitar",
): InstrumentSettings {
  const p = instruments.find((p) => p.id === instrument)!;
  return {
    instrument,
    tuning: Object.keys(p.tunings)[0] ?? "none",
    capo: 0,
    notation: p.default_notation,
  };
}
export function resolveInstrument(settings: InstrumentSettings) {
  const profile = instruments.find((p) => p.id === settings.instrument);
  if (!profile) throw Error("Unknown instrument");
  const tuning = profile.tunings[settings.tuning] ?? [];
  if (Object.keys(profile.tunings).length && !tuning.length)
    throw Error("Unsupported tuning");
  if (
    !Object.keys(profile.tunings).length &&
    !["none", "standard"].includes(settings.tuning)
  )
    throw Error("Unsupported tuning");
  if (
    !Number.isInteger(settings.capo) ||
    settings.capo < 0 ||
    settings.capo > 12 ||
    (!profile.supports_capo && settings.capo !== 0)
  )
    throw Error("Invalid capo setting");
  if (!profile.notations.includes(settings.notation))
    throw Error("Unsupported notation");
  const openStrings = tuning.map((m) => m + settings.capo);
  return {
    ...profile,
    settings,
    openStrings,
    midi_min: tuning.length ? Math.min(...openStrings) : profile.midi_min,
    midi_max: tuning.length
      ? Math.min(profile.midi_max, Math.max(...tuning) + 24)
      : profile.midi_max,
    maxFret: 24 - settings.capo,
  };
}
export type ResolvedInstrument = ReturnType<typeof resolveInstrument>;
export function tabPosition(midi: number, profile: ResolvedInstrument) {
  return profile.openStrings
    .map((n, i) => ({ string: i + 1, fret: midi - n }))
    .filter((p) => p.fret >= 0 && p.fret <= profile.maxFret)
    .sort((a, b) => a.fret - b.fret)[0];
}
