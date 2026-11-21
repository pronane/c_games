# Real-match calibration targets

`skillcorner_metrics.json` holds team-shape, pressure and speed figures measured from
three A-League 2024/25 matches in the [SkillCorner open data](https://github.com/SkillCorner/opendata)
broadcast-tracking set (MIT licence, credit: SkillCorner). Regenerate with
`Tools/skillcorner_metrics.py` after downloading the matches' `*_tracking_extrapolated.jsonl`
files to `/tmp/sc/`.

| metric | meaning |
| --- | --- |
| length_in / length_out | back-to-front spread of the 10 outfield players, in / out of possession (m) |
| width_in / width_out | touchline-to-touchline spread (m) |
| def_line_from_gk | deepest outfield defender to own keeper, out of possession (m) |
| press_median / press_under2m | carrier to nearest opponent (m), and the share of time inside 2 m |
| speed_mean / share_over_5_5 / share_over_7 / speed_p95 | outfield running speeds (m/s) |

`MatchCoreTests` ("Calibration gate") measures the same figures from four AI matches and
fails when the simulation drifts out of its bands. The bands sit around the real values for
shape. For speed and pressure they are deliberately looser: an arcade match is denser than a
real one, and SkillCorner's possession holder is kept through short passes, which pushes the
real pressure figure up.
