import type { Refinement } from "./engineApi";

function percent(score: number | null) {
  return score == null ? "—" : `${Math.round(score * 100)}`;
}

/** Before/after match score and the per-pass log. Hidden when the loop was not asked for. */
export default function RefinementReport({ refinement }: { refinement?: Refinement | null }) {
  if (!refinement) return null;
  if (!refinement.enabled) {
    if (!refinement.skipped || refinement.skipped === "not requested") return null;
    const text =
      refinement.skipped === "notation reference is exact"
        ? "The reference is written notation, so those notes are already exact and were not revised."
        : refinement.skipped === "FRETWORK_REFINE is not set"
          ? "Refine was requested. The server has it switched off (start it with FRETWORK_REFINE=1)."
          : refinement.skipped === "refinement is guitar-only"
            ? "Refine was requested. This loop revises guitar transcriptions."
            : refinement.skipped;
    return <p className="helper">{text}</p>;
  }
  return (
    <div className="refinement">
      <div className="refinement-score">
        <span>Match score</span>
        <strong>
          {percent(refinement.original_score)}
          <small> → </small>
          {percent(refinement.final_score)}
        </strong>
        <em>
          {refinement.stopped}
          {refinement.elapsed_seconds ? ` · ${refinement.elapsed_seconds.toFixed(1)}s` : ""}
        </em>
      </div>
      {refinement.iterations.length > 0 && (
        <ol>
          {refinement.iterations.map((step) => (
            <li key={`${step.part ?? "part"}-${step.iteration}`}>
              Pass {step.iteration}
              {step.part ? ` · ${step.part}` : ""}: {percent(step.score)}
              {step.changes
                ? ` · ${step.changes} change${step.changes === 1 ? "" : "s"}`
                : ""}
              {step.changed.length ? ` — ${step.changed.join("; ")}` : step.action ? ` — ${step.action}` : ""}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
