#!/bin/bash
# mdtest against a mounted mountOS volume: metadata-layer behaviour under
# create, stat, and remove, across directory shapes that stress different parts
# of the metadata path.
#
#   ./mdtest.sh --list                 show the combinations and what each probes
#   ./mdtest.sh                        run the default set (flat, tree, contention)
#   ./mdtest.sh flat-wide deep-tree    run named combinations
#   ./mdtest.sh --all                  run every combination
#   TASKS=4 ./mdtest.sh shared-dir     run with 4 parallel MPI tasks
#
# mdtest ships with IOR (github.com/hpc/ior). setup.sh installs both.
set -uo pipefail

MNT="${MNT:-/mnt/mountos}"
LOGDIR="${LOGDIR:-/var/log/mountos-conformance}"
TASKS="${TASKS:-1}"
ITER="${ITER:-1}"
export HOME="${HOME:-/root}"

# name|args|what it probes
COMBOS=(
"flat-wide|-n 10000 -F -C -T -r -w 0 -e 0|One directory, 10k zero-byte files. Single-directory scaling: lookup and readdir cost as a directory grows."
"flat-small|-n 2000 -F -C -T -r -w 0 -e 0|Same shape, smaller. A quick signal, and the one to run first."
"deep-tree|-z 10 -b 2 -I 10|Depth 10, branching 2. Path-traversal cost: every op walks ten levels."
"wide-tree|-z 2 -b 32 -I 10|Depth 2, branching 32. Many sibling directories rather than depth."
"shared-dir|-n 2000 -F -C -T -r -w 0 -e 0|All tasks in ONE directory. Concurrent create in a shared parent, which is where ownership and locking contention shows. Run with TASKS>1 or it proves nothing."
"unique-dir|-n 2000 -F -u -C -T -r -w 0 -e 0|Each task its own directory. The contention-free control for shared-dir; compare the two."
"with-data|-n 2000 -F -C -T -r -w 4096 -e 4096|4 KiB written and read per file. Separates pure metadata from the data path by contrast with flat-small."
"create-only|-n 5000 -F -C -w 0 -e 0|Create phase alone, no stat or remove. Isolates the create path."
"stat-only|-n 5000 -F -T -w 0 -e 0|Stat phase alone, against files created in the same run."
"remove-only|-n 5000 -F -r -w 0 -e 0|Remove phase alone. Deletion is often the slowest metadata op and the least measured."
"dirs-only|-n 2000 -D -C -T -r|Directories instead of files. Directory create/stat/remove is a different server path from files."
)
DEFAULT_SET=(flat-small flat-wide deep-tree shared-dir unique-dir)

list_combos() {
  printf '%-14s %s\n' "COMBINATION" "PROBES"
  printf '%-14s %s\n' "-----------" "------"
  for c in "${COMBOS[@]}"; do
    IFS='|' read -r n a d <<< "$c"
    printf '%-14s %s\n' "$n" "$d"
    printf '%-14s   args: %s\n' "" "$a"
  done
  echo
  echo "Default set: ${DEFAULT_SET[*]}"
  echo "TASKS=$TASKS (parallel MPI tasks; shared-dir needs >1 to mean anything)"
}

[ "${1:-}" = "--list" ] && { list_combos; exit 0; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }
mount | grep -q "on $MNT type fuse" || { echo "FATAL: $MNT is not a FUSE mount"; exit 1; }
command -v mdtest >/dev/null 2>&1 || { echo "FATAL: mdtest not found; run setup.sh"; exit 1; }

mkdir -p "$LOGDIR"
say() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGDIR/mdtest.log"; }

# mpirun when parallel is asked for. --oversubscribe so TASKS may exceed cores;
# --allow-run-as-root because this runs as root to reach the mount.
MPI=()
if [ "$TASKS" -gt 1 ]; then
  command -v mpirun >/dev/null 2>&1 || { echo "FATAL: TASKS=$TASKS needs mpirun; install openmpi"; exit 1; }
  MPI=(mpirun --allow-run-as-root --oversubscribe -n "$TASKS")
fi

args_for() {
  for c in "${COMBOS[@]}"; do
    IFS='|' read -r n a d <<< "$c"
    [ "$n" = "$1" ] && { echo "$a"; return 0; }
  done
  return 1
}

run_combo() {
  local name="$1" args
  args="$(args_for "$name")" || { say "unknown combination: $name (try --list)"; return 1; }
  local work="$MNT/mdtest-$name-$$"
  local out="$LOGDIR/mdtest-$name.txt"
  mkdir -p "$work" || { say "$name: cannot create $work"; return 1; }

  say "$name start (tasks=$TASKS)"
  # shellcheck disable=SC2086 # args is a deliberate word list
  "${MPI[@]}" mdtest -d "$work" -i "$ITER" $args > "$out" 2>&1
  local rc=$?

  # mdtest's SUMMARY block carries the per-operation rates; that is the result.
  if grep -q "SUMMARY" "$out"; then
    sed -n '/SUMMARY/,/^$/p' "$out" | sed 's/^/    /' | tee -a "$LOGDIR/mdtest.log"
  else
    say "$name: no SUMMARY in output, see $out"
    tail -5 "$out" | sed 's/^/    /'
  fi
  say "$name done rc=$rc ($out)"
  rm -rf "$work" 2>/dev/null
  return $rc
}

SUITES=("$@")
if [ ${#SUITES[@]} -eq 0 ]; then
  SUITES=("${DEFAULT_SET[@]}")
elif [ "${SUITES[0]}" = "--all" ]; then
  SUITES=(); for c in "${COMBOS[@]}"; do IFS='|' read -r n _ _ <<< "$c"; SUITES+=("$n"); done
fi

say "mdtest: ${SUITES[*]}"
overall=0
for s in "${SUITES[@]}"; do run_combo "$s" || overall=1; done
say "mdtest ALL DONE rc=$overall  logs in $LOGDIR"
exit $overall
