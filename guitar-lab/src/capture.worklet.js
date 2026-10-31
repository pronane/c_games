// PCM capture is independent of MediaRecorder's platform-dependent codecs.
// Output is silent; hardware/direct monitoring is intentionally left to the interface.
class FretworkCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.active = false;
    this.buffers = [];
    this.count = 0;
    this.total = 0;
    this.maxFrames = 0;
    this.port.onmessage = ({ data }) => {
      if (data.type === "start") {
        this.buffers = Array.from(
          { length: data.channels },
          () => new Float32Array(4096),
        );
        this.count = 0;
        this.total = 0;
        this.maxFrames = data.maxFrames;
        this.active = true;
      } else if (data.type === "stop" && this.active) this.finish();
    };
  }
  flush() {
    if (!this.count) return;
    const channels = this.buffers.map((b) => b.slice(0, this.count));
    this.port.postMessage(
      { type: "chunk", channels },
      channels.map((c) => c.buffer),
    );
    this.count = 0;
  }
  finish() {
    this.active = false;
    this.flush();
    this.port.postMessage({ type: "done", frames: this.total });
  }
  process(inputs) {
    if (!this.active) return true;
    const channels = inputs[0];
    if (!channels?.length) return true;
    const frames = Math.min(channels[0].length, this.maxFrames - this.total);
    for (let i = 0; i < frames; i++) {
      this.buffers.forEach((b, c) => {
        b[this.count] = channels[c]?.[i] ?? 0;
      });
      this.count++;
      this.total++;
      if (this.count === 4096) this.flush();
    }
    if (this.total >= this.maxFrames) this.finish();
    return true;
  }
}
registerProcessor("fretwork-capture", FretworkCapture);
