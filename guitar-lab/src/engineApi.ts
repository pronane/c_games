import type { InstrumentProfile, Notation } from "./instruments";
export type InstrumentSnapshot = InstrumentProfile & {
  tuning: string;
  capo: number;
  notation: Notation;
  open_strings: number[];
  max_fret: number;
};
export type EngineNote = {
  id: number;
  time: number;
  duration: number;
  midi: number;
  amplitude: number;
  string?: number | null;
  fret?: number | null;
};
export type EngineResult = {
  alignment: {
    map: number[][];
    mean_chroma_cost: number;
    confidence: string;
    median_offset_seconds: number;
    reference_seconds_per_take_second: number;
    warning: string;
  };
  reference_notes: EngineNote[];
  take_notes: EngineNote[];
  comparison: {
    findings: {
      kind: string;
      take_time?: number;
      reference_time?: number;
      take_midi?: number;
      reference_midi?: number;
      raw_timing_seconds?: number;
      duration_difference_seconds?: number;
      detail?: string;
    }[];
    mean_absolute_timing_seconds: number | null;
    pitch_difference_candidates: number;
    uncertainty: string;
  };
  provenance: {
    separation: { model: string; device: string; warning?: string };
    transcription: string;
    edited: boolean;
    instrument_profile: InstrumentSnapshot;
  };
  warnings: string[];
};
export type Job = {
  id: string;
  status: string;
  stage: string;
  error: string | null;
  guitar_url: string | null;
  device: { model?: string; device?: string; warning?: string };
  duration: number;
  original_offset: number;
  instrument_profile: InstrumentSnapshot;
  expires_at: number;
  result: EngineResult | null;
};
export type Health = {
  models: {
    separation: {
      configured: boolean;
      model: string;
      runtime_installed?: boolean;
      weights_verified?: boolean;
      installation_supported?: boolean;
      download_url?: string;
      detail?: string;
    };
    transcription: { configured: boolean; model: string };
    device_policy: string;
  };
  retention_seconds: number;
};
export async function api<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: { "X-Fretwork-Client": "studio", ...options.headers },
  });
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: `Engine request failed (${response.status})` }));
    throw Error(
      typeof body.detail === "string"
        ? body.detail
        : JSON.stringify(body.detail),
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function encodeWav(channels: Float32Array[], sampleRate: number) {
  const frames = channels[0].length,
    count = channels.length,
    buffer = new ArrayBuffer(44 + frames * count * 2),
    v = new DataView(buffer);
  const text = (offset: number, s: string) =>
    [...s].forEach((c, i) => v.setUint8(offset + i, c.charCodeAt(0)));
  text(0, "RIFF");
  v.setUint32(4, 36 + frames * count * 2, true);
  text(8, "WAVE");
  text(12, "fmt ");
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, count, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * count * 2, true);
  v.setUint16(32, count * 2, true);
  v.setUint16(34, 16, true);
  text(36, "data");
  v.setUint32(40, frames * count * 2, true);
  for (let i = 0; i < frames; i++)
    for (let c = 0; c < count; c++) {
      const n = Math.max(-1, Math.min(1, channels[c][i]));
      v.setInt16(
        44 + (i * count + c) * 2,
        Math.round(n * (n < 0 ? 32768 : 32767)),
        true,
      );
    }
  return new Blob([buffer], { type: "audio/wav" });
}
export async function excerpt(
  buffer: AudioBuffer,
  start: number,
  duration: number,
) {
  const context = new OfflineAudioContext(
      Math.min(2, buffer.numberOfChannels),
      Math.ceil(duration * 44100),
      44100,
    ),
    source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);
  source.start(0, start, duration);
  const rendered = await context.startRendering();
  return encodeWav(
    Array.from({ length: rendered.numberOfChannels }, (_, i) =>
      rendered.getChannelData(i),
    ),
    44100,
  );
}
