# Teaching the note detector to read guitar inside a band mix

**Goal:** Riley reads solo guitar well (about 94% of notes on clean guitar) but loses most of
the guitar once it is inside a band mix and has been through separation. This plan trains it
on exactly that material, on a rented graphics card, and accepts the result only if it wins
on real recordings that were fixed beforehand.

Nothing here has been run on a graphics card yet. The scripts were run end to end on a
2-processor machine with the 20-song BabySlakh sample; times and costs below are estimates
to be confirmed by the pilot in step 4.

## The rule that makes the result real

1. The test is built and scored **before** any training (step 1).
2. Test recordings are never used for training or for choosing settings.
3. The decision is made by `benchmarks/fullband/gate.py` and the locked baselines in
   `benchmarks/regression`, not by listening or by training loss.
4. A "no" is a valid outcome and gets written up like a "yes".

## Step 1: freeze the test (no graphics card needed)

On the machine that has the recordings:

```bash
cd guitar-lab

# a) Songs whose separate guitar tracks you have (e.g. the NIN multitrack):
python -m benchmarks.fullband.items multitrack <mix audio> nin_1000000 <guitar track 1> <guitar track 2>

# b) Play-along items, one per song (see "Recording a play-along take" below):
python -m benchmarks.fullband.items playalong <your take> <the song> <name>

# c) Fix the bar. The command refuses to overwrite data/baseline.json.
python -m benchmarks.fullband.gate baseline
```

Aim for 5 to 10 songs across the styles you care about (clean, crunch, heavy). Items live in
`benchmarks/fullband/data/`, which is not committed.

### Recording a play-along take

- Play the song's guitar part along with the song **on headphones**, so the recording has
  only your guitar in it. A phone next to an unplugged electric, an acoustic, or a clean amp
  at low volume all work; clean or light crunch is best, because the reference is the engine's
  reading of your take on its own.
- Play at the song's tempo from wherever you like; the script finds where your take starts.
  One continuous take per item, 1 to 3 minutes is plenty.
- Check the printed `line_up_similarity`. Under about 0.5 the take probably was not lined up;
  re-record or trim the take so it starts on a clear phrase.
- What the item measures: how much of what the engine hears in your guitar alone it still
  hears once the band is around it. It does not prove the notes themselves are right.

## Step 2: rent the machine

- Any provider with an NVIDIA card of 24 GB works. RunPod on-demand prices on 14 Nov 2026:
  RTX 4090 $0.89/hour, RTX A5000 $0.27/hour; volume storage $0.10 per GB per month.
- Disk: 350 GB (Slakh is 104 GB compressed and about as much again unpacked, plus segments).
- Image: any recent PyTorch + CUDA image with Python 3.11 or newer.

```bash
git clone https://github.com/pronane/c_games && cd c_games/guitar-lab
pip install -r server/requirements.txt -r server/requirements-models.txt -r server/requirements-transcription.txt \
    -r server/requirements-transcription-extras.txt pretty_midi pyyaml
python -m server.model_store                # the separation weights, checksum-verified (server/README.md)
```

## Step 3: get the training material

```bash
# Slakh2100-redux, CC BY 4.0 (credit: Manilow, Wichern, Seetharaman, Le Roux, WASPAA 2019)
wget -O slakh.tar.gz "https://zenodo.org/api/records/4599666/files/slakh2100_flac_redux.tar.gz/content"
tar xzf slakh.tar.gz && rm slakh.tar.gz
```

Only `train/` is used for training and `validation/` for choosing a checkpoint. `test/` is
left untouched for a final Slakh number.

## Step 4: pilot (about 2 hours, a few dollars)

```bash
# 150 songs -> segments of the separated guitar (and the raw mix) with exact notes
python -m training.slakh_data build slakh2100_flac_redux/train data/pilot --tracks 150 --also-mix
python -m training.finetune_riley --data data/pilot --out runs/pilot --steps 3000 --every 500 --batch 16 --workers 4
python -m training.slakh_data eval slakh2100_flac_redux/validation --tracks 30      # released model
FRETWORK_RILEY_CHECKPOINT=runs/pilot/step_3000.pth python -m training.slakh_data eval slakh2100_flac_redux/validation --tracks 30
```

Write down seconds per song for `build` and seconds per step for training: they decide the
cost of step 5. **Stop here if the pilot checkpoint is not clearly better than the released
model on the "separated" column** of the validation songs. More data rarely rescues a method
that shows nothing at 150 songs.

## Step 5: full run

```bash
# First, solo guitar so the model does not forget it (GuitarSet players 00-04 and amp renders).
# This script numbers its segments from zero, so it must run before the Slakh build:
python -m training.build_data --guitarset-audio <pickup audio dir> --guitarset-ann <annotation dir> --out data/full
# Then the band material, which continues the numbering:
python -m training.slakh_data build slakh2100_flac_redux/train data/full --also-mix
python -m training.finetune_riley --data data/full --out runs/full --steps 40000 --every 2000 --batch 16 --workers 4
```

Estimates, to be replaced by the pilot's measurements: separation of 1,500 songs 8 to 15
hours, training 3 to 6 hours, so 15 to 25 hours of an RTX 4090: roughly $15 to $25 of
compute plus a few dollars of storage. `--all-layers` trains the whole network instead of
the recurrent and output layers; try it only after the default run, as a second experiment.

Pick the checkpoint with the best "separated" score on the Slakh **validation** songs. Do not
look at the frozen test to choose it.

## Step 6: the decision

Copy the chosen checkpoint to the machine with the test recordings, then:

```bash
python -m benchmarks.fullband.gate check runs/full/step_NNNNN.pth      # must pass
FRETWORK_RILEY_CHECKPOINT=runs/full/step_NNNNN.pth python -m pytest server/tests/test_regression_benchmark.py
FRETWORK_RILEY_CHECKPOINT=runs/full/step_NNNNN.pth python -m benchmarks.take_compare_eval ...
```

- **Adopt** only if the gate passes (mean note F1 up by at least 0.05, no item down by more
  than 0.02) **and** the locked regression baselines hold (no clip down by more than 0.02).
- If it helps band mixes but costs solo guitar, ship it as a separate "Riley (band mix)" entry
  in the detector menu, used for separated stems only.
- Otherwise the released model stays, and the result goes in `RESULTS.md`.

## What can go wrong

- **Synthetic to real.** Slakh is sampled instruments, not a miked amp on a record. The last
  attempt (amp-simulated solo guitar) improved its own validation loss and made a real record
  worse. The frozen test of real mixes is there to catch exactly that.
- **Few distorted guitars.** Slakh's guitars are mostly clean and "distortion guitar" patches
  from a sampler. Heavy sections may need amp-rendered guitar mixed into Slakh backings.
- **The reference is the engine's own reading** of the guitar alone, so the gate cannot show
  the model became more correct than Riley is on solo guitar; it shows the band costs less.
