import { useEffect, useRef, useState } from "react";
import {
  Check,
  CloudUpload,
  RefreshCw,
  Trash2,
  Save,
  Plus,
} from "lucide-react";
import {
  api,
  excerpt,
  type Job,
  type Health,
  type EngineNote,
} from "./engineApi";
import { fingering, note } from "./analysis";
import ModelInstaller from "./ModelInstaller";
import { summarise, type BarMark } from "./feedback";
import type { Processing } from "./ProcessingToggle";
import { tabPosition, type ResolvedInstrument } from "./instruments";

type Props = {
  reference: { name: string; buffer: AudioBuffer } | null;
  take: { name: string; buffer: AudioBuffer } | null;
  kind: string;
  start: number;
  length: number;
  recording: boolean;
  profile: ResolvedInstrument;
  /** Bar starts within the compared passage, when it came from a song breakdown. */
  bars?: BarMark[];
  /** Exact reference notes when the reference is the app's rendering of an uploaded tab. */
  referenceNotes?: { time: number; duration: number; midi: number; string?: number | null; fret?: number | null }[];
  processing?: Processing;
};
const pending = ["queued", "separating", "analysing"];
function withTab(n: EngineNote, profile: ResolvedInstrument): EngineNote {
  const position = tabPosition(n.midi, profile);
  return {
    ...n,
    string: profile.openStrings.length
      ? (n.string ?? position?.string ?? null)
      : null,
    fret: profile.openStrings.length
      ? (n.fret ?? position?.fret ?? null)
      : null,
  };
}

