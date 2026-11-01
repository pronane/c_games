// Builds examples/night-watch-etude.gp from the alphaTex source next to it.
//   npx tsx examples/make-practice-piece.mts
import { readFileSync, writeFileSync } from "node:fs";
import * as alphaTab from "@coderline/alphatab";
const settings = new alphaTab.Settings();
const tex = readFileSync(new URL("./night-watch-etude.tex", import.meta.url), "utf8");
const score = alphaTab.importer.ScoreLoader.loadAlphaTex(tex, settings);
// Every bar must be exactly 4/4 (3840 ticks) or the timing would drift.
const bars = score.tracks[0].staves[0].bars;
for (const bar of bars) {
  const ticks = bar.voices[0].beats.reduce((t, b) => t + b.playbackDuration, 0);
  if (ticks !== 3840) throw Error(`Bar ${bar.index + 1} has ${ticks} ticks, not 3840`);
}
writeFileSync(new URL("./night-watch-etude.gp", import.meta.url), new alphaTab.exporter.Gp7Exporter().export(score, settings));
console.log(`${bars.length} bars, ${score.masterBars.filter((m) => m.section).map((m) => `bar ${m.index + 1}: ${m.section!.text}`).join(" | ")}`);
