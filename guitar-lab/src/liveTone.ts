// The player's own amp and pedals, as Web Audio nodes: heard live while recording, and applied
// to the recorded take afterwards. The recording itself is always kept dry (the clean guitar),
// because that is what the note detector reads best; the effects only change what you hear,
// so they can be changed after the take without playing it again.
import { useEffect, useState } from "react";
import { AMP, DEFAULT_SOUND, type GuitarSound } from "./guitarTone";

/** The clipper's transfer curve: tanh(gain·x), normalised so a full-scale input stays full scale. */
export function driveCurve(gain: number, out: number, size = 2048) {
  const curve = new Float32Array(size),
    norm = Math.tanh(gain);
  for (let i = 0; i < size; i++) {
    const x = (i / (size - 1)) * 2 - 1;
    curve[i] = (Math.tanh(x * gain) / norm) * out;
  }
  return curve;
}

/** A small-room impulse response: decaying noise, the same every time (seeded). */
export function roomImpulse(rate: number, seconds = 1.2, seed = 7) {
  const n = Math.round(seconds * rate),
    left = new Float32Array(n),
    right = new Float32Array(n);
  let s = seed;
  const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296) * 2 - 1;
  for (let i = 0; i < n; i++) {
    const env = Math.pow(1 - i / n, 3) * Math.exp((-3 * i) / n);
    left[i] = rnd() * env;
    right[i] = rnd() * env;
  }
  return [left, right];
}

export type ToneChain = { input: AudioNode; output: AudioNode; stop: () => void };

/** input → (drive → cabinet) → chorus → delay → reverb → output, for any (offline) context. */
export function buildToneChain(c: BaseAudioContext, sound: GuitarSound): ToneChain {
  const input = c.createGain(),
    output = c.createGain();
  let node: AudioNode = input;
  const oscillators: OscillatorNode[] = [];
  if (sound.drive !== "clean") {
    const amp = AMP[sound.drive],
      tighten = c.createBiquadFilter(),
      shaper = c.createWaveShaper(),
      cab1 = c.createBiquadFilter(),
      cab2 = c.createBiquadFilter();
    tighten.type = "highpass";
    tighten.frequency.value = 80;
    shaper.curve = driveCurve(amp.gain, amp.out);
    shaper.oversample = "4x";
    cab1.type = cab2.type = "lowpass";
    cab1.frequency.value = amp.cab;
    cab2.frequency.value = amp.cab * 1.4;
    cab1.Q.value = cab2.Q.value = 0.5;
    node.connect(tighten).connect(shaper).connect(cab1).connect(cab2);
    node = cab2;
  }
  if (sound.chorus) {
    // A slowly swept copy, 7-13 ms behind, mixed under the dry signal.
    const mix = c.createGain(),
      dry = c.createGain(),
      wet = c.createGain(),
      line = c.createDelay(0.05),
      lfo = c.createOscillator(),
      depth = c.createGain();
    dry.gain.value = 0.75;
    wet.gain.value = 0.5;
    line.delayTime.value = 0.01;
    lfo.frequency.value = 0.8;
    depth.gain.value = 0.003;
    lfo.connect(depth).connect(line.delayTime);
    lfo.start();
    oscillators.push(lfo);
    node.connect(dry).connect(mix);
    node.connect(line).connect(wet).connect(mix);
    node = mix;
  }
  if (sound.delay) {
    // Echo at 340 ms, each repeat quieter and darker.
    const mix = c.createGain(),
      line = c.createDelay(1),
      feedback = c.createGain(),
      tone = c.createBiquadFilter();
    line.delayTime.value = 0.34;
    feedback.gain.value = 0.35;
    tone.type = "lowpass";
    tone.frequency.value = 3500;
    node.connect(mix);
    node.connect(line).connect(tone).connect(feedback).connect(line);
    tone.connect(mix);
    node = mix;
  }
  if (sound.reverb) {
    const mix = c.createGain(),
      room = c.createConvolver(),
      wet = c.createGain(),
      [l, r] = roomImpulse(c.sampleRate),
      ir = c.createBuffer(2, l.length, c.sampleRate);
    ir.getChannelData(0).set(l);
    ir.getChannelData(1).set(r);
    room.buffer = ir;
    wet.gain.value = 0.25;
    node.connect(mix);
    node.connect(room).connect(wet).connect(mix);
    node = mix;
  }
  node.connect(output);
  return {
    input,
    output,
    stop: () =>
      oscillators.forEach((o) => {
        try {
          o.stop();
        } catch {}
      }),
  };
}

export const isDry = (sound: GuitarSound) => sound.drive === "clean" && !sound.chorus && !sound.delay && !sound.reverb;

/** The dry take played through the chosen amp and pedals (a "re-amp"), as a mono buffer. */
export async function reamp(take: AudioBuffer, sound: GuitarSound): Promise<AudioBuffer> {
  if (isDry(sound)) return take;
  const tail = sound.delay || sound.reverb ? 1.5 : 0,
    rate = take.sampleRate,
    c = new OfflineAudioContext(1, take.length + Math.round(tail * rate), rate),
    source = c.createBufferSource(),
    chain = buildToneChain(c, sound);
  source.buffer = take;
  source.connect(chain.input);
  chain.output.connect(c.destination);
  source.start();
  const out = await c.startRendering();
  // Keep the take's length so it still lines up with the song, and its level comparable.
  const result = new AudioBuffer({ length: take.length, numberOfChannels: 1, sampleRate: rate }),
    wet = out.getChannelData(0).subarray(0, take.length),
    dry = take.getChannelData(0);
  let peakDry = 0,
    peakWet = 0;
  for (let i = 0; i < dry.length; i++) {
    peakDry = Math.max(peakDry, Math.abs(dry[i]));
    peakWet = Math.max(peakWet, Math.abs(wet[i]));
  }
  const scale = peakWet > 0 ? Math.min(4, (peakDry || 1) / peakWet) : 1;
  const data = result.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = wet[i] * scale;
  return result;
}

// ------------------------------------------------------------------ the player's setting
export type PlayerSound = GuitarSound & { monitor: boolean; level: number };
export const DEFAULT_PLAYER: PlayerSound = { ...DEFAULT_SOUND, monitor: false, level: 0.8 };
const KEY = "guitar-lab.player-sound";

function load(): PlayerSound {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULT_PLAYER, ...JSON.parse(raw) };
  } catch {}
  return DEFAULT_PLAYER;
}

/** Your amp and pedals (separate from the app's own playback sound), remembered in this browser. */
export function usePlayerSound(): [PlayerSound, (s: PlayerSound) => void] {
  const [sound, set] = useState<PlayerSound>(load);
  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(sound));
    } catch {}
  }, [sound]);
  return [sound, set];
}
