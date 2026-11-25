#!/usr/bin/env bash
# Agent-side retrieval: API-readable diagnostics first, then best-effort videos.
# Usage: bash tools/review_workflow.sh RUN_ID
set -euo pipefail
RUN="${1:?Supply a GitHub run ID}"
[[ "$RUN" =~ ^[0-9]+$ ]] || { echo 'Run ID must be numeric' >&2; exit 1; }
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
OUT="build/workflow-review/$RUN"
mkdir -p "$OUT"
gh run view "$RUN" --repo "$REPO" --json status,conclusion,url,jobs > "$OUT/run.json"
gh api "repos/$REPO/actions/runs/$RUN/jobs" --paginate --jq '.jobs[].check_run_url' > "$OUT/check-urls.txt"
while IFS= read -r url; do
  id="${url##*/}"
  gh api "repos/$REPO/check-runs/$id/annotations" --paginate --jq '.[] | tojson' > "$OUT/annotations-$id.jsonl"
done < "$OUT/check-urls.txt"
cat "$OUT/run.json"
node --input-type=module - "$OUT" <<'NODE'
import fs from 'node:fs';
import path from 'node:path';
const dir = process.argv[2];
for (const file of fs.readdirSync(dir).filter(f => /^annotations-.*\.jsonl$/.test(f))) {
  for (const annotation of fs.readFileSync(path.join(dir, file), 'utf8').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line))) {
    const match = /^GAMEPLAY_PREVIEW_(\d+)$/.exec(annotation.title ?? '');
    if (match) {
      const target = path.join(dir, `preview-${match[1]}.jpg`);
      fs.writeFileSync(target, Buffer.from(annotation.message.trim(), 'base64'));
      console.log(`Recovered game preview: ${target}`);
    } else console.log(`${annotation.annotation_level}: ${annotation.title}: ${annotation.message}`);
  }
}
NODE
if gh run download "$RUN" --repo "$REPO" --name aussies-rules-motion-ab-visual --dir "$OUT/visual"; then
  echo "Video and capture states downloaded into $OUT/visual — ready for frame review."
else
  echo "Artifact download failed. API measurements were retrieved; video is NOT reviewed. See $OUT." >&2
fi
