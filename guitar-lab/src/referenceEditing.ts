import type { PracticeNote } from './practiceProject';

export type EditHistory = { past: PracticeNote[][]; present: PracticeNote[]; future: PracticeNote[][] };
export const copyNotes = (notes: PracticeNote[]) => notes.map(n => ({ time: n.time, duration: n.duration, midi: n.midi }));
export function noteLabel(midi: number) { return `${['C','C♯','D','E♭','E','F','F♯','G','A♭','A','B♭','B'][midi % 12]}${Math.floor(midi / 12) - 1}`; }
export function snapTime(time: number, step: number) { return step > 0 ? Math.round(time / step) * step : time; }
export function validNotes(notes: PracticeNote[], duration: number) {
  return notes.length <= 30000 && notes.every(n => Number.isFinite(n.time) && n.time >= 0 && n.time <= duration - .01 && Number.isFinite(n.duration) && n.duration >= .01 && n.time + n.duration <= duration + 1e-7 && Number.isInteger(n.midi) && n.midi >= 0 && n.midi <= 127);
}
export function edit(history: EditHistory, notes: PracticeNote[]): EditHistory {
  if (JSON.stringify(history.present) === JSON.stringify(notes)) return history;
  return { past: [...history.past, history.present].slice(-40), present: copyNotes(notes), future: [] };
}
export function undo(history: EditHistory): EditHistory {
  if (!history.past.length) return history;
  return { past: history.past.slice(0, -1), present: history.past.at(-1)!, future: [history.present, ...history.future] };
}
export function redo(history: EditHistory): EditHistory {
  if (!history.future.length) return history;
  return { past: [...history.past, history.present].slice(-40), present: history.future[0], future: history.future.slice(1) };
}
/** One bounded transform for a selection. Preserve chord intervals and spacing at the edges. */
export function transformNotes(notes: PracticeNote[], selected: number[], duration: number, change: { time?: number; pitch?: number; length?: number }): PracticeNote[] {
  const group = selected.filter(i => notes[i]).map(i => notes[i]);
  if (!group.length) return notes;
  const time = Math.max(-Math.min(...group.map(n => n.time)), Math.min(change.time ?? 0, duration - Math.max(...group.map(n => n.time + n.duration))));
  const pitch = Math.max(-Math.min(...group.map(n => n.midi)), Math.min(Math.round(change.pitch ?? 0), 127 - Math.max(...group.map(n => n.midi))));
  const length = Math.max(.01 - Math.min(...group.map(n => n.duration)), Math.min(change.length ?? 0, Math.min(...group.map(n => duration - n.time - n.duration))));
  return notes.map((n, i) => selected.includes(i) ? { time: Math.round((n.time + time) * 1e6) / 1e6, midi: n.midi + pitch, duration: Math.max(.01, Math.round((n.duration + length) * 1e6) / 1e6) } : n);
}
export function chordSelection(notes: PracticeNote[], index: number) {
  return notes.flatMap((n, i) => Math.abs(n.time - notes[index].time) < .03 ? [i] : []);
}
