import * as alphaTab from "@coderline/alphatab";
// General MIDI sound bank shipped with alphaTab (SONiVOX EAS, Apache-2.0), served from our origin.
import soundBankUrl from "@coderline/alphatab/soundfont/sonivox.sf2?url";

/**
 * Renders a tab/score file with its own instruments (the program each track asks for:
 * distortion guitar, bass, drums...), with repeats played out exactly as `playbackOrder`
 * times them. Runs on the main thread in chunks so the page stays responsive.
 */
let bank: Promise<Uint8Array> | null = null;
function soundBank() {
  return (bank ??= fetch(soundBankUrl).then(async (r) => {
    if (!r.ok) throw Error("The instrument sounds could not be loaded.");
    return new Uint8Array(await r.arrayBuffer());
  }));
}

const silentOutput = () =>
  ({
    sampleRate: 44100,
    ready: { on() {}, off() {} },
    samplesPlayed: { on() {}, off() {} },
    sampleRequest: { on() {}, off() {} },
    open() {},
    play() {},
    destroy() {},
    pause() {},
    addSamples() {},
    resetSamples() {},
    activate() {},
    enumerateOutputDevices: async () => [],
    setOutputDevice: async () => {},
    getOutputDevice: async () => null,
  }) as unknown as alphaTab.synth.ISynthOutput;

/** Channels a track plays on (Guitar Pro tracks use a primary and an effects channel). */
function channelsOf(score: alphaTab.model.Score, track: number) {
  const info = score.tracks[track]?.playbackInfo;
  return info ? [...new Set([info.primaryChannel, info.secondaryChannel])] : [];
}

export type FileMix = { tracks: Map<number, number> };

/**
 * Stereo audio of [from, to) seconds (as timed by scoreToPiece) at `rate`.
 * `volume(track)` sets each track's level (0 mutes it).
 */
export async function renderFile(
  score: alphaTab.model.Score,
  from: number,
  to: number,
  rate: number,
  volume: (track: number) => number = () => 1,
): Promise<[Float32Array, Float32Array]> {
  const midi = new alphaTab.midi.MidiFile(),
    generator = new alphaTab.midi.MidiFileGenerator(score, null, new alphaTab.midi.AlphaSynthMidiFileHandler(midi));
  generator.generate();
  const options = new alphaTab.synth.AudioExportOptions();
  options.soundFonts = [await soundBank()];
  // The synthesizer misbehaves at low rates; 44.1/48 kHz are what browsers use anyway.
  options.sampleRate = rate >= 44100 ? rate : 44100;
  options.masterVolume = 1;
  options.metronomeVolume = 0;
  options.useSyncPoints = false;
  options.trackVolume = new Map();
  options.trackTranspositionPitches = new Map();
  score.tracks.forEach((_, i) => channelsOf(score, i).forEach((ch) => options.trackVolume.set(ch, volume(i))));
  const synth = new alphaTab.synth.AlphaSynth(silentOutput(), 500),
    exporter = synth.exportAudio(options, midi, [], generator.transpositionPitches);
  const frames = Math.max(1, Math.ceil((to - from) * rate)),
    out: [Float32Array, Float32Array] = [new Float32Array(frames), new Float32Array(frames)],
    step = options.sampleRate / rate;
  let t = 0; // seconds rendered so far
  try {
    for (;;) {
      const chunk = await exporter.render(2000);
      if (!chunk) break;
      const n = chunk.samples.length / 2;
      const chunkStart = t;
      t += n / options.sampleRate;
      if (t < from) continue;
      // Interleaved stereo at the synth's rate -> our rate, only the wanted window.
      const first = Math.max(0, Math.floor((chunkStart - from) * rate)),
        last = Math.min(frames, Math.ceil((t - from) * rate));
      for (let i = first; i < last; i++) {
        const src = (from - chunkStart) * options.sampleRate + i * step;
        if (src < 0) continue;
        if (src >= n) break;
        const k = Math.floor(src);
        out[0][i] = chunk.samples[2 * k];
        out[1][i] = chunk.samples[2 * k + 1];
      }
      if (t >= to) break;
      await new Promise((r) => setTimeout(r, 0));
    }
  } finally {
    (exporter as { destroy?: () => void }).destroy?.();
  }
  return out;
}

/** Amp setting suggested by a track's General MIDI program. */
export function driveForProgram(program: number | undefined) {
  if (program === 30) return "distorted" as const; // Distortion Guitar
  if (program === 29) return "crunch" as const; // Overdriven Guitar
  if (program !== undefined && program >= 24 && program <= 28) return "clean" as const;
  return null;
}
