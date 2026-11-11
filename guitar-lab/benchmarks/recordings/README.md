# User recordings

These files are the player's own audio. They are not in git, and there is
**no ground-truth tab**. The numbers in `reference/user_recordings.json` lock
what the song-path decoder currently writes down. They are not an accuracy
score. A later change that moves them is a behaviour change. It is not, by
itself, an improvement.

From `guitar-lab/`:

```sh
python -m benchmarks.recordings --root /path/to/the/aac/folder
```

The folder needs these four files, with these sha256 sums:

| File | sha256 |
| --- | --- |
| `current_upload.aac` | `cb121e0fd26f48cec619e651fb77a9587bde54b54891e959fd879b5465b14564` |
| `take_a_4m51.aac` | `f0e075a1c53be2fabd5fb0e3305c34420e995e85731a7d7c798f75e7e0a97322` |
| `take_b_1m44.aac` | `8aa776e0739f1101466e00d939900f0e3ac66f41349be9e2f92621bd91c3267e` |
| `take_c_synth_4m58.aac` | `cb121e0fd26f48cec619e651fb77a9587bde54b54891e959fd879b5465b14564` |

`current_upload.aac` and `take_c_synth_4m58.aac` are the same bytes. The
manifest shipped with the earlier takes named a different hash (`9c8e4494…`)
for a newer upload that was not in that package. That other file is not what
this lock measures.

Take A, take B, and take C are three earlier recordings. Earlier notes
describe A and C as separate performances of one song, and B as a different
section that does not line up with them. They are **not** a confirmed dry/wet
pair, and the lock does not score one as the reference chart for the other.
Agreement between them is "do the two transcriptions still tell the same
story after an audio-only time map". Same story is not the true tab.

The decoder is the song path: `songs.decode` (ffmpeg for AAC, 44.1 kHz
stereo), then Riley with the same per-channel merge the song pipeline uses
when both channels are active. Effects and guitar 1 vs guitar 2 are not
labels on these files.

The pytest skips when the files are absent. A different checksum fails. The
slack matches the public clips: 0.02 on rates, pitch-class shares, timing,
playback-onset lag, and pairwise agreement. Note count uses 2% or one note,
whichever is larger. Both directions fail. There is no ground truth that
would make "more notes" a pass.

`reference/user_recordings.json` holds only those aggregate numbers and the
checksums. It does not contain the audio or the note list.

## What the current decoder emitted

Riley, song path, per-channel merge. Measured once and locked.

| File | Notes | Notes/s | Median duration | Short notes (<80 ms) | Playback attack lag |
| --- | ---: | ---: | ---: | ---: | ---: |
| current upload (same bytes as take C) | 238 | 0.780 | 0.429 s | 0 | 0.4 ms |
| take A (4 m 51 s) | 627 | 2.087 | 0.288 s | 2.2% | 0.7 ms |
| take B (1 m 44 s) | 565 | 5.190 | 0.211 s | 11.5% | 0.6 ms |
| take C | 238 | 0.780 | 0.429 s | 0 | 0.4 ms |

Take A and take C share pitch-class content (cosine 0.967) and do not share a
note sequence (F1 0.345 at 50 ms after the audio-only time map). Take A has
about 2.6 times as many notes as take C over a similar length. That can be a
denser performance, a wetter recording, or the decoder retriggering. This lock
does not decide which. Take B against take A is note F1 0.032. The identical
upload and take C agree at note F1 1.0.
