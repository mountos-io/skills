# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

## 1.0.3

- `mdtest.sh`: `deep-tree` walked to depth 10 (`-z 10`), deeper than the
  path lengths most deployments actually see. Reduced to depth 5 (`-z 5`)
  so the traversal cost measured matches typical directory nesting.

## 1.0.2

- `mosbench.py`: `wl_raw`'s writer built its per-file path from a bare,
  thread-local sequence counter (`f%d % seq[0]`) with no thread identity in
  it, unlike every other workload's own per-thread subdirectory
  (`wl_links`'s `d = wdir("links", "w%d" % idx)`). With more than one writer
  role thread (`--threads raw.writer=N > 1`), every writer counts through the
  same integer sequence independently and collides on identical filenames:
  one thread's `O_EXCL` create loses the race to another, and a reader that
  already dequeued the loser's `(path, tag, size)` can end up reading
  whichever thread's write actually landed there. That surfaced as a false
  `raw.stale_content` correctness counter, not a real filesystem defect --
  confirmed via a local repro where every mismatch's actual bytes exactly
  matched a *different*, genuinely valid write to the same bare path. Fixed
  by namespacing both the path and the tag by writer `idx`, mirroring
  `wl_links`'s already-correct pattern. Verified the fix eliminates the
  mismatch under the same stress conditions that reproduced it.
- `wl_raw` (`raw.stale_content`), `wl_links` (`links.symlink_content_mismatch`),
  and `wl_xattr` (`xattr.mismatch`) now log the specific path (and xattr key)
  plus expected-vs-actual size/content on a real mismatch, not just the
  aggregate counter. A correctness counter tripping used to leave no trail to
  follow; the path-collision bug above was found and root-caused using this
  same logging.

## 1.0.1

- `setup.sh`: `dnf -y install ... curl ...` failed outright on a fresh AL2023
  instance whose mirror snapshot had accumulated enough past `curl-minimal` builds
  to make a plain `curl` install unresolvable, silently skipping the whole
  transaction including `mdtest`. Fixed with `--allowerasing`.
- `mosbench.sh`: added the same `HOME` fallback its siblings already carry, for a
  non-login invocation (SSM `RunShellScript`, cron) where `HOME` is unset.

## 1.0.0

First release. Holds the measurement tools, which report rates and wallclock read
against a baseline. Correctness lives in `conformance`, which produces verdicts.

The split is verdict against measurement. mdtest first sat in `conformance` because
it is a filesystem test, but it reports operations per second and has no pass or
fail, so it belongs here with the other numbers.

- `mosbench.sh` / `mosbench.py`: eleven DIFFERENT workloads run concurrently, because
  a real system has a build, a log writer, a backup reader and a scanner competing at
  once and the interesting behaviour only appears under that mix. Reports latency
  percentiles per operation, and carries correctness counters alongside: holes read
  back as zero, nlink checked after linking, readdir sentinels that must never
  vanish, read-after-write content verified. A nonzero counter is a defect and
  outranks any latency number in the same run. No network fetch inside the timed
  section; the corpus is generated locally by an untimed prepare phase and is
  manifest-guarded so a seed or shape mismatch refuses to run.
  Written custom after surveying fio, smallfile, filebench, elbencho, compilebench,
  postmark, dbench and bonnie++: none covers the intersection of mixed concurrent
  workloads, no network, latency percentiles, and rename/link/xattr/readdir-under-
  mutation. fio remains the right tool for pure data-path throughput.
- `mdtest.sh`: metadata rates across eleven named directory shapes. Flat at two
  sizes, deep and wide trees, shared against unique parent directory, zero-byte
  against 4 KiB files, each phase in isolation, and directories rather than files.
  `--list` explains what each probes. The interesting results are PAIRS: shared
  against unique isolates contention, zero-byte against 4 KiB isolates what the data
  path adds. `shared-dir` is a no-op at one task and says so.
- `smallfiles.sh`: times a source checkout and a dependency install, carried over
  from the retired `smallfiles` skill. Documents its own limitation plainly, that
  both phases fetch from the network inside the timed section, so the clone figure
  is not a filesystem measurement.
