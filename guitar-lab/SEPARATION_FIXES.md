# Separation fixes (local branch `local/separation-fixes`)

Measured on CPU against **true-stem Basic Pitch ceilings** (Head Down excerpt 75 s; 14 Ghosts II excerpt130 = 60 s from 127.5 s). Demucs `htdemucs_6s` is MIT. No weights were pushed.

## Kept (shipped)

| Change | HD F1@50 / @100 | HD SI-SDR | Ghosts F1@50 | Cost |
| --- | --- | --- | --- | --- |
| Baseline `shifts=1 ov=0.25` mono TX | 0.45–0.48 / ~0.53 | ≈ −0.3…−0.5 | ≈ 0.04–0.05 | ~15 s/min audio |
| **`shifts=2 ov=0.50` + L/R TX merge** | **0.54 / 0.60** | **+0.02** | **~0.06** | ~80 s/min sep + ~2× TX |
| L/R TX merge alone (shifts1 stem) | 0.50–0.53 / ~0.57–0.58 | same stem | ~0.04–0.05 | +1 TX pass |

Env (defaults = kept quality settings):

- `FRETWORK_DEMUCS_SHIFTS` (default `2`)
- `FRETWORK_DEMUCS_OVERLAP` (default `0.5`)
- `FRETWORK_LR_TRANSCRIBE` (default `1`; set `0` to disable channel merge)

## Tried and not kept

| Idea | Licence | Result |
| --- | --- | --- |
| (b) guitar+other (+piano) as TX input | MIT demucs stems | Flat or down vs guitar alone |
| (c) mid-only TX | — | No win vs mono; L/R merge better |
| (c) L/R demucs then average | MIT | Not better than stereo demucs + L/R TX |
| (d) HPSS + HP ~80 Hz before TX | librosa | Ghosts F1@50 ~0.07 (small↑) but **HD regresses** (~0.39); not default |
| (e) spectral de-reverb | numpy/librosa | HD mono ↑ (~0.50) but with L/R merge it does not beat raw L/R |
| (f) mix-range multi-pitch confirm stem | — | Large F1 drop |
| (g) community `htdemucs-6s-guitar-ft` | **Apache-2.0** (`adityalakhani/htdemucs-6s-guitar-ft`) | HD SI-SDR ↑ (~0.45–0.53) but **F1@50 down** (~0.44–0.47); Ghosts SI-SDR ↑ (~−11 vs −14) but F1 worse. Not adopted |

True-stem ceilings remain far above separated stems (HD F1@50 ~0.74 on true stem; Ghosts still SI-SDR ~−13…−14 after shifts2).

## No-regression paths

- **GuitarSet** benchmark never calls Demucs; only Basic Pitch thresholds — unchanged unless a fixture is stereo with both channels live (merge collapses near-duplicates).
- **Carcassi / isolated reference** jobs skip Demucs; L/R merge is a no-op on mono / single-active-channel files.

## Speed (CPU, this box)

- Demucs `shifts=1 ov=0.25`: ~15 s per minute of audio (HD 75 s → ~19 s)
- Demucs `shifts=2 ov=0.50`: ~80 s per minute of audio (HD 75 s → ~100 s)
- Basic Pitch TX: ~0.5–1 s per minute per channel; L/R ≈ 2×
