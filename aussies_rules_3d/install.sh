#!/usr/bin/env sh
#
# Aussie Rules 3D — installer for macOS and Linux.
#
#   ./install.sh                full setup (Node, dependencies, 3D assets)
#   ./install.sh --check        say what is already there, change nothing
#   ./install.sh --assets       also regenerate the 3D assets with Blender
#
# Nothing here needs sudo. If the machine has no Node 20+, a private copy is
# downloaded into ~/.aussie-rules-3d/node and never touches anything else.
set -eu

cd "$(dirname "$0")"

MIN_MAJOR=20
NODE_DIR="${AUSSIE_RULES_NODE_DIR:-$HOME/.aussie-rules-3d/node}"

say() { printf '%s\n' "$*"; }
die() { printf '\n%s\n\n' "$*" >&2; exit 1; }

download() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$2" "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$2" "$1"
  else
    die "Neither curl nor wget is available, so Node cannot be downloaded.
Install Node 20+ from https://nodejs.org and run this again."
  fi
}

node_major() {
  node -e 'process.stdout.write(String(process.versions.node.split(".")[0]))' 2>/dev/null || printf '0'
}

bootstrap_node() {
  case "$(uname -s)" in
    Darwin) os=darwin ;;
    Linux) os=linux ;;
    *) die "This installer supports macOS and Linux. On Windows, run install.ps1." ;;
  esac
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    arm64|aarch64) arch=arm64 ;;
    *) die "Unsupported CPU architecture: $(uname -m)" ;;
  esac

  say "→ downloading a private Node.js runtime into $NODE_DIR (one-time, ~30 MB)"
  mkdir -p "$NODE_DIR"
  version=$(curl -fsSL https://nodejs.org/dist/index.json | grep -o '"version":"v[0-9.]*"' | head -1 | sed 's/.*"v/v/;s/"//') || version=v22.11.0
  tarball="node-$version-$os-$arch.tar.gz"
  download "https://nodejs.org/dist/$version/$tarball" "$NODE_DIR/$tarball"
  tar -xzf "$NODE_DIR/$tarball" -C "$NODE_DIR" --strip-components=1
  rm -f "$NODE_DIR/$tarball"
  printf '%s/bin' "$NODE_DIR" > "$NODE_DIR/bin-path"
}

if [ "$(node_major)" -lt "$MIN_MAJOR" ]; then
  if [ -f "$NODE_DIR/bin-path" ]; then
    PATH="$(cat "$NODE_DIR/bin-path"):$PATH"
    export PATH
  fi
fi

if [ "$(node_major)" -lt "$MIN_MAJOR" ]; then
  bootstrap_node
  PATH="$(cat "$NODE_DIR/bin-path"):$PATH"
  export PATH
fi

if [ "$(node_major)" -lt "$MIN_MAJOR" ]; then
  die "Node 20+ is required but could not be installed automatically.
Install it from https://nodejs.org and run this again."
fi

exec node scripts/install.mjs "$@"
