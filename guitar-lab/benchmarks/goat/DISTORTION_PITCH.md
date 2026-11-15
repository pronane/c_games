# Heavy-distortion pitch recovery: measured, not adopted

The decoder is unchanged. Nothing here was chosen on a held-out item. Held-out
items 35, 60, 103, 118, 152, 156, and 166 were not scored. Tone labels below
come from `song_analysis.tone_estimate` on the audio, not from a user label.
Each GOAT item is one guitar, so guitar 1 versus guitar 2 does not apply.

Train items 4, 5, 46, and 101 were re-measured with the published Riley
decoder (mono, the GOAT scorer). Note F1 is exact pitch, offsets ignored.
The train mean is F1@50 0.577 and F1@100 0.598, the same baseline as before.
DI mean F1@50 is 0.877. Amplifier mean F1@50 is 0.517.

## The low amplifier scores are missing notes

On the amplifiers whose exact-pitch F1 is poor, the estimated note that does
land on a reference onset is usually the right pitch. The reference notes
that fail have no estimate within 50 ms. Counts are from the published
decoder.

| Item | Signal | F1@50 | Exact pitch at a matched onset | Octave error | Reference notes with no onset within 50 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 46 | amp 1 | 0.640 | 24 | 0 | 18 / 45 |
| 46 | amp 2 | 0.448 | 15 | 3 low | 24 / 45 |
| 46 | amp 3 | 0.233 | 7 | 2 low | 35 / 45 |
| 46 | amp 4 | 0.448 | 15 | 4 low | 25 / 45 |
| 46 | amp 5 | 0.174 | 6 | 3 low | 33 / 45 |
| 101 | amp 2 | 0.296 | 29 | 2 low | 117 / 156 |
| 101 | amp 3 | 0.328 | 32 | 5 low | 113 / 156 |
| 101 | amp 4 | 0.270 | 25 | 0 | 124 / 156 |
| 101 | amp 5 | 0.498 | 55 | 4 low | 92 / 156 |

An octave correction cannot create a note the decoder never emitted. The
~0.08 exact-pitch figure is not what these train amplifiers do when an onset
is close: the F1 is low because most reference notes are absent. The octave
mistakes that do exist are the model sitting 12 or 24 semitones **below** the
reference, a handful of notes per file.

Item 5's weak amplifiers (F1@50 0.164 to 0.275) are the other failure: the
onset is found and the pitch of the matched note is exact (7 of 9, or 6 of 9),
but the same pitch is emitted again many times (33 to 58 extra onsets). That
is sustain retriggering, reported with the sustain comparison, not an
octave error.

## Two corrections, both rejected

Both were scored only on the train items. Neither is in the decoder, so the
EGSet12 / Guitar-TECHS gate and the user-recording gate were not given a new
decoder to fail. The published decoder still passes them.

**Higher-octave onset posterior.** Where `tone_estimate` says distorted, move
a note up 12 semitones when the onset posterior there exceeds the chosen
pitch by 0.05 and the frame posterior is above 0.15. DI mean F1@50 stays
0.877. Amplifier mean moves from 0.589 to 0.589 on the note list that already
includes the unadopted sustain comparison (the published list has almost no
octave errors to flip). One file, item 46 amplifier 3, gains 0.005. That is
not a recovery.

**Fundamental from the audio.** On the same note list, where the tone guess
says distorted, replace the pitch with midi+12 or midi+24 or midi−12 when
YIN's median f0 over ±30–50 ms around the onset is within 0.6 semitones of
that candidate and more than 0.6 semitones from the model's pitch.

| | F1@50 before | after |
| --- | ---: | ---: |
| DI | 0.877 | 0.832 |
| amplifiers | 0.589 | 0.574 |

Item 46 DI is the clear loss: the tone guess calls that DI distorted, YIN
disagrees with notes that were already correct, and F1@50 falls from 0.933
to 0.756. Several amplifiers fall as well (item 101 amplifier 4, 0.673 to
0.622; item 46 amplifier 1, 0.640 to 0.533). A few item 4 amplifiers rise by
about 0.01. The net is worse on both DI and amplifiers.

The tone guess is not a safe switch for a pitch change. It labels item 46's
DI as distorted and item 5 amplifier 1, which is full of retriggers, as clean.

## What would have to be true to adopt a later attempt

A pitch rule has to raise exact-pitch F1 on the train DI files and on the
train amplifiers, without adding notes the floors forbid. On this set the
open problem is still notes that are never emitted under high gain, not notes
that are emitted a semitone or an octave off. More high-gain train items
would show whether that absence is the usual case. These four items are not
enough to invent a pitch map, and the two maps above are not safe.
