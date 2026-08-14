#!/bin/bash
# Small-file speed against a mounted mountOS volume: a shallow git clone and an
# npm install, which is the shape most likely to expose per-file overhead on a
# network filesystem.
#
# This is a PERFORMANCE probe, not a correctness suite. There is no pass or fail.
# Compare against the same workload on a local filesystem on the same host, and
# against your own earlier runs.
#
#   sudo ./smallfiles.sh
#   sudo GIT_REPO=https://github.com/you/yours.git ./smallfiles.sh
#   sudo NPM_PACKAGES="react react-dom vite" ./smallfiles.sh
#
# Prefer the operator's own repository and dependency set over these defaults.
set -uo pipefail

MNT="${MNT:-/mnt/mountos}"
LOGDIR="${LOGDIR:-/var/log/mountos-conformance}"
GIT_REPO="${GIT_REPO:-https://github.com/expressjs/express.git}"
NPM_PACKAGES="${NPM_PACKAGES:-express lodash}"
export HOME="${HOME:-/root}"

mkdir -p "$LOGDIR"
LOG="$LOGDIR/smallfiles.log"; : > "$LOG"
say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
mount | grep -q "on $MNT type fuse" || { echo "FATAL: $MNT is not a FUSE mount"; exit 1; }
command -v git >/dev/null || { echo "FATAL: git missing"; exit 1; }
command -v npm >/dev/null || { echo "FATAL: npm missing"; exit 1; }

# A fresh work root per run. A populated node_modules makes npm a no-op and the
# numbers meaningless.
WORK="$MNT/smallfiles-$(date +%s)-$$"
mkdir -p "$WORK/git" "$WORK/npm"

count() { find "$1" 2>/dev/null | wc -l; }
timed() { # <label> <dir> -- <cmd...>
  local label="$1" dir="$2"; shift 3
  local t0 t1
  t0=$(date +%s)
  ( cd "$dir" && "$@" ) >> "$LOG" 2>&1
  local rc=$?
  t1=$(date +%s)
  printf '%-28s %6ss  rc=%d\n' "$label" "$((t1 - t0))" "$rc" | tee -a "$LOG"
  return $rc
}

say "work root: $WORK"
say "git repo:  $GIT_REPO"
say "npm pkgs:  $NPM_PACKAGES"
echo | tee -a "$LOG"

timed "git clone" "$WORK/git" -- git clone --depth 1 "$GIT_REPO" repo
say "  entries after clone: $(count "$WORK/git/repo")"

if [ -f "$WORK/git/repo/package.json" ]; then
  timed "npm install (in repo)" "$WORK/git/repo" -- npm install --no-audit --no-fund --loglevel=error
  say "  node_modules entries: $(count "$WORK/git/repo/node_modules")"
fi

( cd "$WORK/npm" && npm init -y >/dev/null 2>&1 )
# shellcheck disable=SC2086 # NPM_PACKAGES is a deliberate word list
timed "npm install (fresh)" "$WORK/npm" -- npm install --no-audit --no-fund --loglevel=error $NPM_PACKAGES
say "  node_modules entries: $(count "$WORK/npm/node_modules")"

echo | tee -a "$LOG"
say "done. Left in place for inspection: $WORK"
say "Remove it when finished:  rm -rf $WORK"
