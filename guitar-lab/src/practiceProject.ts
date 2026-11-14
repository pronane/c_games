import type { Comparison, DiffNote } from './compare';

export type PracticeNote = { time: number; duration: number; midi: number };
export type Section = { id: string; name: string; start: number; end: number };
export type Review = 'confirmed' | 'dismissed' | 'unsure';
export type PracticeSeed = {
  title: string; part: string; tuning: string; capo: number; bpm: number;
  duration: number; notes: PracticeNote[]; origin: 'chart' | 'transcription';
};
export type Attempt = {
  id: string; created: number; revision: number; start: number; end: number; speed: number;
  audio?: Blob; comparison?: Comparison; reviews: Record<string, Review>;
  audible?: string; useful?: string; improved?: string; latencyMeasured: boolean;
};
export type PracticeProject = PracticeSeed & {
  version: 1; id: string; revision: number; goal: string;
  practiceSpeed: number; activeSection: string;
  trust: 'unverified' | 'reviewed'; sections: Section[];
  ignored: string[]; attempts: Attempt[]; updated: number;
};
export function newProject(seed: PracticeSeed): PracticeProject {
  return { ...seed, notes: seed.notes.map(n => ({ time: n.time, duration: n.duration, midi: n.midi })),
    version: 1, id: crypto.randomUUID(), revision: 1, goal: '', practiceSpeed: .7, activeSection: '', trust: 'unverified',
    sections: [{ id: crypto.randomUUID(), name: 'Practice phrase', start: 0, end: Math.min(20, seed.duration) }],
    ignored: [], attempts: [], updated: Date.now() };
}
export function phraseNotes(project: PracticeProject, section: Section, speed: number) {
  return project.notes.filter(n => n.time >= section.start && n.time < section.end)
    .map(n => ({ ...n, time: (n.time - section.start) / speed, duration: Math.min(n.duration, section.end - n.time) / speed }));
}
export function issueKey(n: DiffNote) { return `${n.bar}:${n.id}:${n.kind}`; }
export function issueStatus(n: DiffNote, trust: PracticeProject['trust'], measured: boolean) {
  if (trust !== 'reviewed') return 'Reference may be wrong';
  if (n.kind === 'uncertain' || n.heard_faintly || ['wrong_duration', 'wrong_string'].includes(n.kind)) return 'Uncertain — review by ear';
  if (['early', 'late'].includes(n.kind) && !measured) return 'Device delay unverified';
  return 'Likely playing issue — confirm by listening';
}
export function comparable(a: Attempt, b: Attempt) {
  return a.revision === b.revision && a.start === b.start && a.end === b.end && a.speed === b.speed;
}
export function excludedPhrase(p: PracticeProject, s: Section) {
  return p.sections.some(region => p.ignored.includes(region.id) && region.start < s.end && s.start < region.end);
}
export function exercise(kind: string) {
  if (['early', 'late'].includes(kind)) return 'Count the beat aloud, mute the strings and land the change on the click. Then add the fretted notes.';
  if (kind === 'wrong_pitch') return 'Play the expected note or chord slowly, check the fretting, then approach it from the previous change.';
  if (kind === 'missing') return 'Isolate the change and check that every intended note rings clearly. Confirm the detector did not simply miss it.';
  if (kind === 'extra') return 'Listen for unwanted open strings and practise muting through the transition.';
  return 'Listen first. Sustain, effects and inferred fingering are uncertain; do not change technique based on this estimate alone.';
}
export function confirmedCount(a: Attempt) { return Object.values(a.reviews).filter(x => x === 'confirmed').length; }

