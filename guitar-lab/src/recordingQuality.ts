export type RecordingQuality = {
  version: 1; seconds: number; peak: number; rmsDb: number; clippedFraction: number;
  status: 'no_signal' | 'low_level' | 'ceiling' | 'usable';
};
/** Signal-health heuristics only: not a noise estimator, tone judgement or calibrated confidence. */
export function recordingQuality(channels: Float32Array[], rate: number): RecordingQuality {
  if (!Number.isFinite(rate) || rate < 1 || !channels.length) throw Error('Invalid recording sample rate or channels.');
  let peak = 0, sum = 0, clipped = 0, count = 0;
  for (const channel of channels) for (const raw of channel) {
    if (!Number.isFinite(raw)) throw Error('Recording contains non-finite samples.');
    const level = Math.abs(raw); peak = Math.max(peak, level); sum += raw * raw; count++;
    if (level >= .999) clipped++;
  }
  const rmsDb = Math.max(-120, 20 * Math.log10(Math.max(1e-6, Math.sqrt(sum / Math.max(1, count)))));
  const clippedFraction = clipped / Math.max(1, count);
  const status = peak < .0002 && rmsDb < -75 ? 'no_signal' : clippedFraction >= .02 ? 'ceiling' : rmsDb < -45 ? 'low_level' : 'usable';
  return { version: 1, seconds: channels[0].length / rate, peak, rmsDb, clippedFraction, status };
}
export function qualityMessage(q: RecordingQuality) {
  if (q.status === 'no_signal') return 'Almost no input signal. Check the selected microphone/interface, cable and input gain. No automatic grade was requested.';
  if (q.status === 'low_level') return 'Very low average input level. Play through the phrase and check gain/distance; rests also lower this measurement. Listen before trusting note findings.';
  if (q.status === 'ceiling') return 'Many samples reach the digital ceiling. Check interface gain and listen for clipping. Intentional distortion can also cause this pattern; it is not proof of a playing mistake.';
  return 'No basic level problem detected. This does not verify tuning, noise, separation, latency or note accuracy.';
}
export function validateQuality(q: RecordingQuality) {
  return !!q && q.version === 1 && Number.isFinite(q.seconds) && q.seconds >= 0 && q.seconds <= 1200 && Number.isFinite(q.peak) && q.peak >= 0 && q.peak <= 100 && Number.isFinite(q.rmsDb) && q.rmsDb >= -120 && q.rmsDb <= 40 && Number.isFinite(q.clippedFraction) && q.clippedFraction >= 0 && q.clippedFraction <= 1 && ['no_signal','low_level','ceiling','usable'].includes(q.status);
}
