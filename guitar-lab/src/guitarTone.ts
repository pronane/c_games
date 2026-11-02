import { useEffect, useState } from "react";

/**
 * The sound the app's own guitar plays with: an amp setting (clean, crunch or distorted) and a
 * few common pedals. It only changes how the app's playback sounds, never the notes, so a
 * distorted song can be played back distorted and compared by ear.
 */
export type Drive = "clean" | "crunch" | "distorted";
export type GuitarSound = { drive: Drive; chorus: boolean; delay: boolean; reverb: boolean };
export type ToneEstimate = {
  tone: Drive | "uncertain";
  /** What the player chose before the breakdown, and the sound the notes were transcribed for. */
  chosen?: "auto" | Drive;
  used?: Drive | "uncertain";
  brightness: number;
  loudness_spread_db: number;
  detail: string;
};

export const DEFAULT_SOUND: GuitarSound = { drive: "clean", chorus: false, delay: false, reverb: false };
export const DRIVES: { id: Drive; label: string }[] = [
  { id: "clean", label: "Clean" },
  { id: "crunch", label: "Crunch (light overdrive)" },
  { id: "distorted", label: "Distorted (high gain)" },
];

// Pre-gain into the clipper, and how far the "speaker cabinet" rolls off the top end.
const AMP: Record<Drive, { gain: number; cab: number; out: number }> = {
  clean: { gain: 1, cab: 0, out: 1 },
  crunch: { gain: 12, cab: 5500, out: 0.5 },
  distorted: { gain: 150, cab: 4200, out: 0.35 },
};

function onePoleLowpass(x: Float32Array, rate: number, hz: number) {
  const a = Math.exp((-2 * Math.PI * hz) / rate);
  let y = 0;
  for (let i = 0; i < x.length; i++) x[i] = y = (1 - a) * x[i] + a * y;
}

function highpass(x: Float32Array, rate: number, hz: number) {
  const a = Math.exp((-2 * Math.PI * hz) / rate);
  let px = 0,
    py = 0;
  for (let i = 0; i < x.length; i++) {
    const y = a * (py + x[i] - px);
    px = x[i];
    x[i] = py = y;
  }
}

/** Apply the amp and pedals in place to the app's synthesized guitar (mono). */
export function applySound(x: Float32Array, rate: number, sound: GuitarSound) {
  const amp = AMP[sound.drive];
  if (sound.drive !== "clean") {
    // Tighten the lows before the clipper (as most drive pedals do), clip, then the cabinet.
    highpass(x, rate, 80);
    const norm = Math.tanh(amp.gain);
    for (let i = 0; i < x.length; i++) x[i] = (Math.tanh(x[i] * amp.gain) / norm) * amp.out;
    onePoleLowpass(x, rate, amp.cab);
    onePoleLowpass(x, rate, amp.cab * 1.4);
  }
  if (sound.chorus) {
    // A slowly swept copy, 7-13 ms behind.
    const dry = x.slice(),
      base = 0.01 * rate,
      depth = 0.003 * rate;
    for (let i = 0; i < x.length; i++) {
      const d = base + depth * Math.sin((2 * Math.PI * 0.8 * i) / rate),
        j = i - d,
        k = Math.floor(j);
      if (k < 0) continue;
      const f = j - k,
        v = dry[k] * (1 - f) + (dry[k + 1] ?? 0) * f;
      x[i] = 0.75 * dry[i] + 0.5 * v;
    }
  }
  if (sound.delay) {
    // Three-repeat echo at 340 ms, each repeat darker and quieter.
    const gap = Math.round(0.34 * rate);
    for (let i = gap; i < x.length; i++) x[i] += 0.35 * x[i - gap];
  }
  if (sound.reverb) {
    // A small room: a few parallel feedback combs.
    const dry = x.slice();
    for (const [ms, fb] of [[29.7, 0.77], [37.1, 0.75], [41.1, 0.73], [43.7, 0.71]]) {
      const d = Math.round((ms / 1000) * rate),
        comb = new Float32Array(x.length);
      for (let i = 0; i < x.length; i++) comb[i] = dry[i] + (i >= d ? fb * comb[i - d] : 0);
      for (let i = 0; i < x.length; i++) x[i] += 0.06 * comb[i];
    }
  }
  return x;
}

/** The detected tone as a starting setting. */
export function soundFromEstimate(estimate: ToneEstimate | null | undefined, current: GuitarSound): GuitarSound {
  if (estimate?.chosen && estimate.chosen !== "auto") return { ...current, drive: estimate.chosen };
  if (!estimate || estimate.tone === "uncertain") return current;
  return { ...current, drive: estimate.tone };
}

const KEY = "guitar-lab.sound";
function load(): GuitarSound {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_SOUND, ...JSON.parse(raw) };
  } catch {}
  return DEFAULT_SOUND;
}
const listeners = new Set<(s: GuitarSound) => void>();
let shared: GuitarSound | null = null;

/** One guitar sound for the whole app, remembered in this browser. */
export function useGuitarSound(): [GuitarSound, (s: GuitarSound) => void] {
  const [sound, set] = useState<GuitarSound>(() => (shared ??= load()));
  useEffect(() => {
    listeners.add(set);
    return () => void listeners.delete(set);
  }, []);
  const update = (s: GuitarSound) => {
    shared = s;
    try {
      localStorage.setItem(KEY, JSON.stringify(s));
    } catch {}
    listeners.forEach((l) => l(s));
  };
  return [sound, update];
}
