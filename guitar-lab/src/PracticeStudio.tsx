import { useEffect, useRef, useState } from 'react';
import { shownReport, type DiffNote } from './compare';
import { compareTake } from './songApi';
import { encodeWav } from './engineApi';
import { Recorder } from './recorder';
import { synthesize } from './tabScore';
import { addClicks, loadLatency } from './practice';
import LatencyCheck from './LatencyCheck';
import { useTranscriber } from './TranscriberSelect';
import { MEDIA_ACCEPT } from './audioFiles';
import { comparable, confirmedCount, exportProject, importProject, issueKey, issueStatus, newProject, validateProject, excludedPhrase, exercise, phraseNotes, projectStore, type Attempt, type PracticeProject, type PracticeSeed, type Review, type Section } from './practiceProject';

type Props = { seed: PracticeSeed | null };
export default function PracticeStudio({ seed }: Props) {
  const [project, setProject] = useState<PracticeProject | null>(null);
  const [library, setLibrary] = useState<PracticeProject[]>([]);
  const [sectionId, setSectionId] = useState('');
  const [speed, setSpeed] = useState(.7);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [loop, setLoop] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [retain, setRetain] = useState(false);
  const [latency, setLatency] = useState(loadLatency);
  const [transcriber] = useTranscriber();
  const [editor, setEditor] = useState('');
  const [manualStart, setManualStart] = useState(0);
  const ctx = useRef<AudioContext | null>(null);
  const rec = useRef<Recorder | null>(null);
  const sources = useRef<AudioBufferSourceNode[]>([]);
  const mounted = useRef(true);
  const context = () => ctx.current ?? (ctx.current = new AudioContext({ latencyHint: 'interactive' }));
  const recorder = () => rec.current ?? (rec.current = new Recorder(context()));
  const stop = () => { sources.current.forEach(s => { try { s.stop(); } catch {} }); sources.current = []; };
  useEffect(() => { projectStore('list').then(setLibrary).catch(e => setError(String(e))); return () => { mounted.current = false; stop(); rec.current?.stop(); rec.current?.release(); ctx.current?.close(); }; }, []);
  useEffect(() => { if (seed) { stop(); rec.current?.stop(); setProject(newProject(seed)); setSelected(''); setSectionId(''); setNotice('New project is unsaved. Review the reference before grading.'); document.getElementById('practice-studio')?.scrollIntoView({ behavior: 'smooth' }); } }, [seed]);
  useEffect(() => { if (project) { setSpeed(project.practiceSpeed); setSectionId(project.activeSection); } }, [project?.id]);
  const section = project?.sections.find(s => s.id === sectionId) ?? project?.sections[0];
  const attempt = project?.attempts.find(a => a.id === selected) ?? project?.attempts.at(-1);
  const report = attempt?.comparison && shownReport(attempt.comparison);
  const issues = report?.notes.filter(n => n.kind !== 'correct') ?? [];
  const excluded = !!(project && section && excludedPhrase(project, section));
  const activeSection = section && section.end > section.start && section.end - section.start <= 60;
  const patch = (values: Partial<PracticeProject>) => setProject(p => p && p.id === project?.id ? { ...p, ...values, updated: Date.now() } : p);
  function changeSection(values: Partial<Section>) {
    if (!project || !section) return;
    patch({ sections: project.sections.map(s => s.id === section.id ? { ...s, ...values } : s) });
  }
  async function run(fn: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { if (mounted.current) { setBusy(false); setRecording(false); } }
  }
  function playBuffer(buffer: AudioBuffer, at = context().currentTime + .05, offset = 0, duration = buffer.duration - offset) {
    if (duration <= 0 || offset >= buffer.duration) return;
    const s = context().createBufferSource(); s.buffer = buffer; s.connect(context().destination);
    s.start(at, Math.max(0, offset), Math.max(.01, Math.min(duration, buffer.duration - offset))); sources.current.push(s);
  }
  function expected(p: PracticeProject, s: Section, sp: number) {
    const c = context(); const data = synthesize(phraseNotes(p, s, sp), c.sampleRate, (s.end - s.start) / sp, 1, .25);
    const b = c.createBuffer(1, data.length, c.sampleRate); b.copyToChannel(data, 0); return b;
  }
  async function listen(mode: 'expected' | 'take' | 'both' | 'sequence', n?: DiffNote) {
    if (!project || !section) return;
    await context().resume(); stop();
    const s = attempt ? { id: '', name: '', start: attempt.start, end: attempt.end } : section;
    const sp = attempt?.speed ?? speed;
    const ref = expected(project, s, sp);
    const take = attempt?.audio ? await context().decodeAudioData(await attempt.audio.arrayBuffer()) : null;
    const start = Math.max(0, (n?.target_time ?? n?.take_time ?? 1) - 1);
    const takeStart = Math.max(0, (n?.take_time ?? n?.target_time ?? 1) - 1);
    const length = n ? 3 : ref.duration;
    const at = context().currentTime + .05;
    if (mode !== 'take') playBuffer(ref, at, n ? start : 0, length);
    if (take && mode !== 'expected') playBuffer(take, mode === 'sequence' ? at + Math.min(length, ref.duration - start) + .5 : at, n ? takeStart : 0, length);
    if (!take && mode !== 'expected') setNotice('No retained audio for this take. Enable recording retention before the next take.');
  }
  async function analyse(audio: Blob, s: Section, sp: number, measured: boolean) {
    if (!project) return;
    if (project.attempts.length >= 50) throw Error('Project has 50 takes. Delete an older take before adding another.');
    if (retain && audio.size + project.attempts.reduce((sum, a) => sum + (a.audio?.size ?? 0), 0) > 50 * 1024 * 1024) throw Error('Retained audio exceeds 50 MB. Remove old take audio or turn off retention.');
    const a: Attempt = { id: crypto.randomUUID(), created: Date.now(), revision: project.revision, start: s.start, end: s.end, speed: sp, reviews: {}, latencyMeasured: measured, audio: retain ? audio : undefined };
    if (project.trust === 'reviewed' && !excludedPhrase(project, s)) {
      const notes = phraseNotes(project, s, sp);
      if (!notes.length) throw Error('No reference notes in this phrase. Correct the reference or choose another phrase.');
      a.comparison = await compareTake({ take: audio, transcriber, targets: [{ source: 'file', label: `${project.title} · ${s.name}`, notes, bpm: project.bpm * sp }] });
    }
    if (!mounted.current) return;
    patch({ attempts: [...project.attempts, a].slice(-50) }); setSelected(a.id);
    setNotice(a.comparison ? 'Review the findings by ear, then practise one phrase and retry. Save project to keep this take.' : 'Take captured without a grade: reference unreviewed or phrase excluded.');
  }
  async function record() {
    if (!project || !section || !activeSection) return;
    await run(async () => {
      stop(); const c = context(); await c.resume(); await recorder().ensure();
      const ref = expected(project, section, speed), beat = 60 / project.bpm / speed, count = beat * 4;
      const clicks = c.createBuffer(1, Math.ceil((count + ref.duration) * c.sampleRate), c.sampleRate);
      addClicks([clicks.getChannelData(0)], c.sampleRate, Array.from({ length: Math.ceil((count + ref.duration) / beat) }, (_, i) => ({ time: i * beat, accent: i % 4 === 0 })), 0);
      const captureAt = c.currentTime, at = captureAt + .15;
      setRecording(true); playBuffer(clicks, at); playBuffer(ref, at + count);
      const raw = await recorder().capture(Math.ceil((.15 + count + ref.duration + .3) * c.sampleRate), count + ref.duration + 5);
      stop(); setRecording(false); recorder().release();
      const lead = Math.round((at + count - captureAt + recorder().delay(latency)) * c.sampleRate);
      const take = raw.slice(lead, lead + Math.round(ref.duration * c.sampleRate));
      if (take.length < Math.round(ref.duration * c.sampleRate) * .95) throw Error('Recording stopped before the phrase. No take was graded.');
      await analyse(encodeWav([take], c.sampleRate), section, speed, !!latency?.ok);
    });
    rec.current?.release();
  }
  function review(key: string, value: Review) {
    if (!project || !attempt) return;
    patch({ attempts: project.attempts.map(a => a.id === attempt.id ? { ...a, reviews: { ...a.reviews, [key]: value } } : a) });
  }
  function practise(n: DiffNote) {
    if (!attempt || !project) return;
    const time = attempt.start + (n.target_time ?? n.take_time ?? 0) * attempt.speed;
    const start = Math.max(attempt.start, time - 1.5), end = Math.min(attempt.end, time + 3);
    const s = { id: crypto.randomUUID(), name: `Focus: ${n.kind.replaceAll('_', ' ')}`, start, end };
    if (project.sections.length >= 100) { setError('Delete a section before adding another.'); return; }
    patch({ sections: [...project.sections, s], goal: n.message }); setSectionId(s.id); setSpeed(Math.min(attempt.speed, .7)); setSelected('');
    setNotice('Focus phrase ready. Listen, then record a new attempt with the four-beat count-in.');
  }
  async function download(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const suggestions = !report?.alignment_warning && project?.trust === 'reviewed' && attempt?.revision === project.revision ? issues.filter(n => !['dismissed', 'unsure'].includes(attempt.reviews[issueKey(n)]) && ['wrong_pitch', 'missing', 'extra', ...(attempt.latencyMeasured ? ['early','late'] : [])].includes(n.kind)).sort((a,b) => Number(attempt.reviews[issueKey(b)] === 'confirmed') - Number(attempt.reviews[issueKey(a)] === 'confirmed')).slice(0, 2) : [];
  const previous = project && attempt ? project.attempts.filter(a => a.created < attempt.created && comparable(a, attempt)).at(-1) : undefined;
  return <section className="panel practice-studio" id="practice-studio" aria-labelledby="practice-title">
    <h2 id="practice-title">Review → Practise → Retry</h2>
    <p>Choose a chart or generated tab above and send it here. Review the reference, focus on one phrase, then listen and retry. Projects stay on this device only when you explicitly save.</p>
    <div className="presets">
      <select aria-label="Saved practice projects" disabled={busy} value="" onChange={e => { const p = library.find(p => p.id === e.target.value); if (p) { stop(); setProject(p); setSelected(''); setSectionId(''); setNotice('Saved reference and takes restored.'); } }}>
        <option value="">Open saved project…</option>{library.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
      </select>
      <label>Import project <input type="file" accept=".json" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) run(async () => { setProject(await importProject(f)); setSelected(''); setSectionId(''); setNotice('Imported as an unsaved copy.'); }); e.target.value = ''; }} /></label>
    </div>
    {error && <p className="error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    {project && section && <fieldset disabled={busy} className="practice-fields">
      <legend>{project.title} · {project.part}</legend>
      <label>Project title <input value={project.title} maxLength={500} onChange={e => patch({ title: e.target.value })} /></label>
      <p className="helper">{project.origin === 'chart' ? 'Imported chart' : 'Generated transcription'} · {project.tuning} · capo {project.capo} · reference revision {project.revision}. Imported charts also need checking for the right arrangement and tuning.</p>
      <label>Practice goal <input value={project.goal} maxLength={2000} onChange={e => patch({ goal: e.target.value })} /></label>
      <p><b>Before judging your playing:</b> confirm the correct song passage, rhythm/lead part and tuning. Listen to the original in Song Lab and compare the written notes. No detected disagreement is not proof of accuracy.</p>
      <label><input type="checkbox" checked={project.trust === 'reviewed'} onChange={e => patch({ trust: e.target.checked ? 'reviewed' : 'unverified' })} /> I reviewed this reference and arrangement; allow diagnostic comparison</label>
      <details><summary>Correct reference notes / chord tones</summary>
        <p>Edit JSON rows with time (seconds), duration and MIDI pitch. A chord is several notes at the same time. Saving creates a new revision, clears reference approval and keeps old takes separate.</p>
        <button type="button" onClick={() => setEditor(JSON.stringify(project.notes, null, 2))}>Load notes into editor</button>
        <textarea aria-label="Reference note editor" rows={8} value={editor} onChange={e => setEditor(e.target.value)} />
        <button type="button" onClick={() => run(async () => { const next = validateProject({ ...project, notes: JSON.parse(editor), revision: project.revision + 1, trust: 'unverified' }); setProject(next); setSelected(''); setNotice('Reference corrected. Review and approve the new revision before grading.'); })}>Apply reference corrections</button>
      </details>
      <div className="presets">
        <select aria-label="Song section" value={section.id} onChange={e => setSectionId(e.target.value)}>{project.sections.map(s => <option key={s.id} value={s.id}>{s.name} ({s.start.toFixed(1)}–{s.end.toFixed(1)}s)</option>)}</select>
        <button type="button" disabled={project.sections.length >= 100} onClick={() => { const s = { id: crypto.randomUUID(), name: 'Chorus', start: 0, end: Math.min(20, project.duration) }; patch({ sections: [...project.sections, s] }); setSectionId(s.id); }}>Add section</button>
        <button type="button" disabled={project.sections.length === 1} onClick={() => { patch({ sections: project.sections.filter(s => s.id !== section.id), ignored: project.ignored.filter(id => id !== section.id) }); setSectionId(''); }}>Delete section</button>
      </div>
      <label>Section name <input value={section.name} maxLength={500} onChange={e => changeSection({ name: e.target.value })} /></label>
      <label>From seconds <input type="number" min={0} max={section.end - .1} step={.1} value={section.start} onChange={e => changeSection({ start: Math.max(0, Math.min(section.end - .1, Number(e.target.value))) })} /></label>
      <label>To seconds <input type="number" min={section.start + .1} max={project.duration} step={.1} value={section.end} onChange={e => changeSection({ end: Math.max(section.start + .1, Math.min(project.duration, Number(e.target.value))) })} /></label>
      <label><input type="checkbox" checked={project.ignored.includes(section.id)} onChange={e => patch({ ignored: e.target.checked ? [...project.ignored, section.id] : project.ignored.filter(id => id !== section.id) })} /> Reference unreliable here — exclude this phrase from grading</label>
      {excluded && <p>Grading disabled: this phrase overlaps an excluded region. Uncheck the exclusion on the original section to re-enable.</p>}
      <label>Practice speed <select value={speed} onChange={e => setSpeed(Number(e.target.value))}>{[.5,.6,.7,.75,.8,.9,1].map(s => <option key={s} value={s}>{Math.round(s * 100)}%</option>)}</select></label>
      {!activeSection && <p role="alert">Choose a phrase between 0.1 and 60 seconds.</p>}
      <label><input type="checkbox" checked={retain} onChange={e => setRetain(e.target.checked)} /> Keep new take audio in this project (off by default). Saved/exported projects will include it.</label>
      <LatencyCheck recorder={recorder} latency={latency} disabled={busy} onBefore={stop} onMeasured={setLatency} />
      <label><input type="checkbox" checked={loop} onChange={e => setLoop(e.target.checked)} /> Loop phrase when listening (stop playback below)</label>
      <button type="button" onClick={stop}>Stop phrase playback</button>
      <div className="presets">
        <button type="button" disabled={!activeSection} onClick={() => run(async () => { await context().resume(); stop(); const b = expected(project, section, speed); if (loop) { const s = context().createBufferSource(); s.buffer = b; s.loop = true; s.connect(context().destination); s.start(); sources.current.push(s); } else playBuffer(b); })}>Hear practice phrase</button>
        <button type="button" disabled={!activeSection || project.attempts.length >= 50} onClick={record}>Count in, practise & record</button>
      </div>
      <p className="helper">Use headphones. Your take is sent to the configured Python engine for analysis, not to cloud storage. The plain guitar guide is not the original tone. Maximum 50 takes and 50 MB of retained audio per project.</p>
      <details><summary>Upload an earlier phrase recording</summary>
        <p>Fallback when automatic song location is unclear: set its original-song start timestamp and the speed you played. Audio must begin at the phrase (trim count-in first); duration determines the end.</p>
        <label>Reference start (seconds) <input type="number" min={0} max={project.duration} value={manualStart} onChange={e => setManualStart(Number(e.target.value))} /></label>
        <input aria-label="Upload phrase take" type="file" accept={MEDIA_ACCEPT} onChange={e => { const f = e.target.files?.[0]; if (f) run(async () => { if (f.size > 30 * 1024 * 1024) throw Error('Choose audio smaller than 30 MB.'); const b = await context().decodeAudioData(await f.arrayBuffer()); if (b.duration > 120 || b.duration < .2 || manualStart < 0 || manualStart + b.duration * speed > project.duration + .05) throw Error('Recording must fit the reference and be at most 120 seconds.'); await analyse(encodeWav(Array.from({ length: b.numberOfChannels }, (_, i) => b.getChannelData(i)), b.sampleRate), { ...section, start: manualStart, end: Math.min(project.duration, manualStart + b.duration * speed) }, speed, false); }); e.target.value = ''; }} />
      </details>
      <div className="presets">
        <button type="button" onClick={() => run(async () => { const saved = { ...project, practiceSpeed: speed, activeSection: section.id }; await projectStore('put', saved); setLibrary(await projectStore('list')); setNotice('Saved on this device. Export a backup before clearing browser data.'); })}>Save project on this device</button>
        <button type="button" onClick={() => run(async () => download(await exportProject({ ...project, practiceSpeed: speed, activeSection: section.id }), `${project.title}.practice.json`))}>Export project & takes</button>
        <button type="button" onClick={() => run(async () => { if (!confirm('Delete this saved project and its retained recordings from this device? Exported copies are not deleted.')) return; await projectStore('delete', project.id); setLibrary(await projectStore('list')); setProject(null); })}>Delete project</button>
      </div>
      <p className="helper">Projects preserve the editable reference notes, not the original song/stems or the complete chart file. Keep your original files separately. Changes are not autosaved. Browser storage may be evicted; keep an export. Delete removes the local saved project, not previously downloaded copies or temporary engine files.</p>
    </fieldset>}
    {recording && <button className="primary" onClick={() => { recorder().stop(); stop(); }}>Stop recording</button>}
    {busy && <p role="status">{recording ? 'Count-in / recording…' : 'Working…'}</p>}
    {project && attempt && <div className="practice-review">
      <h3>Review this take</h3>
      <select aria-label="Practice takes" disabled={busy} value={attempt.id} onChange={e => { stop(); setSelected(e.target.value); }}>{project.attempts.map((a, i) => <option key={a.id} value={a.id}>Take {i + 1} · {Math.round(a.speed * 100)}% · {a.start.toFixed(1)}–{a.end.toFixed(1)}s · rev {a.revision}</option>)}</select>
      {attempt.revision !== project.revision ? <p>Reference changed. This is a historical report; retry using the current revision. Expected-audio comparisons are disabled.</p> : <div className="presets">{(['expected','take','both','sequence'] as const).map(m => <button disabled={busy} key={m} onClick={() => run(() => listen(m))}>{m === 'sequence' ? 'Expected → your take' : m === 'expected' ? 'Expected' : m === 'take' ? 'Your take' : 'Both'}</button>)}</div>}
      <button onClick={stop}>Stop playback</button>
      <button disabled={busy || !attempt.audio} onClick={() => { patch({ attempts: project.attempts.map(a => a.id === attempt.id ? { ...a, audio: undefined } : a) }); setNotice('Audio removed from working project. Save to remove it from the stored copy.'); }}>Remove this take’s audio</button>
      <button disabled={busy} onClick={() => { patch({ attempts: project.attempts.filter(a => a.id !== attempt.id) }); setSelected(''); }}>Delete take</button>
      <p>Findings are diagnostic candidates, not confirmed mistakes. {attempt.latencyMeasured ? 'Device delay was measured.' : 'Device delay was not independently calibrated for this take.'} Sustain, distortion, separation and alignment can cause errors.</p>
      {report?.alignment_warning && <p role="alert">{report.alignment_warning} Findings may reflect alignment rather than your playing. Check the timestamp and reference passage.</p>}
      {report && !issues.length && <p>No issues detected in the aligned notes. This does not verify every note or technique.</p>}
      {issues.length > 0 && <p><b>Next action:</b> listen to a pitch or timing candidate below, confirm whether it is audible, then choose “Practise this phrase”. Work on one change at a time. Dismissed findings are never recommended.</p>}
      {suggestions.length > 0 && <div aria-label="Suggested focus phrases"><h4>Start with one of these</h4><p>Human-confirmed findings come first. Other suggestions still need a listening check.</p>{suggestions.map(n => <div key={issueKey(n)}><p>{n.message}</p><p>{exercise(n.kind)}</p><button disabled={busy} onClick={() => practise(n)}>Focus on {n.kind.replaceAll('_', ' ')} at bar {n.bar}</button></div>)}</div>}
      <ol className="practice-issues">{[...issues].sort((a,b) => Number(attempt.reviews[issueKey(b)] === 'confirmed') - Number(attempt.reviews[issueKey(a)] === 'confirmed')).slice(0, 100).map(n => <li key={issueKey(n)}>
        <b>{report?.alignment_warning ? 'Alignment unclear — review by ear' : issueStatus(n, project.trust, attempt.latencyMeasured)}</b><p>{n.message}</p><p className="helper">{exercise(n.kind)}</p>
        <div className="presets">
          <button disabled={busy || attempt.revision !== project.revision} onClick={() => run(() => listen('sequence', n))}>Hear expected → yours here</button>
          <button disabled={busy || attempt.revision !== project.revision} onClick={() => run(() => listen('both', n))}>Hear both here</button>
          <button disabled={busy || attempt.revision !== project.revision || attempt.reviews[issueKey(n)] === 'dismissed'} onClick={() => practise(n)}>Practise this phrase</button>
          <select aria-label={`Review finding ${n.id}`} disabled={busy} value={attempt.reviews[issueKey(n)] ?? ''} onChange={e => review(issueKey(n), e.target.value as Review)}><option value="" disabled>My review…</option><option value="confirmed">Yes, audible playing issue</option><option value="dismissed">No, incorrect warning</option><option value="unsure">Unsure / reference unclear</option></select>
        </div>
      </li>)}</ol>
      {issues.length > 100 && <p>Showing the first 100 findings. Choose a shorter phrase to review the rest.</p>}
      <h3>Retry progress</h3>
      <p>{previous ? `Same phrase, speed and reference revision: ${confirmedCount(previous)} → ${confirmedCount(attempt)} human-confirmed issues (review coverage: ${Object.keys(previous.reviews).length} → ${Object.keys(attempt.reviews).length} findings). Only compare after reviewing both takes; fewer unreviewed flags does not prove improvement.` : 'No earlier take at this exact phrase, speed and reference revision. Record another to compare like for like.'}</p>
      {previous?.audio && attempt.audio && <button disabled={busy} onClick={() => run(async () => {
        await context().resume(); stop();
        const before = await context().decodeAudioData(await previous.audio!.arrayBuffer());
        const after = await context().decodeAudioData(await attempt.audio!.arrayBuffer());
        const at = context().currentTime + .05; playBuffer(before, at); playBuffer(after, at + before.duration + .5);
      })}>Hear previous take → this take</button>}
      <button disabled={busy || attempt.revision !== project.revision || project.sections.length >= 100} onClick={() => { const s = { id: crypto.randomUUID(), name: 'Retry same phrase', start: attempt.start, end: attempt.end }; patch({ sections: [...project.sections, s] }); setSectionId(s.id); setSpeed(attempt.speed); setNotice('Same phrase and speed selected. Use count in, practise & record above.'); }}>Retry same phrase & speed</button>
      <details><summary>Human validation: was this useful?</summary>
        <p>These are your review labels, not independent ground truth. Export them for a teacher/reviewer to check. No accuracy claim is calculated from unreviewed recordings.</p>
        {([['audible','Were the highlighted issues audible?'],['useful','Did the suggested exercise address them?'],['improved','Did the retry sound better?']] as const).map(([key,label]) => <label key={key}>{label}<select disabled={busy} value={attempt[key] ?? ''} onChange={e => patch({ attempts: project.attempts.map(a => a.id === attempt.id ? { ...a, [key]: e.target.value } : a) })}><option value="" disabled>Not reviewed</option><option value="yes">Yes</option><option value="no">No</option><option value="unsure">Unsure</option></select></label>)}
        <button onClick={() => download(new Blob([JSON.stringify({ schema: 'fretwork-human-review-v1', independent_ground_truth: false, project: { title: project.title, origin: project.origin, tuning: project.tuning, part: project.part }, attempts: project.attempts.map(({ audio, ...a }) => a) }, null, 2)], { type: 'application/json' }), 'practice-human-review.json')}>Export review labels (no audio)</button>
      </details>
    </div>}
  </section>;
}
