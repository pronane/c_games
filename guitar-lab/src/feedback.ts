// Turns note-level comparison findings into what a teacher would say: a few concrete
// points ("2 wrong notes in bar 2, rushed bar 6") and an estimated score per section.
// Inputs are model estimates, so the wording stays "looks like" and scores are rounded.

export type Finding = {
  kind: string;
  take_time?: number;
  reference_time?: number;
  latency_compensated_seconds?: number;
};
/** Start time (seconds, in the compared passage) and number of each bar. */
export type BarMark = { number: number; time: number };
export type Section = {
  label: string;
  start: number;
  end: number;
  notes: number;
  matched: number;
  wrong: number;
  missed: number;
  extra: number;
  early: number;
  late: number;
  /** Mean early(-)/late(+) of matched notes, seconds, latency already removed. */
  drift: number | null;
  score: number | null;
};

const TIME_FEEL = 0.05;

/** Sections: one per bar when bars are known, otherwise 4-second slices. */
export function sections(duration: number, bars?: BarMark[]): { label: string; start: number; end: number }[] {
  if (bars && bars.length) {
    const marks = bars.filter((b) => b.time < duration - 0.05);
    return marks.map((b, i) => ({
      label: `bar ${b.number}`,
      start: Math.max(0, b.time),
      end: i + 1 < marks.length ? marks[i + 1].time : duration,
    }));
  }
  const out = [];
  for (let t = 0; t < duration - 0.05; t += 4)
    out.push({ label: `${Math.floor(t)}–${Math.floor(Math.min(duration, t + 4))} s`, start: t, end: Math.min(duration, t + 4) });
  return out;
}

export function summarise(findings: Finding[], duration: number, bars?: BarMark[]) {
  const rows: Section[] = sections(duration, bars).map((s) => ({
    ...s,
    notes: 0,
    matched: 0,
    wrong: 0,
    missed: 0,
    extra: 0,
    early: 0,
    late: 0,
    drift: null,
    score: null,
  }));
  const at = (t: number) => rows.find((r) => t >= r.start && t < r.end) ?? rows[rows.length - 1];
  const drifts = new Map<Section, number[]>();
  for (const f of findings) {
    const t = f.reference_time ?? f.take_time;
    if (t === undefined || !rows.length) continue;
    const row = at(t);
    if (f.kind === "unmatched_take") {
      row.extra++;
      continue;
    }
    row.notes++;
    if (f.kind === "unmatched_reference") row.missed++;
    else if (f.kind === "pitch_difference") row.wrong++;
    else {
      const d = f.latency_compensated_seconds ?? 0;
      if (f.kind === "timing_difference") (d < 0 ? row.early++ : row.late++);
      else row.matched++;
      drifts.set(row, [...(drifts.get(row) ?? []), d]);
    }
  }
  for (const row of rows) {
    const d = drifts.get(row);
    row.drift = d && d.length ? d.reduce((a, b) => a + b, 0) / d.length : null;
    const graded = row.notes + row.extra;
    // Timing slips count half: the right note a little off the beat is closer than a wrong one.
    row.score = graded ? Math.round((100 * (row.matched + 0.5 * (row.early + row.late))) / graded) : null;
  }
  const graded = rows.filter((r) => r.score !== null);
  const total = graded.reduce((s, r) => s + r.notes + r.extra, 0);
  const overall = total
    ? Math.round(graded.reduce((s, r) => s + (r.score! * (r.notes + r.extra)) / 100, 0) * 100 / total)
    : null;

  const points: { weight: number; text: string }[] = [];
  const plural = (n: number, one: string, many = one + "s") => `${n} ${n === 1 ? one : many}`;
  for (const r of rows) {
    if (r.wrong) points.push({ weight: 3 * r.wrong, text: `${plural(r.wrong, "wrong note")} in ${r.label}` });
    if (r.missed) points.push({ weight: 2 * r.missed, text: `${plural(r.missed, "missed note")} in ${r.label}` });
    if (r.extra) points.push({ weight: r.extra, text: `${plural(r.extra, "extra note")} in ${r.label}` });
    const slips = r.early + r.late;
    if (r.drift !== null && Math.abs(r.drift) > TIME_FEEL && slips)
      points.push({
        weight: 2 * slips,
        text: `${r.drift < 0 ? "rushed" : "dragged"} ${r.label} (about ${Math.round(Math.abs(r.drift) * 1000)} ms ${r.drift < 0 ? "early" : "late"})`,
      });
  }
  points.sort((a, b) => b.weight - a.weight);
  const worst = [...graded].sort((a, b) => a.score! - b.score!)[0];
  let next: string;
  if (!graded.length) next = "No notes were compared. Check the recording level and try again.";
  else if (!points.length) next = "Every note we could compare lined up. Try the next section or a faster speed.";
  else if (worst && worst.score! < 70)
    next = `Loop ${worst.label} slowly until it feels easy, then bring the speed back up.`;
  else next = `Close. Play it again and listen for ${points[0].text.split(" in ")[0].split(" (")[0]}.`;
  return { sections: rows, overall, points: points.slice(0, 4).map((p) => p.text), next };
}
