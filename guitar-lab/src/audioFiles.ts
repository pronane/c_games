import { encodeWav } from "./engineApi";

/** What the file pickers accept: audio files, plus the sound of video files (WebM, MP4, MKV, MOV). */
export const MEDIA_ACCEPT =
  "audio/*,video/webm,video/mp4,video/quicktime,video/x-matroska,.mp3,.wav,.flac,.ogg,.oga,.m4a,.aac,.opus,.webm,.weba,.mkv,.mp4,.mov";

/** Formats the engine can only read with ffmpeg; the browser decodes these itself instead. */
export function needsBrowserDecode(name: string) {
  return /\.(webm|weba|mkv|mp4|m4a|m4v|mov|opus|aac)$/i.test(name);
}

/**
 * Decode a media file's sound in the browser and return it as a WAV file (first two channels).
 * Video is ignored. Throws if the browser can't decode it.
 */
export async function toWav(file: File, context: BaseAudioContext): Promise<File> {
  const audio = await context.decodeAudioData(await file.arrayBuffer());
  const channels = Array.from({ length: Math.min(2, audio.numberOfChannels) }, (_, i) => audio.getChannelData(i));
  const wav = encodeWav(channels, audio.sampleRate);
  return new File([wav], file.name.replace(/\.[^.]+$/, "") + ".wav", { type: "audio/wav" });
}
