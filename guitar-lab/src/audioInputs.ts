export type InputMode = "input1" | "input2" | "stereo";
export function inputConstraints(deviceId: string): MediaStreamConstraints {
  return {
    audio: {
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
      channelCount: { ideal: 2 },
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    },
    video: false,
  };
}
export function selectedChannels(mode: InputMode): number[] {
  return mode === "stereo" ? [0, 1] : [mode === "input2" ? 1 : 0];
}
export function captureError(error: unknown): string {
  const name =
    error && typeof error === "object" && "name" in error
      ? String(error.name)
      : "";
  if (name === "NotAllowedError" || name === "SecurityError")
    return "Audio access was denied. Allow microphone/audio-input access in your browser over HTTPS. USB interfaces use the same permission.";
  if (name === "OverconstrainedError" || name === "NotFoundError")
    return "The selected input is unavailable. Reconnect the adapter and refresh inputs. We have not switched to a different microphone.";
  if (name === "NotReadableError")
    return "The input could not be opened. Check the cable, OS audio permissions, and whether another app is using the interface.";
  return error instanceof Error
    ? error.message
    : "Unable to open this audio input.";
}
export function mergeCapture(
  chunks: Float32Array[][],
  channelCount: number,
  frames: number,
): Float32Array[] {
  if (!Number.isInteger(frames) || frames < 1)
    throw Error("No audio was captured.");
  const output = Array.from(
    { length: channelCount },
    () => new Float32Array(frames),
  );
  let offset = 0;
  for (const chunk of chunks) {
    if (
      chunk.length !== channelCount ||
      chunk.some((c) => c.length !== chunk[0].length)
    )
      throw Error("The input channel layout changed during recording.");
    const count = Math.min(chunk[0].length, frames - offset);
    if (count <= 0) break;
    chunk.forEach((samples, c) =>
      output[c].set(samples.subarray(0, count), offset),
    );
    offset += count;
  }
  if (offset !== frames)
    throw Error("The audio recording was interrupted; please try again.");
  return output;
}
