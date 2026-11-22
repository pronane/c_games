# Locomotion styles from 100STYLE (CC BY 4.0)

21 loops come from **The 100STYLE Dataset - Ian Mason** (Mason, Starke and Komura, 2022), licensed CC BY 4.0. Sources: <https://www.ianxmason.com/100style/> and <https://zenodo.org/records/8127870>.

**Changes made:** the motion was retargeted onto the Arena FC skeleton. Loops were cut and straightened. Sidestep and backpedal directions were measured from the root.

**Styles and gaits used:**
- Neutral, Rushed, BigSteps, Proud and Heavyset, in forward runs and walks, backpedals and sidesteps.
- BentKnees and Crouched (a defender's low stance), in sidesteps and backpedals only.

**How each take was processed:**
1. The actors moved in curves inside a small capture area. So `Tools/import_100style.py` picks the straightest 2 seconds of each take (or, for a sidestep, the most one-way stretch).
2. Sprite Forge's `motionlib.import_file` imports it. This needed v11.35's `bvh_classic` bone naming: Collar/Shoulder/Elbow/Wrist and Hip/Knee/Ankle.
3. The remaining heading drift is taken out of the loop.
4. The loop's speed and direction come from the hips' travel in the body's own frame.

Speeds run from 0.4 to 2.2 m/s. This is jogging and shuffling pace, so the loops add variety to walking, jogging, jockeying and backpedalling, not to sprints.
