# USB audio and MIDI input support

## USB audio interfaces — guitar, bass and keyboard audio

The studio now records from browser/OS audio inputs, not just an unspecified microphone. USB interfaces are accessed through **getUserMedia/Web Audio**, not WebUSB; the operating system must recognise the adapter as an audio device.

1. Connect a class-compliant USB audio interface or an interface with working OS drivers.
2. Open the studio over HTTPS (localhost is allowed for development).
3. Under **Your take → Microphone / USB audio interface**, click **Enable / connect input** and allow browser microphone/audio-input permission. Device names may be hidden until permission is granted.
4. Choose the interface in **Audio input**. Selecting a different device or channel disconnects the old one; click **Enable / connect input** again.
5. Choose **Input 1**, **Input 2**, or **Inputs 1 + 2 · stereo**. These are browser-exposed channel positions, not verified physical jack names. Some interfaces expose only their first one/two channels or a mixed stereo pair. Arbitrary ASIO/DAW channel routing is not supported.
6. Check the live level meter, adjust the interface gain, then **Record selected input**. The take stops at the selected passage length, up to 60 seconds. You can stop early. PCM is captured by an AudioWorklet, avoiding lossy/platform-specific MediaRecorder codecs.
7. Recorded audio becomes the current take and can enter the existing comparison workflow. It remains local until explicit specialist-engine upload consent.

### Cabling / monitoring

- Guitar and bass: use an instrument/Hi-Z input or a suitable DI/preamp. A passive USB-to-jack cable is not necessarily a working audio interface.
- Piano/keyboard: its USB port may carry audio, MIDI, or both. If it is MIDI-only, connect its line/headphone audio output to appropriate interface line inputs to record its actual sound. Stereo keyboard audio can use two exposed inputs.
- Do not connect an amplifier's speaker output to an ordinary interface input.
- No audible software monitoring is enabled. Use headphones and the interface's hardware direct-monitor feature to avoid feedback and minimise monitoring latency. Playback uses the OS/browser's normal audio output; choose your interface as the system output if required.
- Browser echo cancellation, automatic gain and noise suppression are requested off. Browsers/hardware can still apply processing; no claim of calibrated/bit-perfect hardware capture is made. The displayed sample rate is the AudioContext rate, not necessarily the converter's native rate.
- A clipping warning is advisory, based on selected-channel sample peaks. It cannot identify every kind of analogue clipping. No interface latency correction/calibration is applied to timing comparisons.

### Compatibility and failure handling

- Works only where the browser and OS expose the interface through audio capture. No custom driver installation, WebUSB protocol or vendor-specific control software is included.
- Desktop Chrome/Edge/Firefox/Safari and mobile browsers vary in device enumeration and channel control. A class-compliant interface may work through USB-C/OTG/Lightning with the correct adapter and adequate power, but **no physical device/mobile compatibility matrix has been validated here**.
- Refresh devices after connecting new hardware. Explicitly selected devices use an exact device ID; failures do not silently fall back to the built-in microphone. The **System default** choice follows OS/browser routing and cannot guarantee a particular physical device.
- Disconnection, processor failure or browser audio suspension during recording discards the unfinished take and releases input resources. Existing completed takes remain available.
- Audio capture is bounded by samples, not a UI timer. There is no long-running/background recording guarantee; keep the app active.
- Lack of permission, HTTPS, AudioWorklet support or compatible drivers is reported; uploading an audio file remains the fallback.

## USB MIDI keyboards / MIDI adapters

Expand **USB MIDI keyboard / MIDI adapter** and enable MIDI permission. Select an input and record a local MIDI take.

- Uses Web MIDI with **SysEx disabled**. Does not use or transmit raw device commands.
- Records note-on/off, velocity and channel; velocity-zero note-on is treated as note-off. Sustain pedal is reflected in note duration. Notes still held when stopping/disconnecting are finalised.
- Download as a standard format-0 `.mid` file, with explicit 120 BPM and 480 PPQ timing.
- Sustain is baked into durations. Raw pedal curves, pitch bend, aftertouch, program changes and instrument sounds are not exported. No synthesiser/software monitoring is provided.
- **MIDI is not audio.** It does not create a guitar take, run audio comparison, or enable piano-specific scoring. This step supports capture/export only; direct MIDI-to-reference comparison is future work.
- Web MIDI availability and permissions differ from USB audio. Desktop Chrome/Edge are useful targets; Safari/iOS Web MIDI is not supported through this path. Unsupported browsers show an explanation rather than claiming to connect.

## Current analysis scope

Choose the instrument in the **Before you play** panel. Shared profiles now control pitch ranges, the selected six-source separation stem, transcription parameters and notation/tuning/capo-aware tab. Bass/piano analysis is experimental and not validated on real instruments; MIDI comparison is still not implemented. See INSTRUMENT_PROFILES.md. Existing full-band checkpoint-provisioning limitations are unchanged.

## Validation

```sh
npm test
npm run build
BROWSER_EXECUTABLE_PATH=/path/to/chromium npm run test:inputs
```

Unit tests cover exact device constraints, channel selection, PCM assembly, sample-limited/manual-stop AudioWorklet behaviour, MIDI sustain/note/channel semantics and MIDI file structure. The browser input test uses a **simulated USB source** with separate 220/440 Hz channels and a simulated MIDI keyboard. It checks actual worklet capture/channel selection, meter activity, permission/disconnect handling, MIDI recording/download and phone-width page overflow. These are not physical USB or real mobile-device tests.
