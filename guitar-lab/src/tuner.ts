// YIN-style cumulative mean-normalised difference. Single sustained notes only.
export function detectPitch(
  input: Float32Array,
  sampleRate: number,
  minHz = 25,
  maxHz = 1500,
): { hz: number; clarity: number } | null {
  const step = Math.max(1, Math.floor(sampleRate / 12000)),
    rate = sampleRate / step;
  const samples = Float32Array.from(
    { length: Math.floor(input.length / step) },
    (_, i) => input[i * step],
  );
  let mean = 0,
    energy = 0;
  for (const n of samples) mean += n;
  mean /= samples.length;
  for (let i = 0; i < samples.length; i++) {
    samples[i] -= mean;
    energy += samples[i] ** 2;
  }
  if (Math.sqrt(energy / samples.length) < 0.006) return null;
  const maxLag = Math.min(
      Math.floor(rate / minHz),
      Math.floor(samples.length / 2),
    ),
    minLag = Math.max(2, Math.floor(rate / maxHz)),
    size = samples.length - maxLag;
  if (size < 32) return null;
  const difference = new Float64Array(maxLag + 1);
  let sum = 0;
  for (let lag = 1; lag <= maxLag; lag++) {
    let d = 0;
    for (let j = 0; j < size; j++) d += (samples[j] - samples[j + lag]) ** 2;
    sum += d;
    difference[lag] = sum ? (d * lag) / sum : 1;
  }
  for (let lag = minLag; lag < maxLag - 1; lag++)
    if (difference[lag] < 0.15) {
      while (lag + 1 < maxLag && difference[lag + 1] < difference[lag]) lag++;
      const a = difference[lag - 1],
        b = difference[lag],
        c = difference[lag + 1],
        den = a - 2 * b + c,
        shift = den ? (a - c) / (2 * den) : 0;
      const hz = rate / (lag + shift);
      return hz >= minHz && hz <= maxHz ? { hz, clarity: 1 - b } : null;
    }
  return null;
}
// referenceCents shifts A4 away from 440 Hz, e.g. +30 for a recording that sits sharp.
export function tuningReading(
  hz: number,
  targets: number[],
  manual: number | null = null,
  referenceCents = 0,
) {
  const a4 = 440 * 2 ** (referenceCents / 1200),
    midi = 69 + 12 * Math.log2(hz / a4),
    target =
      manual ??
      (targets.length
        ? targets.reduce((a, b) =>
            Math.abs(a - midi) < Math.abs(b - midi) ? a : b,
          )
        : Math.round(midi));
  return {
    target,
    cents: 1200 * Math.log2(hz / (a4 * 2 ** ((target - 69) / 12))),
    hz,
  };
}
