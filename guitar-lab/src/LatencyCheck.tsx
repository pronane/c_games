import { useState } from "react";
import { captureError } from "./audioInputs";
import type { LatencyResult } from "./practice";
import type { Recorder } from "./recorder";

/** "Recording delay" card: shows the saved measurement and runs a new one. */
export default function LatencyCheck({
  recorder,
  latency,
  disabled,
  onMeasured,
  onBefore,
}: {
  recorder: () => Recorder;
  latency: LatencyResult | null;
  disabled?: boolean;
  onMeasured: (result: LatencyResult) => void;
  onBefore?: () => void;
}) {
  const [measuring, setMeasuring] = useState<"" | "speakers" | "play-along">(""),
    [note, setNote] = useState("");
  async function measure(method: "speakers" | "play-along") {
    onBefore?.();
    setNote("");
    setMeasuring(method);
    try {
      const { result, note } = await recorder().measureLatency(method);
      setNote(note);
      if (result.ok) onMeasured(result);
    } catch (e) {
      setNote(captureError(e));
    } finally {
      setMeasuring("");
    }
  }
  return (
    <div className="latency">
      <p className="helper">
        <b>Recording delay:</b>{" "}
        {latency?.ok
          ? `${latency.ms} ms, measured ${latency.measured} (${latency.method === "speakers" ? "speaker test" : "play-along test"}).`
          : "not measured on this device yet. Timing results include your device's delay until you measure it once."}
      </p>
      <div className="presets">
        <button disabled={!!measuring || disabled} onClick={() => measure("speakers")}>
          {measuring === "speakers" ? "Listening…" : "Measure with speakers"}
        </button>
        <button disabled={!!measuring || disabled} onClick={() => measure("play-along")}>
          {measuring === "play-along" ? "Pluck on each click…" : "Measure with headphones"}
        </button>
      </div>
      {measuring === "speakers" && <p className="helper">Headphones off, volume up, stay quiet for five seconds.</p>}
      {measuring === "play-along" && (
        <p className="helper">After four count-in clicks, pluck a muted string exactly on each of the next eight clicks.</p>
      )}
      {note && <p className="helper" role="status">{note}</p>}
    </div>
  );
}
