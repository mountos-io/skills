#!/bin/bash
# Single-command entry for the mixed small-file / metadata workload.
#
#   ./run.sh /mnt/mountos                     # full mix, 60s measured
#   ./run.sh /mnt/mountos --duration 300
#   ./run.sh /mnt/mountos --only rename       # isolation mode after a regression
#
# Everything after the target directory is passed to mosbench.py verbatim
# (see: python3 mosbench.py run --help). The wrapper only does preflight:
# python version, target sanity, and a warning when the target is not a FUSE
# mount, which is a warning rather than an error because a local-disk run of
# the exact same mix is the natural baseline to compare a mount against.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  echo "usage: $0 <target-dir> [mosbench run args...]" >&2
  echo "       $0 /mnt/mountos --duration 300 --label before-upgrade" >&2
  exit 2
fi
TARGET="$1"; shift

command -v python3 >/dev/null || { echo "FATAL: python3 not found" >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' \
  || { echo "FATAL: python3 >= 3.8 required" >&2; exit 1; }

[ -d "$TARGET" ] || { echo "FATAL: $TARGET is not a directory" >&2; exit 1; }

if [ -r /proc/mounts ]; then
  FSTYPE="$(awk -v t="$(cd "$TARGET" && pwd -P)" '
    { if (t == $2 || $2 == "/" || index(t, $2 "/") == 1) { if (length($2) >= length(best)) { best = $2; fs = $3 } } }
    END { print fs }' /proc/mounts)"
  # mountOS is always FUSE, so a non-FUSE target almost always means the mount
  # FAILED and this is about to benchmark the underlying directory instead. That
  # failure is silent: writes to an unmounted mount point succeed against local
  # disk and look entirely healthy. Refuse by default and make the deliberate
  # local-baseline case say so explicitly.
  case "$FSTYPE" in
    fuse*) ;;
    *)
      if [ "${ALLOW_NON_FUSE:-0}" = "1" ]; then
        echo "note: $TARGET is on '$FSTYPE', not FUSE. Continuing because ALLOW_NON_FUSE=1." >&2
        echo "      Label this run as a local baseline; it is not a mountOS measurement." >&2
      else
        echo "FATAL: $TARGET is on '$FSTYPE', not a FUSE mount." >&2
        echo "       Either the mount failed, or this is the wrong path. Check with:" >&2
        echo "         mount | grep '$TARGET'" >&2
        echo "       For a deliberate local-disk baseline: ALLOW_NON_FUSE=1 $0 $TARGET ..." >&2
        exit 1
      fi
      ;;
  esac
else
  echo "note: /proc/mounts unreadable; cannot confirm $TARGET is a FUSE mount" >&2
fi

exec python3 "$HERE/mosbench.py" run --target "$TARGET" "$@"
