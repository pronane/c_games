import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import {
  captureError,
  inputConstraints,
  mergeCapture,
  selectedChannels,
} from "./audioInputs";
test("explicit USB selection never silently falls back to another device", () => {
  const audio = inputConstraints("usb-interface")
    .audio as MediaTrackConstraints;
  assert.deepEqual(audio.deviceId, { exact: "usb-interface" });
  assert.equal(audio.echoCancellation, false);
  assert.equal(audio.noiseSuppression, false);
  assert.equal(audio.autoGainControl, false);
  assert.equal("deviceId" in (inputConstraints("").audio as object), false);
  assert.deepEqual(selectedChannels("input2"), [1]);
  assert.deepEqual(selectedChannels("stereo"), [0, 1]);
});
test("PCM capture retains separate channels and rejects missing frames", () => {
  const result = mergeCapture(
    [
      [new Float32Array([0.25]), new Float32Array([-0.5])],
      [new Float32Array([0.75]), new Float32Array([0.5])],
    ],
    2,
    2,
  );
  assert.deepEqual([...result[0]], [0.25, 0.75]);
  assert.deepEqual([...result[1]], [-0.5, 0.5]);
  assert.throws(() => mergeCapture([], 1, 5), /interrupted/);
  assert.throws(() => mergeCapture([], 1, 0), /No audio/);
});
test("permission and disconnect errors are actionable", () => {
  assert.match(captureError({ name: "NotAllowedError" }), /HTTPS/);
  assert.match(captureError({ name: "OverconstrainedError" }), /not switched/);
  assert.match(captureError({ name: "NotReadableError" }), /another app/);
});
function processor() {
  let Processor: any;
  const messages: any[] = [];
  class Stub {
    port: {
      onmessage: ((event: any) => void) | null;
      postMessage: (data: any) => void;
    } = { onmessage: null, postMessage: (data) => messages.push(data) };
  }
  vm.runInNewContext(
    readFileSync(new URL("./capture.worklet.js", import.meta.url), "utf8"),
    {
      AudioWorkletProcessor: Stub,
      registerProcessor: (_: string, value: any) => (Processor = value),
      Float32Array,
    },
  );
  return { node: new Processor(), messages };
}
test("worklet enforces sample-based stop and preserves stereo PCM", () => {
  const { node, messages } = processor();
  node.port.onmessage({ data: { type: "start", channels: 2, maxFrames: 200 } });
  const left = new Float32Array(128).fill(0.25),
    right = new Float32Array(128).fill(-0.5);
  node.process([[left, right]]);
  node.process([[left, right]]);
  node.process([[left, right]]);
  const done = messages.filter((x) => x.type === "done");
  assert.equal(done.length, 1);
  assert.equal(done[0].frames, 200);
  const chunk = messages.find((x) => x.type === "chunk");
  assert.equal(chunk.channels[0].length, 200);
  assert.equal(chunk.channels[1][199], -0.5);
});
test("worklet flushes partial buffers on manual stop and handles another take", () => {
  const { node, messages } = processor();
  node.port.onmessage({
    data: { type: "start", channels: 1, maxFrames: 5000 },
  });
  for (let i = 0; i < 33; i++)
    node.process([[new Float32Array(128).fill(0.1)]]);
  node.port.onmessage({ data: { type: "stop" } });
  assert.equal(messages.find((x) => x.type === "done").frames, 4224);
  assert.deepEqual(
    messages.filter((x) => x.type === "chunk").map((x) => x.channels[0].length),
    [4096, 128],
  );
  node.port.onmessage({ data: { type: "start", channels: 1, maxFrames: 128 } });
  node.process([[new Float32Array(128)]]);
  assert.equal(messages.filter((x) => x.type === "done").at(-1).frames, 128);
});
