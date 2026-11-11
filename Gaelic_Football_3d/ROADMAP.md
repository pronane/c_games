# Gaelic Football roadmap

The rules stay in `src/game.c`. This list is the order of work. Only the first item is in progress.

1. **Movement and the ball.** Upright walk, jog and sprint, with the cycle sped to the ground speed and the stance foot planted. Turns ease off and the chest leads the hips. The ball stays in both hands when he is standing or jogging, in one hand when he sprints (the other arm keeps swinging), on the toe for a solo, on the ground for a bounce, and it leaves on the kick and the fist. The shipped GLB is unchanged. A candidate with an extra clip is produced by Sprite Forge (`sprite_forge/tools/GAELIC_CLIP_MERGE.md`), not by replacing the squad file.
2. **Support play.** Support runs, overlaps, defenders recovering, and players offering for the kick-out.
3. **Contact.** A legal shoulder and a shield, stumbles when contact is fair, and the frees already given for a tackle from behind or over the shoulder.
4. **Kicking and the fist.** A lob and a driven kick pass, a fist pass that stays up, and a one-two.
5. **Scores.** The two-point arc, a fisted point, and the keeper rushing or standing on a penalty. Check what the engine already scores before adding a second copy of it.
6. **The referee.** Advantage and calling play back, and dissent. Check the current GAA rules, and keep the five-step count in this game separate from the official four-step rule where they differ.
7. **A match around the play.** County and team kits, half time and full time, the GAA scoreline, and a replay of a score.
