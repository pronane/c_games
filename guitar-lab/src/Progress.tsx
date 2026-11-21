import { TrendingUp } from "lucide-react";
import { summarise, type ProgressEntry, type Trainer } from "./progress";

const pct = (x: number | null) => (x == null ? "–" : `${x}%`);
const when = (ms: number) =>
  new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short" }) +
  " " +
  new Date(ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });

/** A tiny line of scores, oldest to newest. */
function Spark({ scores }: { scores: (number | null)[] }) {
  const pts = scores.map((s, i) => [i, s] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (pts.length < 2) return null;
  const w = 90,
    h = 22,
    n = Math.max(1, scores.length - 1);
  const d = pts.map(([i, s], k) => `${k ? "L" : "M"}${((i / n) * w).toFixed(1)},${(h - (s / 100) * h).toFixed(1)}`).join(" ");
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

/** Your takes on this song over time, per stretch of bars, kept in this browser. */
export default function Progress({
  history,
  pass,
  onPractise,
  onClear,
}: {
  history: ProgressEntry[];
  pass: number;
  onPractise: (from: number, to: number) => void;
  onClear: () => void;
}) {
  if (!history.length) return null;
  const rows = summarise(history, pass);
  return (
    <div className="progress-panel" aria-label="Your progress">
      <h4>
        <TrendingUp size={15} /> Your progress on this song
      </h4>
      <table>
        <thead>
          <tr>
            <th>Bars</th>
            <th>Takes</th>
            <th>Best</th>
            <th>Best at full speed</th>
            <th>Fastest at {pass}%+</th>
            <th>Trend</th>
            <th>Last</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.from}-${r.to}`}>
              <td>
                {r.from}–{r.to}
              </td>
              <td>{r.takes}</td>
              <td>{pct(r.best)}</td>
              <td>{pct(r.bestFull)}</td>
              <td>{r.fastestPass == null ? "–" : `${Math.round(r.fastestPass * 100)}%`}</td>
              <td>
                <Spark scores={r.scores} />
              </td>
              <td>
                {pct(r.last.score)} at {Math.round(r.last.speed * 100)}%
                <small>{when(r.last.at)}</small>
              </td>
              <td>
                <button className="link-button" onClick={() => onPractise(r.from, r.to)}>
                  Practise
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="helper">
        Kept in this browser only. Scores are against {history.some((h) => h.against.startsWith("tab")) ? "your tab where you chose it" : "the app's transcription"}.{" "}
        <button className="link-button" onClick={onClear}>
          Clear this song's history
        </button>
      </p>
    </div>
  );
}

/** Speed-trainer settings. */
export function TrainerControls({
  trainer,
  onChange,
  status,
  disabled,
}: {
  trainer: Trainer;
  onChange: (t: Trainer) => void;
  status: string;
  disabled?: boolean;
}) {
  const select = (id: string, label: string, value: number, options: number[], fmt: (v: number) => string, key: keyof Trainer) => (
    <label className="speed">
      {label}
      <select id={id} value={value} disabled={disabled || !trainer.on} onChange={(e) => onChange({ ...trainer, [key]: Number(e.target.value) })}>
        {options.map((v) => (
          <option key={v} value={v}>
            {fmt(v)}
          </option>
        ))}
      </select>
    </label>
  );
  const pc = (v: number) => `${Math.round(v * 100)}%`;
  return (
    <div className="guitar-sound trainer" aria-label="Speed trainer">
      <label className="speed">
        <input id="trainer-on" type="checkbox" checked={trainer.on} disabled={disabled} onChange={(e) => onChange({ ...trainer, on: e.target.checked })} />
        <b>Speed trainer</b>
      </label>
      {select("trainer-start", "Start at", trainer.start, [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8], pc, "start")}
      {select("trainer-step", "Step up", trainer.step, [0.05, 0.1], (v) => `+${Math.round(v * 100)}%`, "step")}
      {select("trainer-pass", "when you score", trainer.pass, [70, 75, 80, 85, 90, 95], (v) => `${v}%+`, "pass")}
      <small className="helper">
        {trainer.on
          ? status ||
            "Loop a few bars and press Play along & record. Each take is reviewed straight away; score enough and the next one is a step faster."
          : "Start a passage slow and speed up only when you play it cleanly."}
      </small>
    </div>
  );
}
