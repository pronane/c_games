import { chordShape } from "./chordShapes";

export type BoardNote = { time: number; duration: number; midi: number; string?: number | null; fret?: number | null };
type Pos = { string: number; fret: number };

const INLAYS = [3, 5, 7, 9, 15, 17, 19, 21];

/** Where a note is played: the tab's own string and fret, else the lowest fret that reaches it. */
export function place(n: BoardNote, openStrings: number[], maxFret: number): Pos | null {
  if (n.string && n.fret != null && n.string >= 1 && n.string <= openStrings.length) return { string: n.string, fret: n.fret };
  const options = openStrings
    .map((open, i) => ({ string: i + 1, fret: n.midi - open }))
    .filter((p) => p.fret >= 0 && p.fret <= maxFret)
    .sort((a, b) => a.fret - b.fret);
  return options[0] ?? null;
}

/**
 * The neck, high e at the top, with the notes sounding now lit and the next ones fading in.
 * `openStrings` is in the instrument profile's order: string 1 (the highest) first.
 */
export default function Fretboard({
  notes,
  take,
  time,
  openStrings,
  maxFret = 22,
  ahead = 1.2,
  label,
}: {
  notes: BoardNote[];
  /** Your playing, drawn as rings over the target notes. */
  take?: BoardNote[];
  time: number;
  openStrings: number[];
  maxFret?: number;
  ahead?: number;
  label: string;
}) {
  const strings = openStrings.length;
  const near = (list: BoardNote[], from: number, to: number) => list.filter((n) => n.time < to && n.time + Math.max(n.duration, 0.12) > from);
  const now = near(notes, time, time + 0.001),
    next = near(notes, time + 0.001, time + ahead).filter((n) => n.time > time),
    mine = take ? near(take, time, time + 0.001) : [];
  const placed = (list: BoardNote[]) => list.map((n) => ({ n, p: place(n, openStrings, maxFret) })).filter((x): x is { n: BoardNote; p: Pos } => !!x.p);
  // Show the stretch of neck in use: from a little below the lowest fret to 12 frets above it.
  const around = placed([...now, ...next]);
  const low = around.length ? Math.max(0, Math.min(...around.map((x) => x.p.fret)) - 2) : 0;
  const first = low <= 3 ? 0 : low,
    last = Math.min(maxFret, first + 12);
  const W = 640,
    H = 26 + strings * 22,
    left = 34,
    right = 10,
    top = 16;
  const fx = (f: number) => left + ((f - first) / (last - first + 0.5)) * (W - left - right);
  const noteX = (f: number) => (f === 0 ? left - 14 : (fx(f - 1) + fx(f)) / 2);
  const sy = (s: number) => top + (s - 1) * 22;
  const name = (m: number) => ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][m % 12];
  return (
    <figure className="fretboard" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${label}: ${now.length} notes sounding`}>
        <rect x={left} y={top - 6} width={W - left - right} height={(strings - 1) * 22 + 12} rx="4" className="neck" />
        {Array.from({ length: last - first + 1 }, (_, i) => first + i).map((f) => (
          <g key={f}>
            {f > 0 && <line x1={fx(f)} x2={fx(f)} y1={top - 6} y2={sy(strings) + 6} className="fret" />}
            {INLAYS.includes(f) && <circle cx={noteX(f)} cy={(sy(1) + sy(strings)) / 2} r="4" className="inlay" />}
            {f === 12 && (
              <>
                <circle cx={noteX(f)} cy={sy(2) + 11} r="4" className="inlay" />
                <circle cx={noteX(f)} cy={sy(strings - 1) - 11} r="4" className="inlay" />
              </>
            )}
            {f > 0 && (f % 2 === 1 || f === 12) && (
              <text x={noteX(f)} y={H - 2} className="fret-number">
                {f}
              </text>
            )}
          </g>
        ))}
        {first === 0 && <line x1={left} x2={left} y1={top - 6} y2={sy(strings) + 6} className="nut" />}
        {Array.from({ length: strings }, (_, i) => i + 1).map((s) => (
          <line key={s} x1={left - 22} x2={W - right} y1={sy(s)} y2={sy(s)} className="string" strokeWidth={0.8 + (s - 1) * 0.35} />
        ))}
        {placed(next).map(({ n, p }, i) => {
          const soon = 1 - (n.time - time) / ahead;
          return <circle key={`n${i}`} cx={noteX(p.fret)} cy={sy(p.string)} r={5 + 4 * soon} className="note next" opacity={0.15 + 0.5 * soon} />;
        })}
        {placed(now).map(({ n, p }, i) => (
          <g key={`c${i}`}>
            <circle cx={noteX(p.fret)} cy={sy(p.string)} r="9.5" className="note now" />
            <text x={noteX(p.fret)} y={sy(p.string) + 3.5} className="note-name">
              {name(n.midi)}
            </text>
          </g>
        ))}
        {placed(mine).map(({ p }, i) => (
          <circle key={`m${i}`} cx={noteX(p.fret)} cy={sy(p.string)} r="12" className="note mine" />
        ))}
      </svg>
      <figcaption>
        {label}
        {take ? " · rings: what you played" : ""}
      </figcaption>
    </figure>
  );
}

/** A chord box: six strings, the first frets of the shape, X / O above. */
export function ChordDiagram({ name, size = 1 }: { name: string; size?: number }) {
  const shape = chordShape(name);
  if (!shape) return <div className="chord-diagram empty">{name === "N" ? "–" : name}</div>;
  const played = shape.frets.filter((f): f is number => f != null && f > 0);
  const base = shape.barre && shape.barre > 1 ? shape.barre : 1;
  const span = 4,
    w = 70 * size,
    h = 86 * size,
    x0 = 10 * size,
    y0 = 18 * size,
    dx = (w - 2 * x0) / 5,
    dy = (h - y0 - 8 * size) / span;
  const sx = (i: number) => x0 + i * dx;
  const barreFrom = shape.frets.indexOf(shape.barre),
    barreTo = shape.frets.lastIndexOf(shape.barre);
  const fy = (f: number) => y0 + (f - base + 0.5) * dy;
  return (
    <div className="chord-diagram">
      <b>{name}</b>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-label={`${name} chord shape`}>
        {Array.from({ length: span + 1 }, (_, i) => (
          <line key={`f${i}`} x1={x0} x2={w - x0} y1={y0 + i * dy} y2={y0 + i * dy} className={i === 0 && base === 1 ? "nut" : "fret"} />
        ))}
        {Array.from({ length: 6 }, (_, i) => (
          <line key={`s${i}`} x1={sx(i)} x2={sx(i)} y1={y0} y2={y0 + span * dy} className="string" />
        ))}
        {shape.frets.map((f, i) =>
          f == null ? (
            <text key={i} x={sx(i)} y={y0 - 5 * size} className="mark">
              ×
            </text>
          ) : f === 0 ? (
            <circle key={i} cx={sx(i)} cy={y0 - 8 * size} r={3 * size} className="open" />
          ) : null,
        )}
        {shape.barre != null && shape.barre > 0 && barreFrom >= 0 && (
          <rect
            x={sx(barreFrom) - 4 * size}
            y={fy(shape.barre) - 4 * size}
            width={sx(barreTo) - sx(barreFrom) + 8 * size}
            height={8 * size}
            rx={4 * size}
            className="barre"
          />
        )}
        {shape.frets.map((f, i) => (f != null && f > 0 && f !== shape.barre ? <circle key={`d${i}`} cx={sx(i)} cy={fy(f)} r={4.5 * size} className="dot" /> : null))}
        {base > 1 && (
          <text x={w - 2} y={fy(base) + 3} className="base">
            {base}
          </text>
        )}
      </svg>
      {played.length === 0 && <small>open</small>}
    </div>
  );
}
