import { useRef, useState } from 'react';
import type { PracticeNote, Section } from './practiceProject';
import { chordSelection, copyNotes, edit, noteLabel, redo, snapTime, transformNotes, undo, validNotes, type EditHistory } from './referenceEditing';

type Props = {
  disabled?: boolean; notes: PracticeNote[]; duration: number; bpm: number; section: Section;
  onApply: (notes: PracticeNote[]) => void;
  onAudition: (notes: PracticeNote[], start: number, end: number) => void;
};
/** Draft-only piano roll: an explicit Apply is the only operation that changes the reference. */
export default function VisualReferenceEditor({ notes, duration, bpm, section, onApply, onAudition, disabled = false }: Props) {
  const initial = () => copyNotes(notes).map(n => ({ ...n, time: Math.min(n.time, duration - .01), duration: Math.max(.01, Math.min(n.duration, duration - n.time)) }));
  const [history, setHistory] = useState<EditHistory>(() => ({ past: [], present: initial(), future: [] }));
  const [selection, setSelection] = useState<number[]>([]);
  const [snap, setSnap] = useState('sixteenth');
  const [chord, setChord] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState('');
  const drag = useRef<{ x: number; y: number; selected: number[]; notes: PracticeNote[]; resize: boolean } | null>(null);
  const draft = history.present;
  const step = snap === 'off' ? .01 : 60 / bpm / (snap === 'beat' ? 1 : snap === 'eighth' ? 2 : 4);
  const visible = draft.flatMap((n, i) => n.time < section.end && n.time + n.duration > section.start ? [{ n, i }] : []).slice(0, 2000);
  const low = Math.max(0, Math.min(40, ...visible.map(({ n }) => n.midi)) - 2);
  const high = Math.min(127, Math.max(76, ...visible.map(({ n }) => n.midi)) + 2);
  const row = 18, labelWidth = 55, scale = 100;
  const width = labelWidth + Math.max(1, section.end - section.start) * scale;
  const height = (high - low + 1) * row + 25;
  const first = draft[selection[0]];
  const dirty = JSON.stringify(draft) !== JSON.stringify(notes);
  function replace(next: PracticeNote[]) {
    if (!validNotes(next, duration)) { setError('Notes must fit inside the reference, with MIDI pitch 0–127 and at least 0.01 seconds duration.'); return; }
    setError(''); setHistory(h => edit(h, next));
  }
  function move(change: { time?: number; pitch?: number; length?: number }) { replace(transformNotes(draft, selection, duration, change)); }
  function select(index: number, multi: boolean) {
    const group = chord ? chordSelection(draft, index) : [index];
    const selected = multi ? [...new Set([...selection, ...group])] : group;
    setSelection(selected); return selected;
  }
  function add(time: number, midi: number) {
    if (draft.length >= 30000) { setError('Reference has 30,000 notes. Delete a note first.'); return; }
    const at = Math.max(0, Math.min(duration - .01, snapTime(time, snap === 'off' ? 0 : step)));
    replace([...draft, { time: at, duration: Math.max(.01, Math.min(60 / bpm, duration - at)), midi }]); setSelection([draft.length]);
  }
  const changeHistory = (direction: 'undo' | 'redo') => { setHistory(direction === 'undo' ? undo : redo); setSelection([]); setError(''); };
  return <details className="visual-editor">
    <summary>Visual reference editor — notes and chord tones</summary>
    <p>Choose notes on the piano roll; drag to move pitch/time, or Alt-drag to change length. Arrow keys move a selection; Alt + left/right changes length. Shift-click adds notes to the selection. Edits stay in a draft until Apply.</p>
    <p className="helper">Showing {section.name}: {section.start.toFixed(2)}–{section.end.toFixed(2)} seconds of the reference. Note tails are bounded to the reference end. This edits pitches and timing, not guitar fingering or full notation.</p>
    <div className="presets">
      <label>Snap <select value={snap} onChange={e => setSnap(e.target.value)}><option value="sixteenth">1/16 note</option><option value="eighth">1/8 note</option><option value="beat">Beat</option><option value="off">Off (keyboard: 10 ms)</option></select></label>
      <label><input type="checkbox" checked={chord} onChange={e => setChord(e.target.checked)} /> Select chord tones together (attacks within 30 ms)</label>
      <label><input type="checkbox" checked={adding} onChange={e => setAdding(e.target.checked)} /> Click empty grid to add a note</label>
      <button type="button" disabled={!history.past.length} onClick={() => changeHistory('undo')}>Undo note edit</button>
      <button type="button" disabled={!history.future.length} onClick={() => changeHistory('redo')}>Redo note edit</button>
    </div>
    {error && <p role="alert">{error}</p>}
    <div className="piano-scroll" aria-label="Scrollable reference piano roll">
      <svg role="group" aria-label="Reference notes piano roll" width={width} height={height} viewBox={`0 0 ${width} ${height}`} onPointerDown={e => {
        if (disabled || !adding || e.target !== e.currentTarget && (e.target as SVGElement).dataset.grid !== 'true') return;
        const box = e.currentTarget.getBoundingClientRect();
        const x = (e.clientX - box.left) * width / box.width, y = (e.clientY - box.top) * height / box.height;
        if (x < labelWidth || y < 25) return;
        const midi = Math.max(low, Math.min(high, high - Math.floor((y - 25) / row)));
        add(section.start + (x - labelWidth) / scale, midi);
      }} onPointerMove={e => {
        if (disabled || !drag.current) return;
        const d = drag.current;
        const delta = (e.clientX - d.x) / scale;
        const time = snapTime(delta, snap === 'off' ? 0 : step);
        const next = transformNotes(d.notes, d.selected, duration, d.resize ? { length: time } : { time, pitch: Math.round((d.y - e.clientY) / row) });
        // Preview without filling undo history for every pointer movement.
        setHistory(h => ({ ...h, present: next }));
      }} onPointerUp={() => {
        if (disabled || !drag.current) return;
        const before = drag.current.notes; drag.current = null;
        setHistory(h => edit({ ...h, present: before }, h.present));
      }} onPointerCancel={() => { if (drag.current) { const before = drag.current.notes; drag.current = null; setHistory(h => ({ ...h, present: before })); } }}>
        {Array.from({ length: high - low + 1 }, (_, r) => {
          const midi = high - r, y = 25 + r * row;
          return <g key={midi}><rect data-grid="true" x={labelWidth} y={y} width={width - labelWidth} height={row} fill={[1,3,6,8,10].includes(midi % 12) ? '#192334' : '#222e40'} stroke="#66708533" /><text x={3} y={y + 13} fill="#cbd5e1" fontSize={11}>{noteLabel(midi)}</text></g>;
        })}
        {Array.from({ length: Math.min(2000, Math.ceil((section.end - section.start) / (60 / bpm)) + 1) }, (_, i) => {
          const time = section.start + i * 60 / bpm, x = labelWidth + (time - section.start) * scale;
          return <g key={i} pointerEvents="none"><line x1={x} x2={x} y1={25} y2={height} stroke="#94a3b866" /><text x={x + 2} y={15} fill="#cbd5e1" fontSize={11}>{time.toFixed(2)}s</text></g>;
        })}
        {visible.map(({ n, i }) => <rect key={i} role="button" tabIndex={0} aria-pressed={selection.includes(i)} aria-label={`Note ${i + 1}: ${noteLabel(n.midi)} at ${n.time.toFixed(2)} seconds, length ${n.duration.toFixed(2)}`} x={labelWidth + Math.max(0, n.time - section.start) * scale} y={25 + (high - n.midi) * row + 2} width={Math.max(5, (Math.min(section.end, n.time + n.duration) - Math.max(section.start, n.time)) * scale)} height={row - 4} rx={3} fill={selection.includes(i) ? '#fbbf24' : '#63cbbb'} stroke={selection.includes(i) ? '#fff' : '#0f172a'} aria-disabled={disabled} onClick={e => { if (!disabled && e.detail === 0) select(i, e.shiftKey); }} onKeyDown={e => {
          if (disabled) return;
          if (['Enter',' '].includes(e.key)) { e.preventDefault(); select(i, e.shiftKey); return; }
          if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Delete'].includes(e.key)) return;
          e.preventDefault(); const chosen = selection.includes(i) ? selection : [i]; setSelection(chosen);
          if (e.key === 'Delete') { replace(draft.filter((_, j) => !chosen.includes(j))); setSelection([]); return; }
          const sign = ['ArrowLeft','ArrowDown'].includes(e.key) ? -1 : 1;
          replace(transformNotes(draft, chosen, duration, e.key === 'ArrowUp' || e.key === 'ArrowDown' ? { pitch: sign } : e.altKey ? { length: sign * step } : { time: sign * step }));
        }} onPointerDown={e => {
          if (disabled) return;
          e.preventDefault(); e.stopPropagation(); e.currentTarget.focus(); const selected = select(i, e.shiftKey);
          drag.current = { x: e.clientX, y: e.clientY, selected, notes: draft, resize: e.altKey };
          e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId);
        }} />)}
      </svg>
    </div>
    {visible.length >= 2000 && <p>Only the first 2,000 overlapping notes are displayed. Choose a shorter section.</p>}
    <p aria-live="polite">{selection.length} note(s) selected. {dirty ? 'Unapplied draft changes.' : 'Reference unchanged.'}</p>
    {first && <div className="presets">
      <label>Selected MIDI pitch <input type="number" min={0} max={127} value={first.midi} onChange={e => { const v = Number(e.target.value); if (Number.isInteger(v)) move({ pitch: v - first.midi }); }} /></label>
      <label>Selected start seconds <input type="number" min={0} max={duration - .01} step={.01} value={first.time} onChange={e => { const v = Number(e.target.value); if (Number.isFinite(v)) move({ time: v - first.time }); }} /></label>
      <label>Selected length seconds <input type="number" min={.01} max={duration} step={.01} value={first.duration} onChange={e => { const v = Number(e.target.value); if (Number.isFinite(v)) move({ length: v - first.duration }); }} /></label>
      <button type="button" onClick={() => move({ pitch: 1 })}>Transpose selection up</button>
      <button type="button" onClick={() => move({ pitch: -1 })}>Transpose selection down</button>
      <button type="button" onClick={() => { replace(draft.filter((_, i) => !selection.includes(i))); setSelection([]); }}>Delete selected notes</button>
      <button type="button" onClick={() => {
        const copies = selection.map(i => draft[i]).map(n => ({ ...n, time: snapTime(n.time + 60 / bpm, snap === 'off' ? 0 : step) }));
        if (!validNotes([...draft, ...copies], duration)) { setError('Duplicate would exceed the reference end or note limit.'); return; }
        replace([...draft, ...copies]); setSelection(copies.map((_, i) => draft.length + i));
      }}>Duplicate one beat later</button>
    </div>}
    <div className="presets">
      <button type="button" onClick={() => add(section.start, 64)}>Add E4 at section start</button>
      <button type="button" onClick={() => onAudition(draft, section.start, section.end)}>Audition draft phrase</button>
      <button type="button" disabled={!selection.length} onClick={() => {
        const group = selection.map(i => draft[i]).filter(Boolean); if (!group.length) return;
        onAudition(group, Math.min(...group.map(n => n.time)), Math.min(duration, Math.max(...group.map(n => n.time + n.duration)) + .2));
      }}>Audition selected notes</button>
      <button type="button" disabled={!dirty} onClick={() => { if (validNotes(draft, duration)) onApply(copyNotes(draft).sort((a,b) => a.time - b.time || a.midi - b.midi)); else setError('Draft contains out-of-range notes.'); }}>Apply visual corrections</button>
      <button type="button" disabled={!dirty} onClick={() => { if (confirm('Discard all unapplied visual edits?')) { setHistory({ past: [], present: initial(), future: [] }); setSelection([]); } }}>Discard visual draft</button>
    </div>
    <p className="helper">Apply creates a new reference revision and revokes approval. Undo/redo affects this draft only. Old takes are not regraded or overwritten. Switching projects discards unapplied drafts; apply and save first.</p>
  </details>;
}
