import {
  barLines,
  noteChips,
  scoreCards,
  shownReport,
  tempoNote,
  worstLines,
  type Comparison,
} from "./compare";

/** Stem, notation, and combined scores, then the notes and bars that didn't match. */
export default function TakeReport({
  comparison,
  onPractise,
}: {
  comparison: Comparison;
  /** Loop these bars (slower) to practise them. */
  onPractise?: (first: number, last?: number) => void;
}) {
  const report = shownReport(comparison);
  if (!report) return null;
  const cards = scoreCards(comparison);
  const tempo = tempoNote(report);
  const worst = worstLines(report);
  const chips = noteChips(report);
  const bars = barLines(report);
  const byBar = new Map<number, typeof chips>();
  for (const chip of chips) {
    const row = byBar.get(chip.bar) ?? [];
    row.push(chip);
    byBar.set(chip.bar, row);
  }
  return (
    <div className="take-diff" aria-label="Take compared with the target">
      <p className="helper" role="note">Diagnostic estimates, not confirmed playing mistakes. Reference errors, separation, sustain and alignment can cause false warnings. Use Review → Practise → Retry to review the reference and confirm findings by ear.</p>
      <div className="diff-scores">
        {cards.map((card) => (
          <div key={card.key} className={"diff-score" + (card.key === "combined" ? " combined" : "")}>
            <small>{card.label}</small>
            <b>{card.overall}</b>
            <span>{card.detail}</span>
          </div>
        ))}
      </div>
      {report.notes.some(n => n.kind === "uncertain") && <p role="note">{report.notes.filter(n => n.kind === "uncertain").length} note(s) are uncertain and excluded from the diagnostic scores. A high score on assessed notes does not confirm those notes.</p>}
      {report.alignment_warning && <p role="alert">{report.alignment_warning}</p>}
      {tempo && <p className="helper">{tempo}</p>}
      {report.duration_policy === "review_only" && <p className="helper" role="note">{report.duration_notice}</p>}
      {onPractise && report.worst_bars.length > 0 && (
        <button
          className="secondary"
          onClick={() => {
            const bars = report.worst_bars.map((b) => b.bar).filter((b) => b > 0);
            if (bars.length) onPractise(Math.min(...bars), Math.max(...bars));
          }}
        >
          Loop the weakest bars, slower
        </button>
      )}
      {worst.length ? (
        <ul className="diff-worst">
          {worst.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="helper">No issues detected in the notes we could line up. This does not verify every note.</p>
      )}
      <div className="diff-legend" aria-hidden="true">
        <span className="diff-note diff-wrong-pitch">Wrong pitch</span>
        <span className="diff-note diff-wrong-string">Wrong string</span>
        <span className="diff-note diff-late">Early / late</span>
        <span className="diff-note diff-wrong-duration">Duration</span>
        <span className="diff-note diff-missing">Missing</span>
        <span className="diff-note diff-extra">Extra</span>
      </div>
      <div className="diff-staff" role="list" aria-label="Notes on the notation and tab">
        {[...byBar.entries()].map(([bar, row]) => (
          <div key={bar} className="diff-bar-notes" role="listitem">
            <small>Bar {bar}</small>
            <div>
              {row.map((chip) => (
                <span key={chip.id} className={chip.className} title={chip.title}>
                  <b>{chip.text}</b>
                  {chip.pitch && chip.pitch !== chip.text ? <small>{chip.pitch}</small> : null}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <ol className="diff-bars">
        {bars.map((bar) => (
          <li key={bar.bar}>
            <span className={"section-score " + bar.className}>
              <small>Bar {bar.bar}</small>
              {bar.score}
            </span>
            {onPractise && bar.className !== "good" && bar.className !== "none" && bar.bar > 0 && (
              <button className="link-button" onClick={() => onPractise(bar.bar)}>
                Practise this bar
              </button>
            )}
            <ul>
              {bar.messages.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      <p className="helper">
        {comparison.transcription === "clean-guitar Basic Pitch"
          ? "Your take was transcribed as clean guitar and lined up to the target, so playing slower or rushing the phrase is allowed for."
          : "Lined up to the target note by note. Playing slower or rushing the phrase is allowed for."}
        {comparison.reports.some((r) => r.source === "tab")
          ? " Your score is against your tab; the app's own transcription is shown alongside for interest."
          : comparison.combined
            ? " Stem and notation are scored on their own; combined is their average."
            : ""}
      </p>
    </div>
  );
}
