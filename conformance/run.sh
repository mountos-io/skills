#!/bin/bash
# Run the conformance suites against a mounted mountOS volume.
#
#   ./run.sh                     all three, serialised
#   ./run.sh pjdfstest fsx       a subset
#   MNT=/mnt/other ./run.sh      a different mount point
#
# Serialised on purpose: the suites share one mount, so running two at once makes
# timing meaningless and can trip LTP's own timeouts on load rather than on a real
# hang.
set -uo pipefail

MNT="${MNT:-/mnt/mountos}"
PREFIX="${PREFIX:-/opt}"
LOGDIR="${LOGDIR:-/var/log/mountos-conformance}"
FSX_OPS="${FSX_OPS:-100000}"
FSX_SIZE="${FSX_SIZE:-262144}"
PJD_JOBS="${PJD_JOBS:-4}"
LTP_EXEC_TIMEOUT="${LTP_EXEC_TIMEOUT:-120}"
SKIPFILE="${SKIPFILE:-$(dirname "$(readlink -f "$0")")/ltp-skip.txt}"
export HOME="${HOME:-/root}"

mkdir -p "$LOGDIR"
say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGDIR/run.log"; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
mount | grep -q "on $MNT type fuse" || { echo "FATAL: $MNT is not a FUSE mount"; exit 1; }

# The mode-0000 assertion. Without --acl on the mount, a zero mode is stored as
# 0644 and pjdfstest open/26.t fails in a way that reads like a create-path bug.
# One second here beats an 84-second suite run and a wrong bug report.
check_acl() {
  local probe="$MNT/.mos-modecheck.$$" got
  rm -f "$probe"
  python3 -c "import os;os.close(os.open('$probe',os.O_CREAT|os.O_WRONLY,0o000))" 2>/dev/null
  got=$(stat -c %a "$probe" 2>/dev/null)
  rm -f "$probe"
  if [ "$got" != "0" ]; then
    say "WARNING: mode-0000 create stored as ${got:-unknown}, expected 0."
    say "         Remount with --acl (or --null-permissions), or pjdfstest open/26.t WILL fail."
    return 1
  fi
  say "mode-0000 preservation: ok"
}

run_pjdfstest() {
  say "pjdfstest start"
  local log="$LOGDIR/pjdfstest.log"; : > "$log"
  # The tests resolve the binary relative to the directory under test, so it has
  # to be staged inside the mount.
  cp "$PREFIX/pjdfstest/pjdfstest" "$MNT/" 2>/dev/null || { say "pjdfstest binary missing; run setup.sh"; return 1; }
  ( cd "$MNT" && prove -rv -o -j"$PJD_JOBS" "$PREFIX/pjdfstest/tests" ) >> "$log" 2>&1
  local rc=$?
  rm -f "$MNT/pjdfstest"
  local ok notok
  ok=$(grep -c '^ok ' "$log" 2>/dev/null); notok=$(grep -c '^not ok ' "$log" 2>/dev/null)
  say "pjdfstest done rc=$rc ok=$ok not-ok=$notok  ($log)"
  # One TODO for unlink() on a directory is expected: mountOS returns EISDIR,
  # matching Linux, where POSIX permits EPERM.
  return $rc
}

run_fsx() {
  say "fsx start ($FSX_OPS ops, $FSX_SIZE bytes)"
  local log="$LOGDIR/fsx.log"; : > "$log"
  command -v fsx >/dev/null 2>&1 || { say "fsx missing; run setup.sh"; return 1; }
  mkdir -p "$MNT/fsxrun"; rm -f "$MNT/fsxrun/fsx.bin"
  # Fresh random seed each run (-S 0). Reuse a seed only to reproduce a failure.
  fsx -N "$FSX_OPS" -S 0 -l "$FSX_SIZE" -p 10000 "$MNT/fsxrun/fsx.bin" >> "$log" 2>&1
  local rc=$?
  if grep -qiE 'bad data|short read|offset mismatch' "$log"; then
    say "fsx DATA DIVERGENCE, see $log"; return 1
  fi
  say "fsx done rc=$rc  ($log)"
  return $rc
}

run_ltp() {
  say "ltp start"
  local log="$LOGDIR/ltp.log"; : > "$log"
  [ -x "$PREFIX/kirk/kirk" ] || { say "kirk missing; run setup.sh"; return 1; }
  mkdir -p "$MNT/ltprun"
  # kirk replaced runltp upstream and takes no --framework argument.
  # The skip list keeps the run to filesystem signal. Without it, non-FS tests
  # (sockets, BPF, kernel CVEs) hang on their own timeouts and the run takes hours
  # instead of minutes.
  local skipargs=()
  [ -f "$SKIPFILE" ] && skipargs=(--skip-file "$SKIPFILE")
  ( cd "$PREFIX/kirk" && LTPROOT="$PREFIX/ltp" PATH="$PREFIX/ltp/testcases/bin:$PATH" \
      ./kirk --run-suite syscalls --tmp-dir "$MNT/ltprun" \
             --exec-timeout "$LTP_EXEC_TIMEOUT" "${skipargs[@]}" \
             --json-report "$LOGDIR/ltp-report.json" ) >> "$log" 2>&1
  local rc=$?
  # Parse kirk's TEST SUMMARY, not the per-line output. Each log line is one test
  # FILE; the summary counts individual assertions, which is the number that is
  # comparable to any published LTP result. Confusing the two understates a run
  # by roughly 5x.
  local pass fail broken skip
  pass=$(sed -n 's/^ *Passed: *\([0-9]*\).*/\1/p'   "$log" | tail -1)
  fail=$(sed -n 's/^ *Failed: *\([0-9]*\).*/\1/p'   "$log" | tail -1)
  broken=$(sed -n 's/^ *Broken: *\([0-9]*\).*/\1/p' "$log" | tail -1)
  skip=$(sed -n 's/^ *Skipped: *\([0-9]*\).*/\1/p'  "$log" | tail -1)
  # Skipped is not a failure: architecture gates and absent kernel features.
  say "ltp done rc=$rc passed=${pass:-?} failed=${fail:-?} broken=${broken:-?} skipped=${skip:-?}  ($log)"
  if [ -n "${fail:-}" ] && [ "${fail:-0}" -gt 0 ]; then
    say "  failing tests:"; sed -n '/^Failures:/,/^$/p' "$log" | sed 's/^/    /'
  fi
  return $rc
}

check_acl || say "continuing anyway; expect open/26.t to fail"

SUITES=("$@")
[ ${#SUITES[@]} -eq 0 ] && SUITES=(pjdfstest fsx ltp)

overall=0
for s in "${SUITES[@]}"; do
  case "$s" in
    pjdfstest) run_pjdfstest || overall=1 ;;
    fsx)       run_fsx       || overall=1 ;;
    ltp)       run_ltp       || overall=1 ;;
    *)         say "unknown suite: $s"; overall=1 ;;
  esac
done

say "ALL DONE rc=$overall  logs in $LOGDIR"
exit $overall
