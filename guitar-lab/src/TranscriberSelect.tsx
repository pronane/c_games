import { useEffect, useState } from "react";
import { AudioLines } from "lucide-react";
import { api } from "./engineApi";

/**
 * Which note detector turns audio into notes: Basic Pitch (default), Riley's guitar model,
 * GAPS or YourMT3+. The list and what is installed come from the engine.
 */
export type TranscriberId = "basic_pitch" | "riley" | "gaps" | "yourmt3";
type Option = { installed: boolean; label?: string; summary?: string; detail?: string | null; default?: boolean };
type Options = Partial<Record<TranscriberId, Option>>;

const ORDER: TranscriberId[] = ["basic_pitch", "riley", "yourmt3", "gaps"];
const KEY = "guitar-lab.transcriber";
let cached: Promise<Options> | null = null;
function options() {
  return (cached ??= api<{ models: { transcription?: { alternatives?: Options } } }>("/api/health")
    .then((h) => h.models.transcription?.alternatives ?? {})
    .catch(() => {
      cached = null;
      return {} as Options;
    }));
}

const listeners = new Set<(t: TranscriberId) => void>();
let shared: TranscriberId | null = null;
/** The browser's remembered choice, if any; otherwise the engine's default is used. */
function remembered(): TranscriberId | null {
  try {
    const v = localStorage.getItem(KEY);
    if (v && (ORDER as string[]).includes(v)) return v as TranscriberId;
  } catch {}
  return null;
}
const engineDefault = (o: Options): TranscriberId =>
  (ORDER.find((id) => o[id]?.default && o[id]?.installed) ?? "basic_pitch") as TranscriberId;

/** One choice for the whole studio, remembered in this browser. */
export function useTranscriber(): [TranscriberId, (t: TranscriberId) => void] {
  const [value, set] = useState<TranscriberId>(() => shared ?? remembered() ?? "basic_pitch");
  useEffect(() => {
    listeners.add(set);
    // No choice made yet in this browser: take the engine's default once it answers.
    if (!shared && !remembered())
      options().then((o) => {
        if (!shared) {
          shared = engineDefault(o);
          listeners.forEach((l) => l(shared!));
        }
      });
    else shared ??= remembered();
    return () => void listeners.delete(set);
  }, []);
  return [
    value,
    (t) => {
      shared = t;
      try {
        localStorage.setItem(KEY, t);
      } catch {}
      listeners.forEach((l) => l(t));
    },
  ];
}

export default function TranscriberSelect({ disabled }: { disabled?: boolean }) {
  const [value, setValue] = useTranscriber();
  const [opts, setOpts] = useState<Options>({});
  useEffect(() => {
    let live = true;
    options().then((o) => {
      if (!live) return;
      setOpts(o);
      // A remembered choice that this engine can't run falls back to the default.
      if (o[value] && !o[value]!.installed) setValue(engineDefault(o));
    });
    return () => {
      live = false;
    };
  }, []);
  const chosen = opts[value];
  return (
    <label className="speed transcriber-select">
      <AudioLines size={13} /> Note detector
      <select id="transcriber" value={value} disabled={disabled} onChange={(e) => setValue(e.target.value as TranscriberId)}>
        {ORDER.filter((id) => id === "basic_pitch" || opts[id]).map((id) => (
          <option key={id} value={id} disabled={id !== "basic_pitch" && !opts[id]?.installed}>
            {(opts[id]?.label ?? (id === "basic_pitch" ? "Basic Pitch" : id)) +
              (opts[id]?.default ? " (default)" : id === "basic_pitch" || opts[id]?.installed ? "" : " (not installed)")}
          </option>
        ))}
      </select>
      {chosen?.summary && <small className="helper">{chosen.summary}</small>}
      {Object.values(opts).some((o) => o && !o.installed) && (
        <small className="helper">Greyed-out detectors need installing on the engine; see the README.</small>
      )}
    </label>
  );
}
