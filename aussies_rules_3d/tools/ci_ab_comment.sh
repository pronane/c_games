#!/usr/bin/env bash
# Upsert a sticky PR comment with the visual-ab leg's stats (AB_STATS lines from the
# Electron console log + artifact sizes). Never fails the job — diagnostics only.
set -uo pipefail
PR="$1"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY not set}"
marker='<!-- aussies-motion-ab-sticky -->'
{
  echo "$marker"
  echo '### Aussies Rules Motion A/B — attract-demo capture'
  echo
  echo 'Both legs captured the title/attract demo under software WebGL (see workflow). If the companion AB_MODE PR is merged, captures run with `?ab=1` (fixed seed, menu hidden, `AB_STATS` logged from `renderer.info`).'
  echo
  for leg in original lod; do
    log="build/motion-ab/$leg/electron.log"
    echo "**$leg**"
    if [ -f "$log" ]; then
      echo '```'
      grep -E 'AB_STATS|RENDER PROCESS GONE|capturePage failed|console' "$log" | tail -6
      echo '```'
    else
      echo '_no electron.log captured_'
    fi
    if [ -f "build/motion-ab/$leg/summary.json" ]; then
      echo "- $(cat "build/motion-ab/$leg/summary.json" | tr -d '\n')"
    fi
    if compgen -G "build/motion-ab/$leg/frame-*.png" > /dev/null; then
      echo "- frames: $(ls build/motion-ab/$leg/frame-*.png | wc -l)"
    fi
    if [ -f "build/motion-ab/$leg/$leg.mp4" ]; then
      echo "- $leg.mp4: $(du -h "build/motion-ab/$leg/$leg.mp4" | cut -f1)"
    fi
    echo
  done
  echo 'Full frames + MP4s + logs: workflow artifact `aussies-rules-motion-ab-visual` on this run.'
  echo "_Refresh: runs on every PR push to this branch; artifact download requires browser access to the run page._"
} > /tmp/ab-comment.md
mkdir -p build/motion-ab && cp /tmp/ab-comment.md build/motion-ab/pr-comment.md

existing=$(gh api "repos/$REPO/issues/$PR/comments" --paginate --jq ".[] | select(.body | contains(\"$marker\")) | .id" 2>&1 | head -1)
echo "existing sticky comment id: ${existing:-none}"
if [[ "$existing" =~ ^[0-9]+$ ]]; then
  gh api -X PATCH "repos/$REPO/issues/comments/$existing" -F body=@/tmp/ab-comment.md && echo "updated comment $existing" || echo "PATCH failed (see errors above)"
else
  gh pr comment "$PR" --body-file /tmp/ab-comment.md && echo "created comment" || echo "POST failed (see errors above)"
fi
