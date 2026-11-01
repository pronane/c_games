// Builds the tab-lesson fixtures: an original 8-bar Drop D riff as Guitar Pro 7 and as text tab.
import { writeFileSync } from "node:fs";
import * as alphaTab from "@coderline/alphatab";
const settings = new alphaTab.Settings();
// alphaTex: fret.string, string 1 = high e. Drop D: low string is D.
const riff = (a: string, b: string) => `${a} | ${b} |`;
const bar1 = "0.6.8 0.6.8 3.6.8 0.6.8 5.6.8 0.6.8 3.6.8 0.6.8";
const bar2 = "(0.6 0.5 0.4).2 (3.6 3.5 3.4).4 (5.6 5.5 5.4).4";
const lead = "7.3.8 9.3.8 7.2.8 8.2.8 10.2.8 8.2.8 7.2.4";
const lead2 = "10.1.8 8.1.8 7.1.8 8.2.8 7.2.2";
const tex = `\\title "Drop D practice riff" \\artist "Guitar Lab" \\tempo 100
\\tuning e4 b3 g3 d3 a2 d2 .
${riff(bar1, bar2)} ${riff(bar1, bar2)} ${lead} | ${lead2} | ${riff(bar1, bar2)}`;
const score = alphaTab.importer.ScoreLoader.loadAlphaTex(tex, settings);
writeFileSync("tests/fixtures/drop-d-riff.gp", new alphaTab.exporter.Gp7Exporter().export(score, settings));
writeFileSync(
  "tests/fixtures/a-minor-arpeggio.txt",
  `A minor arpeggio (Guitar Lab practice tab, 90 BPM)

e|---------------0-|-0---------------|---------------0-|-0---------------|
B|-------------1---|-1---------------|-------------1---|-0---------------|
G|---------2-------|-0---------------|---------2-------|-0---------------|
D|-----2-----------|-2---------------|-----2-----------|-0---------------|
A|-0---------------|-3---------------|-0---------------|-2---------------|
E|-----------------|-----------------|-----------------|-3---------------|
`,
);
console.log("bars", score.masterBars.length, "tuning", score.tracks[0].staves[0].tuning);
