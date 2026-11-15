import { blobData, decodeAttachment, phraseNotes, type Attempt, type PracticeProject, type PracticeNote } from './practiceProject';

export type ListeningPacket = {
  schema: 'fretwork-listening-packet-v1'; id: string;
  window: { start: number; end: number; speed: number };
  reference: { notes: PracticeNote[]; bpm: number; tuning: string; part: string; revision: number; reviewed: boolean };
  audio: string; sha256: string;
};
export type ListeningLabel = { start: number; end: number; kind: 'pitch' | 'timing' | 'missing' | 'extra' | 'sustain' | 'noise' | 'correct' | 'uncertain'; comment: string };
export const labelKinds: ListeningLabel['kind'][] = ['pitch','timing','missing','extra','sustain','noise','correct','uncertain'];
function core(p: ListeningPacket) {
  return { schema: p.schema, id: p.id, window: { start: p.window.start, end: p.window.end, speed: p.window.speed },
    reference: { notes: p.reference.notes.map(n => ({ time: n.time, duration: n.duration, midi: n.midi })), bpm: p.reference.bpm, tuning: p.reference.tuning, part: p.reference.part, revision: p.reference.revision, reviewed: p.reference.reviewed }, audio: p.audio };
}
export async function packetDigest(p: ListeningPacket) {
  const bytes = new TextEncoder().encode(JSON.stringify(core(p)));
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}
export async function makeListeningPacket(project: PracticeProject, attempt: Attempt): Promise<ListeningPacket> {
  if (!attempt.audio || attempt.revision !== project.revision) throw Error('Retained take audio and its unchanged reference revision are required.');
  const packet: ListeningPacket = {
    schema: 'fretwork-listening-packet-v1', id: crypto.randomUUID(), window: { start: attempt.start, end: attempt.end, speed: attempt.speed },
    reference: { notes: phraseNotes(project, { id: '', name: '', start: attempt.start, end: attempt.end }, attempt.speed), bpm: project.bpm * attempt.speed, tuning: project.tuning, part: project.part, revision: project.revision, reviewed: project.trust === 'reviewed' },
    audio: await blobData(attempt.audio), sha256: '',
  };
  if (packet.reference.notes.length > 5000) throw Error('Listening packets support up to 5,000 notes. Choose a shorter phrase.');
  packet.sha256 = await packetDigest(packet); return validateListeningPacket(packet);
}
/** Whitelist-only packet: deliberately cannot carry predictions, grades or prior annotations. */
export async function validateListeningPacket(value: unknown): Promise<ListeningPacket> {
  const p = value as ListeningPacket;
  const keys = (v: unknown, allowed: string[]) => !!v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).every(k => allowed.includes(k));
  const num = (v: unknown, min: number, max: number) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
  const text = (v: unknown, max: number) => typeof v === 'string' && v.length <= max;
  const fail = () => { throw Error('Invalid listening-only packet or unexpected prediction fields.'); };
  if (!keys(p, ['schema','id','window','reference','audio','sha256']) || p.schema !== 'fretwork-listening-packet-v1' || !text(p.id, 100) || !p.id || !keys(p.window, ['start','end','speed']) || !keys(p.reference, ['notes','bpm','tuning','part','revision','reviewed'])) fail();
  if (!num(p.window.start, 0, 600) || !num(p.window.end, p.window.start + .1, 600) || !num(p.window.speed, .5, 1) || (p.window.end - p.window.start) / p.window.speed > 120.01) fail();
  const seconds = (p.window.end - p.window.start) / p.window.speed;
  const r = p.reference;
  if (!text(r.tuning, 500) || !text(r.part, 500) || !num(r.bpm, 10, 400) || !Number.isInteger(r.revision) || r.revision < 1 || r.revision > 100000 || typeof r.reviewed !== 'boolean' || !Array.isArray(r.notes) || r.notes.length > 5000) fail();
  for (const n of r.notes) if (!keys(n, ['time','duration','midi']) || !num(n.time, 0, seconds) || !num(n.duration, 1e-9, seconds + .01) || n.time + n.duration > seconds + .01 || !Number.isInteger(n.midi) || !num(n.midi, 0, 127)) fail();
  if (!text(p.sha256, 64) || !/^[0-9a-f]{64}$/.test(p.sha256)) fail();
  const audio = decodeAttachment(p.audio, 'audio/wav', 30 * 1024 * 1024);
  if (audio.size < 44) fail();
  const header = new Uint8Array(await audio.slice(0, 12).arrayBuffer());
  if (String.fromCharCode(...header.slice(0, 4)) !== 'RIFF' || String.fromCharCode(...header.slice(8, 12)) !== 'WAVE') throw Error('Packet recording must be a WAV file.');
  if (await packetDigest(p) !== p.sha256) throw Error('Packet checksum mismatch. Request a fresh export. Checksums detect changes, not authenticity.');
  return { ...core(p), sha256: p.sha256 };
}
export function validateLabels(labels: ListeningLabel[], seconds: number) {
  return Array.isArray(labels) && labels.length <= 1000 && labels.every(l => l && Number.isFinite(l.start) && Number.isFinite(l.end) && l.start >= 0 && l.end >= l.start && l.end <= seconds + .01 && labelKinds.includes(l.kind) && typeof l.comment === 'string' && l.comment.length <= 1000);
}
export function listeningResult(packet: ListeningPacket, reviewer: string, exposure: string, labels: ListeningLabel[], complete: boolean) {
  if (typeof reviewer !== 'string' || !reviewer.trim() || reviewer.length > 200 || !['no','yes','unsure'].includes(exposure) || !validateLabels(labels, (packet.window.end - packet.window.start) / packet.window.speed)) throw Error('Reviewer pseudonym, exposure declaration and valid annotation times are required.');
  return { schema: 'fretwork-listening-labels-v1', packet_id: packet.id, packet_sha256: packet.sha256, created: Date.now(), reviewer: reviewer.trim(), seen_app_predictions: exposure, reviewed_whole_take: complete,
    independent_ground_truth: false, protocol: 'listening-only; self-declared reviewer exposure; external audit required', labels: labels.map(l => ({ start: l.start, end: l.end, kind: l.kind, comment: l.comment })) };
}
