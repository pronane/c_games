// Exercises real WebAudio/worklet routing with a simulated USB input, not hardware.
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
if (!process.env.BROWSER_EXECUTABLE_PATH)
  throw Error("Set BROWSER_EXECUTABLE_PATH to a local Chromium binary.");
const browser = await chromium.launch({
  executablePath: process.env.BROWSER_EXECUTABLE_PATH,
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--autoplay-policy=no-user-gesture-required",
  ],
});
try {
  const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    }),
    errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.addInitScript(() => {
    const originalCopy = AudioBuffer.prototype.copyToChannel;
    AudioBuffer.prototype.copyToChannel = function (
      values,
      channel,
      offset = 0,
    ) {
      if (values.length > 8192) {
        window.__capture = window.__capture ?? {
          samples: [],
          rate: this.sampleRate,
          channels: this.numberOfChannels,
        };
        window.__capture.samples[channel] = Array.from(values);
      }
      return originalCopy.call(this, values, channel, offset);
    };
    const midi = {
      id: "usb-midi",
      name: "Test USB MIDI keyboard",
      manufacturer: "Fretwork test",
      state: "connected",
      onmidimessage: null,
      open: async () => {},
      close: async () => {},
    };
    window.__midi = midi;
    Object.defineProperty(navigator, "requestMIDIAccess", {
      value: async () => ({
        inputs: new Map([[midi.id, midi]]),
        onstatechange: null,
      }),
    });
    Object.defineProperty(navigator.mediaDevices, "enumerateDevices", {
      value: async () => [
        {
          deviceId: "usb-audio",
          kind: "audioinput",
          label: "Test USB audio interface",
          groupId: "usb",
          toJSON() {
            return {};
          },
        },
      ],
    });
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: async (constraints) => {
        window.__constraints = constraints;
        if (window.__deny) throw new DOMException("Denied", "NotAllowedError");
        const ctx = new AudioContext(),
          left = ctx.createOscillator(),
          right = ctx.createOscillator(),
          gain1 = ctx.createGain(),
          gain2 = ctx.createGain(),
          merger = ctx.createChannelMerger(2),
          output = ctx.createMediaStreamDestination();
        left.frequency.value = 220;
        right.frequency.value = 440;
        gain1.gain.value = 0.1;
        gain2.gain.value = 0.2;
        left.connect(gain1).connect(merger, 0, 0);
        right.connect(gain2).connect(merger, 0, 1);
        merger.connect(output);
        left.start();
        right.start();
        await ctx.resume();
        const track = output.stream.getAudioTracks()[0];
        Object.defineProperty(track, "label", {
          value: "Test USB audio interface",
        });
        track.getSettings = () => ({ deviceId: "usb-audio", channelCount: 2 });
        window.__track = track;
        window.__contexts = window.__contexts ?? [];
        window.__contexts.push(ctx);
        return output.stream;
      },
    });
  });
  await page.goto(process.env.STUDIO_URL ?? "http://127.0.0.1:5173");
  await page
    .getByLabel("Audio input", { exact: true })
    .selectOption("usb-audio");
  await page.getByLabel("Interface channel").selectOption("input2");
  await page
    .getByRole("button", { name: "Enable / connect input", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Disconnect input", exact: true })
    .waitFor();
  assert.equal(
    await page.evaluate(() => window.__constraints.audio.deviceId.exact),
    "usb-audio",
  );
  await page.waitForFunction(
    () =>
      Number(
        document.querySelector('[role="meter"]').getAttribute("aria-valuenow"),
      ) > 0,
  );
  await page.getByRole("checkbox", { name: /Optional: tune/ }).check();
  await page.waitForFunction(() =>
    /44[01]\.\d Hz/.test(
      document.querySelector(".tuner-reading")?.textContent ?? "",
    ),
  );
  await page
    .getByRole("button", { name: "Record selected input", exact: true })
    .click();
  await page.waitForTimeout(1100);
  await page.getByRole("button", { name: /Stop ·/ }).click();
  await page
    .getByText(/Take ready: Guitar · Test USB audio interface · input 2/)
    .waitFor();
  assert.equal(
    await page
      .getByText(/Take ready:/)
      .textContent()
      .then((t) => t.endsWith("mono")),
    true,
  );
  // Verify actual routed PCM, not only the selected UI label.
  const tone = await page.evaluate(() => {
    const capture = window.__capture,
      samples = capture.samples[0].slice(-Math.round(capture.rate * 0.5));
    let crossings = 0;
    for (let i = 1; i < samples.length; i++)
      if (samples[i - 1] < 0 && samples[i] >= 0) crossings++;
    return {
      frequency: (crossings * capture.rate) / samples.length,
      channels: capture.channels,
    };
  });
  assert.equal(tone.channels, 1);
  assert.ok(Math.abs(tone.frequency - 440) < 5, JSON.stringify(tone));
  await page
    .getByRole("button", { name: "Disconnect input", exact: true })
    .click();
  await page.getByLabel("Interface channel").selectOption("stereo");
  await page
    .getByRole("button", { name: "Enable / connect input", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Disconnect input", exact: true })
    .waitFor();
  await page.evaluate(() => {
    window.__capture = null;
  });
  await page
    .getByRole("button", { name: "Record selected input", exact: true })
    .click();
  await page.waitForTimeout(1100);
  await page.getByRole("button", { name: /Stop ·/ }).click();
  await page
    .getByText(/Take ready: Guitar · Test USB audio interface · stereo/)
    .waitFor();
  const stereo = await page.evaluate(() => {
    const capture = window.__capture;
    return {
      channels: capture.channels,
      frequencies: capture.samples.map((channel) => {
        const samples = channel.slice(-Math.round(capture.rate * 0.5));
        let crossings = 0;
        for (let i = 1; i < samples.length; i++)
          if (samples[i - 1] < 0 && samples[i] >= 0) crossings++;
        return (crossings * capture.rate) / samples.length;
      }),
    };
  });
  assert.equal(stereo.channels, 2);
  assert.ok(Math.abs(stereo.frequencies[0] - 220) < 5);
  assert.ok(Math.abs(stereo.frequencies[1] - 440) < 5);
  await page.evaluate(() => window.__track.dispatchEvent(new Event("ended")));
  await page
    .getByRole("alert")
    .filter({ hasText: "input disconnected" })
    .waitFor();
  await page.evaluate(() => {
    window.__deny = true;
  });
  await page
    .getByRole("button", { name: "Enable / connect input", exact: true })
    .click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Audio access was denied" })
    .waitFor();
  await page
    .getByText("USB MIDI keyboard / MIDI adapter", { exact: true })
    .click();
  await page
    .getByRole("button", { name: "Enable MIDI input", exact: true })
    .click();
  await page.getByLabel("MIDI input", { exact: true }).selectOption("usb-midi");
  await page.getByRole("button", { name: /Record MIDI ·/ }).click();
  await page.evaluate(() =>
    window.__midi.onmidimessage({
      data: new Uint8Array([0x90, 60, 100]),
      timeStamp: performance.now(),
    }),
  );
  await page.waitForTimeout(200);
  await page.evaluate(() =>
    window.__midi.onmidimessage({
      data: new Uint8Array([0x80, 60, 0]),
      timeStamp: performance.now(),
    }),
  );
  await page
    .getByRole("button", { name: "Stop MIDI take", exact: true })
    .click();
  await page.getByText("1 note events captured.", { exact: false }).waitFor();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Download MIDI", exact: true }).click(),
  ]);
  assert.equal(download.suggestedFilename(), "fretwork-keyboard-take.mid");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    ),
    false,
  );
  assert.deepEqual(errors, []);
  await page.evaluate(() =>
    Promise.all(window.__contexts.map((c) => c.close())),
  );
  console.log(
    "USB-input simulation: exact-device selection, actual PCM worklet recording, level meter, disconnect, permission failure, MIDI recording/export and mobile overflow checks passed. No physical adapters were tested.",
  );
} finally {
  await browser.close();
}
