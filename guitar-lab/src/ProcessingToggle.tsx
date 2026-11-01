import { useEffect, useState } from "react";
import { Cpu, MonitorCog } from "lucide-react";
import { api } from "./engineApi";

export type Processing = "cpu" | "gpu";
type Gpu = { available: boolean; name: string | null; detail: string };
let cached: Promise<Gpu | null> | null = null;
function gpuInfo() {
  return (cached ??= api<{ models: { gpu?: Gpu } }>("/api/health")
    .then((h) => h.models.gpu ?? null)
    .catch(() => {
      cached = null;
      return null;
    }));
}

/**
 * CPU (default) or the server's graphics card for instrument separation. The GPU option is
 * only enabled when the server reports a usable card. Transcription always runs on CPU.
 */
export default function ProcessingToggle({
  value,
  onChange,
  disabled,
}: {
  value: Processing;
  onChange: (next: Processing) => void;
  disabled?: boolean;
}) {
  const [gpu, setGpu] = useState<Gpu | null>(null);
  useEffect(() => {
    let live = true;
    gpuInfo().then((g) => {
      if (!live) return;
      setGpu(g);
      if (!g?.available && value === "gpu") onChange("cpu");
    });
    return () => {
      live = false;
    };
  }, []);
  return (
    <div className="processing" role="group" aria-label="Processing">
      <span className="processing-label">Separate instruments on</span>
      <div className="segmented">
        <button className={value === "cpu" ? "chosen" : ""} disabled={disabled} onClick={() => onChange("cpu")}>
          <Cpu size={13} /> CPU
        </button>
        <button
          className={value === "gpu" ? "chosen" : ""}
          disabled={disabled || !gpu?.available}
          title={gpu?.available ? `${gpu.name} (${gpu.detail})` : gpu?.detail ?? "Checking the server…"}
          onClick={() => onChange("gpu")}
        >
          <MonitorCog size={13} /> Graphics card
        </button>
      </div>
      <small className="helper">
        {gpu?.available
          ? value === "gpu"
            ? `Using ${gpu.name}. Much faster; falls back to CPU if it runs out of memory.`
            : `${gpu.name} available. CPU is slower but works everywhere.`
          : "No graphics card on the analysis server, so CPU is used. A 4-minute song takes a few minutes."}
      </small>
    </div>
  );
}
