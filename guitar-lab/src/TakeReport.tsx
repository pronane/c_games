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
export default function TakeReport({ comparison }: { comparison: Comparison }) {
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
      <div className="diff-scores">
        {cards.map((card) => (
          <div key={card.key} className={"diff-score" + (card.key === "combined" ? " combined" : "")}>
            <small>{card.label}</small>
            <b>{card.overall}</b>
            <span>{card.detail}</span>
          </div>
        ))}
      </div>
      {tempo && <p className="helper">{tempo}</p>}
      {worst.length ? (
        <ul className="diff-worst">
          {worst.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="helper">Every note we could line up matches this target.</p>
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
        {comparison.combined ? " Stem and notation are scored on their own; combined is their average." : ""}
      </p>
    </div>
  );
}
