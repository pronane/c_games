# Candidate player (not the file the game loads)

`gaelic_player.glb` here is a copy of the shipped squad player with one extra clip, `bounce`, merged by bone name from `assets/source/Gaelic_football_bounce.fbx`.

That FBX is a four-second near-stand: the feet stay put and the right hand dips about 30 cm. It is not a running bounce. The game uses a clip named `bounce` only when the carrier has almost stopped. A moving bounce still plays `run_ball`, and the ball is dropped to the ground by the game.

The shipped file stays `assets/models/gaelic_player.glb`. Try this copy with:

```
./gaelic_football --model assets/candidates/gaelic_player.glb
```

`manifest.json` records the source hashes and the command. It does not state a licence. The bounce FBX's real author and terms have to be recorded before this candidate is redistributed. Meshes, `.parts` and the kit atlases are unchanged; the atlas files remain `assets/textures/kit_*.png`.
