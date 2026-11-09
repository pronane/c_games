"""FFmpeg helpers for compressed audio formats and audio-only extraction."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def ffmpeg_executable() -> str:
    """Return the bundled imageio-ffmpeg binary, or a system ffmpeg fallback."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        if found:
            return found
    raise RuntimeError("FFmpeg support is not installed. Install the app's full dependencies, including imageio-ffmpeg.")


def decode_audio_to_temp_wav(source_path: str) -> str:
    """Extract the first audio stream (no video) into temporary float32 WAV."""
    ffmpeg = ffmpeg_executable()
    fd, target = tempfile.mkstemp(prefix="audiocapture-decoded-", suffix=".wav")
    os.close(fd)
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", os.fspath(source_path), "-map", "0:a:0", "-vn", "-c:a", "pcm_f32le",
               "-f", "wav", target]
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                check=False, text=True)
        if result.returncode != 0 or not os.path.exists(target) or os.path.getsize(target) <= 44:
            details = (result.stderr or "No audio stream was found.").strip()
            raise RuntimeError(f"Could not extract audio from {Path(source_path).name}: {details[-1200:]}")
        return target
    except Exception:
        try:
            os.remove(target)
        except OSError:
            pass
        raise


def pcm_encoder_command(path: str, samplerate: int, channels: int, encoder: str,
                        bitrate_kbps: int) -> list[str]:
    """Construct a raw-float-input encoder command for AAC or MP3."""
    ffmpeg = ffmpeg_executable()
    if encoder == "aac":
        codec, muxer = "aac", "ipod"
    elif encoder == "mp3":
        codec, muxer = "libmp3lame", "mp3"
    else:
        raise ValueError(f"Unsupported compressed audio encoder: {encoder}")
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "f32le", "-ar", str(int(samplerate)), "-ac", str(int(channels)),
            "-i", "pipe:0", "-vn", "-c:a", codec, "-b:a", f"{int(bitrate_kbps)}k",
            "-f", muxer, os.fspath(path)]


def encode_float32_pcm(path: str, samplerate: int, channels: int, encoder: str,
                       bitrate_kbps: int, blocks) -> str:
    """Pipe interleaved float32 blocks into AAC/MP3 FFmpeg encoding."""
    command = pcm_encoder_command(path, samplerate, channels, encoder, bitrate_kbps)
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        for block in blocks:
            if block is not None and len(block):
                proc.stdin.write(block)
        proc.stdin.close()
        stderr = proc.stderr.read() if proc.stderr else b""
        if proc.stderr:
            proc.stderr.close()
        code = proc.wait()
    except Exception:
        proc.kill()
        proc.wait()
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    if code != 0 or not os.path.exists(path) or os.path.getsize(path) == 0:
        try:
            os.remove(path)
        except OSError:
            pass
        detail = stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"FFmpeg audio encode failed: {detail or 'encoder returned an error'}")
    return path
