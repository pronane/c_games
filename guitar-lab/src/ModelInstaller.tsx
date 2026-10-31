import { useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { api, type Health } from "./engineApi";

type Props = {
  separation: Health["models"]["separation"];
  onInstalled: () => Promise<void>;
};
export default function ModelInstaller({ separation, onInstalled }: Props) {
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  async function install(file: File) {
    if (file.size !== 54_996_327) {
      setError(
        "Choose the actual 54,996,327-byte checkpoint. Git LFS pointers, archive files and HTML pages are not the model.",
      );
      return;
    }
    setWorking(true);
    setError("");
    try {
      const body = new FormData();
      body.set("checkpoint", file);
      await api("/api/models/separation", { method: "POST", body });
      await onInstalled();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorking(false);
      if (input.current) input.current.value = "";
    }
  }
  if (separation.configured || !separation.installation_supported) return null;
  return (
    <div className="model-installer">
      <h3>One-time guitar model setup</h3>
      <p>
        {separation.runtime_installed
          ? "Demucs, PyTorch and torchaudio are installed. The verified checkpoint is still missing."
          : "Install the Demucs/PyTorch runtime using the server setup instructions before using the model."}
      </p>
      <p>
        This server cannot reach the model download host. Download the
        checkpoint using your own browser, then select it here. Only the exact
        approved SHA-256 is accepted; arbitrary model files are never loaded.
      </p>
      <div className="model-install-actions">
        {separation.download_url && (
          <a href={separation.download_url} target="_blank" rel="noreferrer">
            <Download size={14} /> Download guitar model · 55 MB
          </a>
        )}
        <input
          ref={input}
          type="file"
          accept=".th"
          aria-label="Choose Demucs checkpoint"
          hidden
          onChange={(e) => e.target.files?.[0] && install(e.target.files[0])}
        />
        <button
          className="primary"
          disabled={working || !separation.runtime_installed}
          onClick={() => input.current?.click()}
        >
          <Upload size={14} />
          {working
            ? "Uploading & verifying model…"
            : "Install downloaded checkpoint"}
        </button>
      </div>
      <small>
        File: 5c90dfd2-34c22ccb.th · six-source model with a dedicated guitar
        output. Successful integrity verification enables full-band submissions;
        inference still needs a first-run test.
      </small>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </div>
  );
}
