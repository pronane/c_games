# Clean-from-amp note filter: training / eval harness

Local-only research harness for `server/clean_model.py` (paths point at the local dataset folder; edit them).

1. `extract.py` – runs Basic Pitch at candidate thresholds (0.3/0.2) with posteriors on Guitar-TECHS P1/P3
   (direct + mic'd amp, real MIDI labels, CC BY 4.0) and Hollow Ground "Ill Fate" amp tracks (labels = engine on
   the same take's DI). Writes per-candidate features + labels (`cands.pkl`, not shipped).
2. `train.py` – 4-fold CV held out by performance (song / technique clip / Hollow Ground guitar), threshold chosen
   on training folds, scikit-learn GradientBoosting (150 trees, depth 3) exported to JSON
   (`server/fx/data/clean_model.json`, ~70 KB, no audio). `VAR=nofx|distfx|all` selects effect-detector features.

`common.py` is the shared loader/scorer (mir_eval note F1). `../fingerprint_eval.py` is the fingerprint matrix.
Not used: IDMT note pairs (not needed once real-MIDI pairs existed; NC-ND audio stays local), EGDB-BIAS (no
matched dry labels available), fine-tuning Basic Pitch (not attempted on CPU).
