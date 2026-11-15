import { useEffect, useRef, useState } from 'react';
import { decodeAttachment } from './practiceProject';
import { labelKinds, listeningResult, validateListeningPacket, type ListeningPacket, type ListeningLabel } from './listeningReview';
import { synthesize } from './tabScore';
import { encodeWav } from './engineApi';

/** Separate entry point. No model requests, predictions, project library or automatic grades. */
export default function ListeningReviewer() {
  const [packet, setPacket] = useState<ListeningPacket | null>(null);
  const [urls, setUrls] = useState<{ take: string; guide: string } | null>(null);
  const [reviewer, setReviewer] = useState('');
  const [exposure, setExposure] = useState('');
  const [complete, setComplete] = useState(false);
  const [labels, setLabels] = useState<ListeningLabel[]>([]);
  const [start, setStart] = useState(0), [end, setEnd] = useState(0);
  const [kind, setKind] = useState<ListeningLabel['kind']>('uncertain');
  const [comment, setComment] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const audio = useRef<HTMLAudioElement>(null), guide = useRef<HTMLAudioElement>(null);
  const loadToken = useRef(0);
  const seconds = packet ? (packet.window.end - packet.window.start) / packet.window.speed : 0;
  useEffect(() => () => { if (urls) { URL.revokeObjectURL(urls.take); URL.revokeObjectURL(urls.guide); } }, [urls]);
  useEffect(() => () => { loadToken.current++; }, []);
  function download(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function load(file: File) {
    const token = ++loadToken.current; setError(''); setNotice(''); setBusy(true);
    try {
      if (file.size > 45 * 1024 * 1024) throw Error('Listening packet exceeds 45 MB.');
      const p = await validateListeningPacket(JSON.parse(await file.text()));
      if (token !== loadToken.current) return;
      const duration = (p.window.end - p.window.start) / p.window.speed;
      const take = decodeAttachment(p.audio, 'audio/wav', 30 * 1024 * 1024);
      const samples = synthesize(p.reference.notes, 22050, duration, 1, .25);
      audio.current?.pause(); guide.current?.pause();
      setUrls({ take: URL.createObjectURL(take), guide: URL.createObjectURL(encodeWav([samples], 22050)) });
      setPacket(p); setLabels([]); setReviewer(''); setExposure(''); setComplete(false); setStart(0); setEnd(0); setComment('');
      setNotice('Checksum verified. No app predictions or prior annotations were included.');
    } catch (e) { if (token === loadToken.current) setError(String(e)); }
    finally { if (token === loadToken.current) setBusy(false); }
  }
  return <main className="panel listening-reviewer" style={{ maxWidth: 1000, margin: '2rem auto', padding: '1.5rem' }}>
    <h1>Listening-only guitar review</h1>
    <p>Annotate what you hear before looking at app findings. This page does not run transcription, display predictions, or assign grades. Data stays in this browser unless you explicitly download/share it.</p>
    <p>Use a reviewer who has not seen the app results when possible. A checksum binds the notes and audio to the packet; it does not establish authenticity, expertise or independent ground truth.</p>
    <label>Open listening packet <input type="file" accept=".json" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f && (!labels.length || confirm('Opening another packet discards unsaved review labels. Export them first. Continue?'))) load(f); e.target.value = ''; }} /></label>
    {busy && <p role="status">Checking packet…</p>}{error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {packet && urls && <>
      <p>{packet.reference.part} · {packet.reference.tuning} · reference revision {packet.reference.revision} · {Math.round(packet.window.speed * 100)}% speed · {seconds.toFixed(2)} seconds.</p>
      <p>{packet.reference.reviewed ? 'The sender declared this reference reviewed; that is not independent verification.' : 'The sender did not approve this reference. Treat disagreements as reference uncertainty, not necessarily player faults.'} The guide is synthesized from the supplied notes and may itself be wrong; it is not original-song audio.</p>
      <h2>Listen</h2>
      <label>Recorded take <audio ref={audio} controls preload="metadata" src={urls.take} onError={() => setError("The take could not be decoded. Ask the sender to re-export a valid recording.")} onPlay={() => guide.current?.pause()} /></label>
      <label>Reference-note guide <audio ref={guide} controls preload="metadata" src={urls.guide} onPlay={() => audio.current?.pause()} /></label>
      <p>All label times are seconds from the beginning of this take, not the original-song clock. “Correct region” marks listening coverage with no audible issue; empty labels do not imply correct playing.</p>
      <fieldset disabled={busy}>
        <legend>Reviewer declaration</legend>
        <label>Reviewer pseudonym <input maxLength={200} value={reviewer} onChange={e => setReviewer(e.target.value)} /></label>
        <label>Have you seen app predictions for this take? <select value={exposure} onChange={e => setExposure(e.target.value)}><option value="" disabled>Declare exposure…</option><option value="no">No</option><option value="yes">Yes</option><option value="unsure">Unsure</option></select></label>
        <label><input type="checkbox" checked={complete} onChange={e => setComplete(e.target.checked)} /> I listened through the whole take</label>
      </fieldset>
      <fieldset disabled={busy}>
        <legend>Add an audible observation</legend>
        <label>Observation start seconds <input type="number" min={0} max={seconds} step={.01} value={start} onChange={e => setStart(Number(e.target.value))} /></label>
        <button onClick={() => setStart(Math.min(seconds, audio.current?.currentTime ?? 0))}>Set start from take playhead</button>
        <label>Observation end seconds <input type="number" min={0} max={seconds} step={.01} value={end} onChange={e => setEnd(Number(e.target.value))} /></label>
        <button onClick={() => setEnd(Math.min(seconds, audio.current?.currentTime ?? 0))}>Set end from take playhead</button>
        <label>Observation type <select value={kind} onChange={e => setKind(e.target.value as ListeningLabel['kind'])}>{labelKinds.map(k => <option key={k} value={k}>{k === 'correct' ? 'Correct region (no audible issue)' : k}</option>)}</select></label>
        <label>Observation comment <textarea maxLength={1000} value={comment} onChange={e => setComment(e.target.value)} placeholder="Describe the audible issue or why you are unsure; expected vs heard if identifiable." /></label>
        <button disabled={labels.length >= 1000} onClick={() => {
          try { listeningResult(packet, reviewer, exposure, [...labels, { start, end, kind, comment }], complete); setLabels([...labels, { start, end, kind, comment }]); setComment(''); setError(''); }
          catch (e) { setError(String(e)); }
        }}>Add listening observation</button>
      </fieldset>
      <ol aria-label="Listening observations">{labels.map((l, i) => <li key={i}><b>{l.start.toFixed(2)}–{l.end.toFixed(2)}s · {l.kind}</b><p>{l.comment}</p>
        <button onClick={() => { if (audio.current) { guide.current?.pause(); audio.current.currentTime = l.start; audio.current.play().catch(e => setError(String(e))); } }}>Listen from observation {i + 1}</button>
        <button onClick={() => setLabels(labels.filter((_, j) => j !== i))}>Remove observation {i + 1}</button>
      </li>)}</ol>
      <button disabled={busy} onClick={() => {
        try { const result = listeningResult(packet, reviewer, exposure, labels, complete); download(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }), 'listening-review-labels.json'); setNotice('Labels exported with packet checksum and self-declared exposure. Independent ground truth remains false pending an external audit.'); }
        catch (e) { setError(String(e)); }
      }}>Export listening labels</button>
      <label>Restore exported labels <input type="file" accept=".json" onChange={async e => {
        const f = e.target.files?.[0]; e.target.value = ''; if (!f) return; const token = loadToken.current;
        try {
          if (f.size > 3 * 1024 * 1024) throw Error('Labels exceed 3 MB.');
          const value = JSON.parse(await f.text());
          if (value.schema !== 'fretwork-listening-labels-v1' || value.packet_id !== packet.id || value.packet_sha256 !== packet.sha256 || typeof value.reviewed_whole_take !== 'boolean') throw Error('Labels do not match this packet.');
          if (token !== loadToken.current) return;
          const checked = listeningResult(packet, value.reviewer, value.seen_app_predictions, value.labels, value.reviewed_whole_take);
          if (labels.length && !confirm('Replace current labels with this saved review?')) return;
          setReviewer(checked.reviewer); setExposure(checked.seen_app_predictions); setComplete(checked.reviewed_whole_take); setLabels(checked.labels); setNotice('Saved review labels restored.'); setError('');
        } catch (e) { setError(String(e)); }
      }} /></label>
      <p>No autosave: export labels before closing. Packets contain private recordings; share only with permission. This page intentionally does not reveal or match predictions after review, avoiding accidental leakage to the next reviewer.</p>
    </>}
    <p><a href="./">Return to guitar practice</a></p>
  </main>;
}
