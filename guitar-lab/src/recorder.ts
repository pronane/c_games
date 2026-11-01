// Microphone / USB-input capture shared by the song and tab lessons: one AudioWorklet that
// records mono PCM, plus the one-time delay check. Browser-only.
import { inputConstraints, mergeCapture } from "./audioInputs";
import { addClicks, detectHits, jitteredTimes, saveLatency, summariseLatency, type LatencyResult } from "./practice";

export class Recorder {
  private mic: { stream: MediaStream; node: AudioWorkletNode } | null = null;
  constructor(public context: AudioContext) {}

  async ensure() {
    if (this.mic) return;
    const c = this.context;
    const stream = await navigator.mediaDevices.getUserMedia(inputConstraints(""));
    await c.audioWorklet.addModule(new URL("./capture.worklet.js?no-inline", import.meta.url).href);
    const source = c.createMediaStreamSource(stream),
      node = new AudioWorkletNode(c, "fretwork-capture", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1],
        channelCount: 1,
        channelCountMode: "explicit",
      }),
      silent = c.createGain();
    silent.gain.value = 0;
    source.connect(node).connect(silent).connect(c.destination);
    this.mic = { stream, node };
  }

  /** Record `frames` mono samples from now, or until stop(). */
  capture(frames: number, timeoutSeconds: number) {
    const chunks: Float32Array[][] = [];
    return new Promise<Float32Array>((resolve, reject) => {
      const port = this.mic!.node.port;
      const timer = setTimeout(() => reject(Error("Recording did not finish.")), timeoutSeconds * 1000);
      port.onmessage = ({ data }) => {
        if (data.type === "chunk") chunks.push(data.channels);
        if (data.type === "done") {
          clearTimeout(timer);
          try {
            resolve(mergeCapture(chunks, 1, data.frames)[0]);
          } catch (e) {
            reject(e);
          }
        }
      };
      port.postMessage({ type: "start", channels: 1, maxFrames: frames });
    });
  }

  stop() {
    this.mic?.node.port.postMessage({ type: "stop" });
  }

  release() {
    this.mic?.stream.getTracks().forEach((t) => t.stop());
    this.mic?.node.disconnect();
    this.mic = null;
  }

  /**
   * Plays eight clicks and listens. "speakers": the microphone hears the clicks directly
   * (no headphones). "play-along": wearing headphones, the player plucks a muted string on
   * each click. The median delay is what every recording on this device needs taking off,
   * so timing feedback is about the player, not the hardware.
   */
  async measureLatency(method: "speakers" | "play-along"): Promise<{ result: LatencyResult; note: string }> {
    const c = this.context;
    await c.resume();
    await this.ensure();
    const gap = method === "speakers" ? 0.5 : 0.75,
      count = 8,
      lead = method === "speakers" ? 0.3 : 4 * gap,
      // Speaker test: uneven spacing, so a regular noise (a fan, a metronome, a test
      // microphone's own beep) cannot line up with every click and look like a result.
      clicks = method === "speakers" ? jitteredTimes(lead, count, gap) : Array.from({ length: count }, (_, i) => lead + i * gap),
      rate = c.sampleRate,
      seconds = clicks[clicks.length - 1] + 1.1,
      pulse = c.createBuffer(1, Math.ceil(seconds * rate), rate),
      data = pulse.getChannelData(0);
    // Play-along gets a four-click count-in before the eight that are measured.
    const all = method === "speakers" ? clicks : [...Array.from({ length: 4 }, (_, i) => i * gap), ...clicks];
    addClicks([data], rate, all.map((time, i) => ({ time, accent: i % 4 === 0 })), 0, 1, method === "speakers" ? 0.9 : 0.5);
    const source = c.createBufferSource();
    source.buffer = pulse;
    source.connect(c.destination);
    const startAt = c.currentTime + 0.1,
      recordFrom = c.currentTime;
    source.start(startAt);
    const raw = await this.capture(Math.ceil((startAt - recordFrom + seconds) * rate), seconds + 5);
    const result = summariseLatency(detectHits(raw, rate, clicks.map((t) => startAt - recordFrom + t)), method);
    if (result.ok) {
      saveLatency(result);
      return { result, note: `Measured ${result.ms} ms (±${result.spreadMs} ms from ${result.used} clicks). Recordings on this device now use it.` };
    }
    return {
      result,
      note:
        result.used < 5
          ? method === "speakers"
            ? "The microphone didn't hear the clicks clearly. Take headphones off, turn the volume up and try again."
            : "Not enough plucks were heard. Play one short, loud note on every click and try again."
          : `Results were too uneven to trust (±${result.spreadMs} ms). Try again${method === "play-along" ? ", keeping each pluck right on the click" : " in a quieter room"}.`,
    };
  }

  /** Seconds to take off a recording: the measured delay, else what the browser reports. */
  delay(latency: LatencyResult | null) {
    const c = this.context;
    return latency?.ok ? latency.ms / 1000 : (c.outputLatency || 0) + (c.baseLatency || 0);
  }
}
