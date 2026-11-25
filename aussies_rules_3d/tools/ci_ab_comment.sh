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
  echo 'Attract legs ran with `?ab=1`: fixed attract seed, menu overlays hidden, broadcast cam, `AB_STATS` logged from `renderer.info` every ~2 s.'
  echo 'The match leg uses `?ab=1&scenario=match` with a fixed seed, scripted tick inputs and a live controlled player (LOD candidate). It is a coverage scenario, not a third model comparison.'
  echo
  for leg in original lod match; do
    log="build/motion-ab/$leg/console.log"
    echo "**$leg**"
    if [ -f "$log" ]; then
      echo '```'
      grep -E 'AB_STATS|AB_PLAY|RENDER PROCESS GONE|capturePage failed|console' "$log" | tail -6
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
  echo
  if command -v node >/dev/null 2>&1 && [ -f tools/ab_stats.mjs ]; then
    node tools/ab_stats.mjs build/motion-ab/original build/motion-ab/lod build/motion-ab/match || echo '_ab_stats aggregation failed_'
    echo
  fi
  if [ -f build/motion-ab/match/gameplay-review.json ]; then
    echo '### Scripted gameplay measurements (not visual sign-off)'
    echo '```json'
    cat build/motion-ab/match/gameplay-review.json
    echo '```'
  fi
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