export default function EngineSession({
  reference,
  take,
  kind,
  start,
  length,
  recording,
  profile,
  bars,
  referenceNotes,
  processing = "cpu",
}: Props) {
  const tuning = profile.openStrings,
    showTab = tuning.length > 0 && profile.settings.notation === "tablature";
  const [health, setHealth] = useState<Health | null>(null),
    [healthError, setHealthError] = useState(""),
    [consent, setConsent] = useState(false),
    [approved, setApproved] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [edits, setEdits] = useState<EngineNote[]>([]),
    [dirty, setDirty] = useState(false),
    [display, setDisplay] = useState("Notes & tab");
  const jobRef = useRef<string | null>(null),
    generation = useRef(0),
    mounted = useRef(true),
    audio = useRef<HTMLAudioElement | null>(null);
  async function refreshHealth() {
    try {
      setHealth(await api<Health>("/api/health"));
      setHealthError("");
    } catch {
      setHealth(null);
      setHealthError(
        "Python engine is not reachable. Start the service to enable specialist analysis.",
      );
    }
  }
  useEffect(() => {
    mounted.current = true;
    refreshHealth();
    return () => {
      mounted.current = false;
      generation.current++;
      if (jobRef.current)
        api("/api/jobs/" + jobRef.current, { method: "DELETE" }).catch(
          () => {},
        );
      audio.current?.pause();
    };
  }, []);
  useEffect(() => {
    generation.current++;
    if (jobRef.current) {
      api("/api/jobs/" + jobRef.current, { method: "DELETE" }).catch(() => {});
      jobRef.current = null;
    }
    audio.current?.pause();
    setJob(null);
    setConsent(false);
    setApproved(false);
    setEdits([]);
    setError("");
    setDirty(false);
    setBusy(false);
  }, [
    reference,
    take,
    kind,
    start,
    length,
    profile.id,
    profile.settings.tuning,
    profile.settings.capo,
    profile.settings.notation,
  ]);
  useEffect(() => {
    if (!job || !pending.includes(job.status)) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const next = await api<Job>("/api/jobs/" + job.id, {
          signal: controller.signal,
        });
        setJob(next);
        if (next.result) {
          setEdits(next.result.take_notes.map((n) => withTab(n, profile)));
          setDirty(false);
        }
      } catch (e) {
        if (!controller.signal.aborted) setError(String(e));
      }
    }, 1200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [job]);
  const duration =
    reference && take
      ? Math.min(
          length,
          take.buffer.duration,
          reference.buffer.duration - start,
        )
      : 0;
  const ready =
    !!health?.models.transcription.configured &&
    (kind === "isolated" || !!health?.models.separation.configured);
  async function upload() {
    if (!reference || !take || !consent || duration < 1) return;
    const current = ++generation.current;
    setBusy(true);
    setError("");
    try {
      const [original, performance] = await Promise.all([
        excerpt(reference.buffer, start, duration),
        excerpt(take.buffer, 0, duration),
      ]);
      if (current !== generation.current) return;
      const body = new FormData();
      body.set("reference", original, "reference.wav");
      body.set("take", performance, "take.wav");
      body.set("consent", "true");
      body.set("kind", referenceNotes ? "isolated" : kind);
      body.set("processing", processing);
      if (referenceNotes)
        body.set(
          "reference_notes",
          JSON.stringify(
            referenceNotes
              .filter((n) => n.time < duration)
              .map((n) => ({ ...n, duration: Math.max(0.03, Math.min(n.duration, duration - n.time)) })),
          ),
        );
      body.set("original_offset", String(start));
      body.set("instrument", profile.id);
      body.set("tuning", profile.settings.tuning);
      body.set("capo", String(profile.settings.capo));
      body.set("notation", profile.settings.notation);
      const next = await api<Job>("/api/jobs", { method: "POST", body });
      const accepted = next.instrument_profile;
      if (
        !accepted ||
        accepted.id !== profile.id ||
        accepted.midi_min !== profile.midi_min ||
        accepted.midi_max !== profile.midi_max ||
        accepted.capo !== profile.settings.capo ||
        accepted.notation !== profile.settings.notation ||
        JSON.stringify(accepted.open_strings) !==
          JSON.stringify(profile.openStrings)
      ) {
        await api("/api/jobs/" + next.id, { method: "DELETE" });
        throw Error(
          "The engine did not accept this instrument configuration. Update/restart the engine before comparing; the session was deleted.",
        );
      }
      if (current !== generation.current || !mounted.current) {
        await api("/api/jobs/" + next.id, { method: "DELETE" });
        return;
      }
      jobRef.current = next.id;
      setJob(next);
      setApproved(false);
    } catch (e) {
      if (current === generation.current)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }
  async function approve() {
    if (!job || !approved) return;
    setBusy(true);
    setError("");
    const current = generation.current;
    try {
      const next = await api<Job>(`/api/jobs/${job.id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved: true }),
      });
      if (current === generation.current) setJob(next);
    } catch (e) {
      if (current === generation.current) setError(String(e));
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }
  async function remove() {
    generation.current++;
    audio.current?.pause();
    setBusy(true);
    setError("");
    try {
      if (jobRef.current)
        await api("/api/jobs/" + jobRef.current, { method: "DELETE" });
      jobRef.current = null;
      setJob(null);
      setEdits([]);
      setConsent(false);
      setApproved(false);
      setDirty(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  function update(id: number, change: Partial<EngineNote>) {
    setEdits((values) =>
      values.map((n) => (n.id === id ? { ...n, ...change } : n)),
    );
    setDirty(true);
  }
  async function save() {
    if (!job) return;
    const current = generation.current;
    setBusy(true);
    setError("");
    try {
      const next = await api<Job>(`/api/jobs/${job.id}/notes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: edits }),
      });
      if (current === generation.current) {
        setJob(next);
        setEdits(next.result!.take_notes.map((n) => withTab(n, profile)));
        setDirty(false);
      }
    } catch (e) {
      if (current === generation.current) setError(String(e));
    } finally {
      if (current === generation.current) setBusy(false);
    }
  }
  const result = job?.result;
  return (
    <section className="engine panel" aria-label="Specialist analysis engine">
      <div className="engine-heading">
        <div>
          <div className="eyebrow">SPECIALIST AUDIO ENGINE</div>
          <h2>Separate. Listen. Then compare.</h2>
        </div>
        <span className="outline-tag">
          PYTHON · {health?.models.device_policy.toUpperCase() ?? "OFFLINE"}
        </span>
      </div>
      <p className="panel-desc">
        The full-band reference is never treated as a clean instrument
        performance. Upload only your selected{" "}
        {Math.max(0, duration).toFixed(1)}-second excerpts, then check the{" "}
        {profile.separation_stem} stem before comparing.
      </p>
      <div className="engine-capabilities">
        <span
          className={health?.models.separation.configured ? "available" : ""}
        >
          {health?.models.separation.configured ? "●" : "○"} {profile.name}{" "}
          separation · htdemucs_6s
        </span>
        <span
          className={health?.models.transcription.configured ? "available" : ""}
        >
          {health?.models.transcription.configured ? "●" : "○"} Polyphonic notes
          · Basic Pitch
        </span>
        <button onClick={refreshHealth} title="Refresh engine availability">
          <RefreshCw size={13} /> Check engine
        </button>
      </div>
      {healthError && <p className="engine-warning">{healthError}</p>}
      {health && !ready && (
        <p className="engine-warning">
          {kind === "mix" && !health.models.separation.configured
            ? "Six-source separation weights are not provisioned on this server. Supply an isolated instrument reference, or install the documented model. "
            : ""}
          {!health.models.transcription.configured
            ? "The specialist transcription model also needs installation. "
            : ""}
          There is no automatic downgrade to the local prototype.
        </p>
      )}
      {health && (
        <ModelInstaller
          separation={health.models.separation}
          onInstalled={refreshHealth}
        />
      )}
      {!job && (
        <>
          <label className="consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>
              I agree to upload these two audio excerpts to the analysis server.
              I have permission to process them. They are not used for training
              and are deleted after one hour, on session deletion or clean
              server shutdown. Closing this view requests deletion; an
              interrupted connection may leave files until expiry.
            </span>
          </label>
          <button
            className="primary"
            disabled={
              !consent ||
              !ready ||
              !reference ||
              !take ||
              duration < 1 ||
              busy ||
              recording
            }
            onClick={upload}
          >
            <CloudUpload size={16} />
            {busy
              ? "Preparing / uploading excerpts…"
              : `Upload excerpts & prepare ${profile.separation_stem}`}
          </button>
        </>
      )}
      {job && (
        <>
          <div className="job-stage" role="status">
            <div>
              <strong>
                {job.status === "failed" ? "Processing unavailable" : job.stage}
              </strong>
              <p>
                {job.device.model ?? "A single worker processes the job queue."}
                {job.device.device ? ` · ${job.device.device}` : ""}
              </p>
            </div>
            <button disabled={busy} onClick={remove}>
              <Trash2 size={14} />{" "}
              {pending.includes(job.status)
                ? "Cancel & delete"
                : "Delete session"}
            </button>
          </div>
          {job.device.warning && (
            <p className="engine-warning">{job.device.warning}</p>
          )}
          {job.error && (
            <p role="alert" className="error">
              {job.error}
            </p>
          )}
          {job.guitar_url && (
            <div className="stem-review">
              <h3>
                {kind === "mix"
                  ? `Extracted ${profile.separation_stem}`
                  : `Supplied ${profile.separation_stem} reference`}{" "}
                · quality check
              </h3>
              <audio
                ref={audio}
                key={job.guitar_url}
                controls
                src={job.guitar_url}
                preload="none"
              />
              <p>
                Listen for missing notes, other instruments or watery/warbling
                artefacts. An instrument stem may contain overlapping parts. If
                it is not usable, delete this session and provide a cleaner
                reference.
              </p>
              {job.status === "review" && (
                <>
                  <label className="consent">
                    <input
                      type="checkbox"
                      checked={approved}
                      onChange={(e) => setApproved(e.target.checked)}
                    />
                    <span>
                      I listened to this reference and it is usable for
                      comparison.
                    </span>
                  </label>
                  <button
                    className="primary"
                    disabled={!approved || busy}
                    onClick={approve}
                  >
                    <Check size={16} /> Approve reference & analyse
                  </button>
                </>
              )}
            </div>
          )}
          {result && (
            <>
              <Summary result={result} duration={job?.duration ?? length} bars={bars} />
              <div className="metrics">
                <div>
                  <label>Harmonic alignment</label>
                  <strong>
                    {result.alignment.confidence} <small>confidence</small>
                  </strong>
                  <p>
                    Uncalibrated · cost{" "}
                    {result.alignment.mean_chroma_cost.toFixed(3)} · manually
                    selected passage
                  </p>
                </div>
                <div>
                  <label>Same-pitch onset difference</label>
                  <strong>
                    {result.comparison.mean_absolute_timing_seconds === null
                      ? "Unavailable"
                      : `${Math.round(result.comparison.mean_absolute_timing_seconds * 1000)} ms`}
                  </strong>
                  <p>Before time warping; includes recording delay.</p>
                </div>
                <div>
                  <label>Pitch difference candidates</label>
                  <strong>
                    {result.comparison.pitch_difference_candidates}
                  </strong>
                  <p>
                    Not confirmed mistakes.{" "}
                    {result.provenance.edited
                      ? "Recomputed from your edited notes."
                      : "From model-estimated note events."}
                  </p>
                </div>
              </div>
              <p className="caution">
                {result.alignment.warning} {result.comparison.uncertainty}
              </p>
              <div className="alignment-plot">
                <strong>Passage alignment</strong>
                <svg
                  viewBox="0 0 500 100"
                  role="img"
                  aria-label="Take time mapped to reference time"
                >
                  <path
                    d="M 5 95 L 495 5"
                    stroke="#c5cfba"
                    strokeDasharray="4"
                    fill="none"
                  />
                  <polyline
                    points={result.alignment.map
                      .map(
                        ([t, r]) =>
                          `${5 + (t / job.duration) * 490},${95 - (r / job.duration) * 90}`,
                      )
                      .join(" ")}
                    fill="none"
                    stroke="#496b3b"
                    strokeWidth="2"
                  />
                </svg>
                <p>
                  Horizontal: your take · Vertical: reference · Dashed:
                  identical timing. This map suggests alignment, not proof of
                  correct timing.
                </p>
              </div>
              <div className="transcription-head">
                <h3>
                  Editable transcription{" "}
                  <span>
                    {profile.name.toUpperCase()} ·{" "}
                    {profile.settings.tuning.toUpperCase()} · CAPO{" "}
                    {profile.settings.capo} · ESTIMATED
                  </span>
                </h3>
                <div className="segmented">
                  {["Notes & tab", "Reference notes", "Differences"].map(
                    (x) => (
                      <button
                        className={display === x ? "chosen" : ""}
                        onClick={() => setDisplay(x)}
                        key={x}
                      >
                        {x === "Notes & tab" && !showTab ? "Notes" : x}
                      </button>
                    ),
                  )}
                </div>
              </div>
              {display === "Notes & tab" ? (
                <>
                  <p className="caution">
                    Correct note pitch, start, duration, or string/fret. Save to
                    recompute the comparison. Tab positions are suggestions, not
                    detected finger placement. Amplitude is model activation,
                    not a confidence probability.
                  </p>
                  <div className="editable-scroll">
                    <table className="editable-notes">
                      <thead>
                        <tr>
                          <th>Start (s)</th>
                          <th>Length (s)</th>
                          <th>Note</th>
                          <th hidden={!showTab}>String</th>
                          <th hidden={!showTab}>Fret</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {edits.map((n) => (
                          <tr key={n.id}>
                            <td>
                              <input
                                aria-label={`Note ${n.id} start`}
                                type="number"
                                min="0"
                                step=".01"
                                value={n.time}
                                onChange={(e) =>
                                  update(n.id, { time: Number(e.target.value) })
                                }
                              />
                            </td>
                            <td>
                              <input
                                aria-label={`Note ${n.id} duration`}
                                type="number"
                                min=".01"
                                step=".01"
                                value={n.duration}
                                onChange={(e) =>
                                  update(n.id, {
                                    duration: Number(e.target.value),
                                  })
                                }
                              />
                            </td>
                            <td>
                              <select
                                aria-label={`Note ${n.id} pitch`}
                                value={n.midi}
                                onChange={(e) => {
                                  const midi = Number(e.target.value),
                                    pos = tabPosition(midi, profile);
                                  update(n.id, {
                                    midi,
                                    string: pos?.string ?? null,
                                    fret: pos?.fret ?? null,
                                  });
                                }}
                              >
                                {Array.from(
                                  {
                                    length:
                                      profile.midi_max - profile.midi_min + 1,
                                  },
                                  (_, i) => i + profile.midi_min,
                                ).map((m) => (
                                  <option key={m} value={m}>
                                    {note(m)}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td hidden={!showTab}>
                              <select
                                aria-label={`Note ${n.id} string`}
                                value={n.string ?? 1}
                                onChange={(e) => {
                                  const string = Number(e.target.value);
                                  update(n.id, {
                                    string,
                                    midi: tuning[string - 1] + (n.fret ?? 0),
                                  });
                                }}
                              >
                                {tuning.map((_, i) => (
                                  <option key={i} value={i + 1}>
                                    {i + 1} ({note(tuning[i])})
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td hidden={!showTab}>
                              <input
                                aria-label={`Note ${n.id} fret`}
                                type="number"
                                min="0"
                                max={profile.maxFret}
                                value={n.fret ?? 0}
                                onChange={(e) => {
                                  const fret = Number(e.target.value);
                                  update(n.id, {
                                    fret,
                                    midi: tuning[(n.string ?? 1) - 1] + fret,
                                  });
                                }}
                              />
                            </td>
                            <td>
                              <button
                                aria-label={`Remove note ${n.id}`}
                                onClick={() => {
                                  setEdits((v) =>
                                    v.filter((x) => x.id !== n.id),
                                  );
                                  setDirty(true);
                                }}
                              >
                                <Trash2 size={13} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {!edits.length && (
                    <p className="caution">
                      No take notes detected. This does not prove that you
                      played no notes.
                    </p>
                  )}
                  <div className="edit-actions">
                    <button
                      onClick={() => {
                        setEdits((v) => [
                          ...v,
                          {
                            id: Math.max(-1, ...v.map((n) => n.id)) + 1,
                            time: 0,
                            duration: Math.min(0.3, job.duration),
                            midi: tuning[0] ?? 60,
                            string: tuning.length ? 1 : null,
                            fret: tuning.length ? 0 : null,
                            amplitude: 0.5,
                          },
                        ]);
                        setDirty(true);
                      }}
                    >
                      <Plus size={14} /> Add note
                    </button>
                    <button
                      className="primary"
                      disabled={!dirty || busy}
                      onClick={save}
                    >
                      <Save size={14} />
                      {busy ? "Saving…" : "Save & recompute differences"}
                    </button>
                  </div>
                  {dirty && (
                    <p className="engine-warning">
                      Unsaved edits: comparison above still reflects the last
                      saved notes.
                    </p>
                  )}
                  <div className="tab-scroll" hidden={!showTab}>
                    <div className="tab">
                      {tuning.map(note).map((s, i) => (
                        <div className="tab-row" key={s}>
                          <b>{s}</b>
                          {edits.slice(0, 24).map((n) => (
                            <span key={n.id}>
                              {n.string === i + 1 ? n.fret : "—"}
                            </span>
                          ))}
                        </div>
                      ))}
                    </div>
                    <p className="caution">
                      First 24 events; columns are note events, not rhythmic
                      notation.
                    </p>
                  </div>
                </>
              ) : display === "Reference notes" ? (
                <div className="notes">
                  {result.reference_notes.map((n) => (
                    <div key={n.id}>
                      <small>{n.time.toFixed(2)}s</small>
                      <b>{note(n.midi)}</b>
                      <small>{n.duration.toFixed(2)}s long</small>
                    </div>
                  ))}
                  {!result.reference_notes.length && (
                    <p>
                      No reference notes detected. Comparison is inconclusive.
                    </p>
                  )}
                </div>
              ) : (
                <div className="differences">
                  {result.comparison.findings
                    .filter(
                      (f) =>
                        f.kind !== "matched" ||
                        Math.abs(f.raw_timing_seconds ?? 0) > 0.1 ||
                        Math.abs(f.duration_difference_seconds ?? 0) > 0.15,
                    )
                    .slice(0, 100)
                    .map((f, i) => (
                      <div key={i}>
                        <b>{f.kind.replaceAll("_", " ")}</b>
                        <span>
                          {f.take_time !== undefined
                            ? `Take ${f.take_time.toFixed(2)}s`
                            : ""}{" "}
                          {f.reference_time !== undefined
                            ? `Reference ${f.reference_time.toFixed(2)}s`
                            : ""}
                        </span>
                        <p>
                          {f.take_midi !== undefined
                            ? `Take: ${note(f.take_midi)}. `
                            : ""}
                          {f.reference_midi !== undefined
                            ? `Reference: ${note(f.reference_midi)}. `
                            : ""}
                          {f.raw_timing_seconds !== undefined
                            ? `Raw onset offset: ${Math.round(f.raw_timing_seconds * 1000)} ms. `
                            : ""}
                          {f.duration_difference_seconds !== undefined
                            ? `Estimated sustain difference: ${Math.round(f.duration_difference_seconds * 1000)} ms. `
                            : ""}
                          {f.detail ??
                            "Listen to confirm; this could be a model or alignment error."}
                        </p>
                      </div>
                    ))}
                </div>
              )}
              <details className="provenance">
                <summary>Models, processing and uncertainty</summary>
                <p>
                  {result.provenance.separation.model} ·{" "}
                  {result.provenance.separation.device}
                  <br />
                  {result.provenance.transcription}
                </p>
                {result.warnings.map((w) => (
                  <p key={w}>{w}</p>
                ))}
                <p>
                  No buzz, neck pressure or individual-string fault diagnosis is
                  made.
                </p>
              </details>
            </>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}

function Summary({
  result,
  duration,
  bars,
}: {
  result: NonNullable<Job["result"]>;
  duration: number;
  bars?: BarMark[];
}) {
  const s = summarise(result.comparison.findings, duration, bars);
  return (
    <div className="take-summary" aria-label="Summary of your take">
      <div className="take-score">
        <small>Estimated match</small>
        <b>{s.overall === null ? "–" : `${s.overall}%`}</b>
      </div>
      <div className="take-points">
        {s.points.length ? (
          <ul>{s.points.map((p) => <li key={p}>{p[0].toUpperCase() + p.slice(1)}</li>)}</ul>
        ) : (
          <p>No clear mistakes found.</p>
        )}
        <p className="take-next"><b>Next:</b> {s.next}</p>
      </div>
      <div className="section-scores" role="list" aria-label="Score per section">
        {s.sections.map((r) => (
          <span
            key={r.label}
            role="listitem"
            className={"section-score " + (r.score === null ? "none" : r.score >= 85 ? "good" : r.score >= 60 ? "fair" : "poor")}
            title={`${r.label}: ${r.matched} matched, ${r.wrong} wrong, ${r.missed} missed, ${r.extra} extra, ${r.early + r.late} off the beat`}
          >
            <small>{r.label}</small>
            {r.score === null ? "–" : r.score}
          </span>
        ))}
      </div>
      <p className="helper">
        {result.comparison.method?.startsWith("score-informed")
          ? "Checked note by note against the tab's written notes. Only your recording is estimated, so these scores are more reliable than song comparisons; still listen back before drilling a bar."
          : "Scores come from automatic note detection on both recordings, so treat a single low bar with suspicion and listen back before drilling it."}
      </p>
    </div>
  );
}