/** Strict, bounded portable import. Imported data is never executed or trusted as human truth. */
export function validateProject(value: unknown): PracticeProject {
  const p = value as PracticeProject;
  const finite = (v: unknown, min: number, max: number) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
  const text = (v: unknown, max = 500) => typeof v === 'string' && v.length <= max;
  const fail = () => { throw Error('Invalid or unsupported practice project.'); };
  if (!p || p.version !== 1 || !text(p.id, 100) || !p.id || !text(p.title) || !text(p.part) || !text(p.tuning) || !text(p.goal, 2000)
    || !finite(p.capo, 0, 24) || !finite(p.bpm, 20, 400) || !finite(p.duration, .1, 600)
    || !finite(p.practiceSpeed, .5, 1) || !text(p.activeSection, 100)
    || !finite(p.revision, 1, 100000) || !finite(p.updated, 0, 1e15)
    || !['chart', 'transcription'].includes(p.origin) || !['unverified', 'reviewed'].includes(p.trust)) fail();
  if (!Array.isArray(p.notes) || p.notes.length > 30000 || p.notes.some(n => !n || !finite(n.time, 0, p.duration) || !finite(n.duration, .01, 600) || !Number.isInteger(n.midi) || !finite(n.midi, 0, 127))) fail();
  if (!Array.isArray(p.sections) || p.sections.length < 1 || p.sections.length > 100 || p.sections.some(s => !s || !text(s.id, 100) || !text(s.name) || !finite(s.start, 0, p.duration) || !finite(s.end, s.start + .1, p.duration))) fail();
  if (!Array.isArray(p.ignored) || p.ignored.length > 30000 || p.ignored.some(x => !text(x, 100))) fail();
  if (!Array.isArray(p.attempts) || p.attempts.length > 50) fail();
  let audioBytes = 0;
  for (const a of p.attempts) {
    audioBytes += a.audio instanceof Blob ? a.audio.size : 0;
    if (!a || !text(a.id, 100) || !finite(a.created, 0, 1e15) || !finite(a.revision, 1, 100000) || !finite(a.start, 0, p.duration) || !finite(a.end, a.start + .1, p.duration) || !finite(a.speed, .5, 1) || typeof a.latencyMeasured !== 'boolean') fail();
    if (!a.reviews || Array.isArray(a.reviews) || typeof a.reviews !== 'object' || Object.values(a.reviews).some(x => !['confirmed', 'dismissed', 'unsure'].includes(x))) fail();
    if (a.audio && (!(a.audio instanceof Blob) || a.audio.size > 30 * 1024 * 1024)) fail();
    for (const key of ['audible', 'useful', 'improved'] as const) if (a[key] !== undefined && !['yes', 'no', 'unsure'].includes(a[key]!)) fail();
    if (a.comparison) {
      const c = a.comparison;
      if (!Array.isArray(c.reports) || c.reports.length > 5) fail();
      for (const r of c.reports) {
        if (!r || !text(r.label) || !text(r.source, 30) || !r.summary || !Array.isArray(r.notes) || r.notes.length > 40000 || !Array.isArray(r.bars) || !Array.isArray(r.worst_bars)) fail();
        if (r.alignment_warning != null && !text(r.alignment_warning, 2000)) fail();
        for (const n of r.notes) if (!n || !finite(n.id, 0, 100000) || !finite(n.bar, 0, 100000) || !text(n.kind, 50) || !text(n.message, 2000) || (n.target_time != null && !finite(n.target_time, 0, 1200)) || (n.take_time != null && !finite(n.take_time, 0, 1200))) fail();
      }
    }
  }
  if (audioBytes > 50 * 1024 * 1024) throw Error('Retained recordings exceed the 50 MB project limit. Remove older audio first.');
  return p;
}

const DB = 'fretwork-practice-v1';
async function database() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore('projects', { keyPath: 'id' });
    r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
  });
}
export async function projectStore(action: 'list' | 'put' | 'delete', value?: PracticeProject | string): Promise<PracticeProject[]> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction('projects', action === 'list' ? 'readonly' : 'readwrite');
    const store = tx.objectStore('projects');
    const request = action === 'list' ? store.getAll() : action === 'put' ? store.put(validateProject(value)) : store.delete(value as string);
    tx.oncomplete = () => { db.close(); resolve(action === 'list' ? request.result as PracticeProject[] : []); };
    tx.onerror = tx.onabort = () => { db.close(); reject(tx.error ?? Error('Could not save project. Storage may be full.')); };
  });
}
export async function exportProject(project: PracticeProject) {
  const attempts = await Promise.all(project.attempts.map(async a => ({ ...a, audio: a.audio ? await new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result as string); reader.onerror = reject; reader.readAsDataURL(a.audio!);
  }) : undefined })));
  return new Blob([JSON.stringify({ ...project, attempts })], { type: 'application/json' });
}
export async function importProject(file: File) {
  if (file.size > 80 * 1024 * 1024) throw Error('Project exceeds the 80 MB import limit.');
  const p = JSON.parse(await file.text());
  if (!Array.isArray(p.attempts) || p.attempts.length > 50) throw Error('Invalid takes.');
  for (const a of p.attempts) if (a.audio) {
    if (typeof a.audio !== 'string' || !a.audio.startsWith('data:audio/wav;base64,') || a.audio.length > 42 * 1024 * 1024) throw Error('Invalid recording.');
    const bytes = Uint8Array.from(atob(a.audio.split(',')[1]), ch => ch.charCodeAt(0));
    a.audio = new Blob([bytes], { type: 'audio/wav' });
  }
  const project = validateProject(p);
  // Never overwrite a local project silently.
  return { ...project, id: crypto.randomUUID(), title: `${project.title} (imported)` };
}
