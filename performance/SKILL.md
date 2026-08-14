---
name: performance
description: Measure mountOS performance against a baseline, on a mounted volume on Linux. Covers metadata operation rates with mdtest across directory shapes (flat, deep, wide, shared versus unique parent, phase isolation), and small-file workload timing. Use to size a deployment, to compare two configurations, or to track a regression between releases.
version: 1.0.0
license: Apache-2.0
---

# mountOS performance

Numbers, read against a baseline. Nothing here has a pass or fail; a result only
means something next to another result taken the same way.

To verify that the filesystem behaves correctly, use the `conformance` skill at
https://github.com/mountos-io/skills, which runs pjdfstest, LTP, and fsx and does
produce verdicts.

## Step 0: load the live context first

| Order | URL | What it gives you |
| --- | --- | --- |
| 1 | https://mountos.io/skills/volumes.md | Mount flags, forks, access keys |
| 2 | https://mountos.io/skills/env.md | Client tunables and what each one does |

## Measure the configuration the operator runs

Conformance suites deliberately disable every cache so the kernel cannot hide a bug
behind stale attributes. Measuring on that mount tells you about the worst case, not
about normal operation.

Use the flags and cache settings the deployment actually runs. When comparing two
deployments, or a deployment against local disk, confirm both sides use the same
cache settings before believing any ratio between them.

## Setup

`setup.sh` installs mdtest (built as part of IOR), MPI for the parallel
combinations, and the git and npm the workload timing needs. It is self-contained,
so it does not assume the conformance skill's setup has run.

```bash
sudo ./setup.sh
```

One trap it already handles: on RHEL-family hosts openmpi installs under
`/usr/lib64/openmpi/bin` and is not on `PATH`, so IOR's configure silently produces
a **serial** build. That failure only surfaces later, when a parallel combination
refuses to run. The script puts it on `PATH` first and reports whether `mpirun` is
present.

## What is here

| Tool | Measures |
| --- | --- |
| `mosbench.sh` | Eleven concurrent mixed workloads, with latency percentiles and correctness counters |
| `mdtest.sh` | Metadata operation rates: create, stat, remove, across directory shapes |
| `smallfiles.sh` | Wallclock for a source checkout and a dependency install |

## mdtest: the metadata layer

Metadata and data have very different costs on a network filesystem, and metadata is
usually what makes a deployment feel slow. `./mdtest.sh --list` prints every
combination with its arguments; the shapes and why each exists:

| Combination | Probes |
| --- | --- |
| `flat-small` | One directory, 2k zero-byte files. Quick signal; run first. |
| `flat-wide` | Same shape at 10k. Single-directory scaling as a directory grows. |
| `deep-tree` | Depth 10, branching 2. Path-traversal cost when every op walks ten levels. |
| `wide-tree` | Depth 2, branching 32. Many sibling directories rather than depth. |
| `shared-dir` | All tasks in ONE directory. Concurrent create in a shared parent, where ownership and locking contention shows. |
| `unique-dir` | Each task its own directory. The contention-free control for `shared-dir`. |
| `with-data` | 4 KiB per file. Separates pure metadata from the data path by contrast with `flat-small`. |
| `create-only`, `stat-only`, `remove-only` | One phase each. Remove is often the slowest and the least measured. |
| `dirs-only` | Directories rather than files, which is a different server path. |

**Ask the operator which shapes match their workload** before running everything. A
workload writing into one large directory cares about `flat-wide` and `shared-dir`;
a deep source tree cares about `deep-tree`. The default set covers common ground.

Two pairs carry most of the signal, and each is only meaningful as a pair:

- **`shared-dir` against `unique-dir`.** Same file count, same task count, differing
  only in whether tasks share a parent. The gap is contention cost. Run both at
  `TASKS=4` or higher; at `TASKS=1` they are the same test and the comparison is
  empty.
- **`flat-small` against `with-data`.** Same shape, zero-byte against 4 KiB files.
  The gap is what the data path adds on top of metadata.

Read mdtest's own SUMMARY block, which reports operations per second per phase.

```bash
sudo ./mdtest.sh --list
sudo ./mdtest.sh                      # default set
sudo TASKS=4 ./mdtest.sh shared-dir unique-dir
```

## mosbench: concurrent mixed workload

The tool of record for workload measurement. Eleven **different** workloads run at
the same time, because a real system has a build, a log writer, a backup reader and
a scanner competing at once, and the interesting behaviour only appears under that
mix.

```bash
sudo ./mosbench.sh /mnt/mountos          # prepare corpus, run the mix, report
sudo ./mosbench.sh --list                # what each workload probes
```

| Workload | Exercises |
| --- | --- |
| `rename` | same-dir, cross-dir, and replace-existing rename, each a distinct metadata transaction |
| `links` | hardlink, symlink, readlink, resolution through a symlink, nlink accounting |
| `trunc` | truncate extend and shrink, sparse far writes, and holes that must read as zero |
| `append` | append-heavy writes with an fsync boundary, rotation, and a live tailer on a growing inode |
| `xattr` | xattr set, get, list, remove against the metadata service |
| `readdir` | one lister against two mutators, with sentinels that must never disappear |
| `raw` | read-after-write, counting ENOENT and stale content |
| `openclose` | open and close churn |
| `deep` | traversal of depth-20 paths |
| `walk` | a full scanner as a noisy neighbour |
| `churn` | create and unlink storms |

Two properties make this worth more than a throughput number:

- **It reports latency distribution, not just aggregate rate.** Tail latency is what
  users feel on a network filesystem, so p50 and p90 are the comparison metrics.
- **It carries correctness counters alongside the timings.** Holes are read back and
  must be zero, nlink is checked after linking, readdir sentinels must never vanish,
  and read-after-write verifies content. A `correctness counters: CLEAN` line means
  the mix found no data or metadata error while it measured. Any nonzero counter is
  a defect, and matters more than any latency number in the same run.

**No network fetch inside the timed section.** The corpus is generated locally by a
`prepare` phase that runs untimed, and it is manifest-guarded, so a seed or shape
mismatch refuses to run rather than silently comparing two different tests.

Compare runs with `mosbench.py compare a/results.json b/results.json`, which judges
only the stable metrics and always fails on a nonzero correctness counter.

### Which numbers to trust

Stable enough to compare run to run, given the same seed, mix, duration, host, and
cache settings: **count, ops/s, p50, p90**.

Noisy, read with judgment: **p99**. And **max is a single sample**, so it is never a
regression on its own.

### Why this is custom rather than an off-the-shelf tool

No existing tool covers the intersection. `fio` has excellent percentiles and does
run mixed jobs concurrently, but it has no engine for rename, hardlink, symlink,
xattr, or listing a directory while it mutates, and its `filecreate`/`filestat`/
`filedelete` engines do one operation per job. `smallfile` has the right operation
vocabulary but takes a single operation per invocation, so it cannot produce a mix.
`filebench` is built for mixed personalities but is effectively unmaintained, needs
ASLR disabled, and is not packaged for these hosts. `elbencho` is maintained and has
percentiles but runs phases sequentially and has no rename, link, or xattr.

For pure data-path throughput questions, `fio` remains the right tool and this does
not replace it.

## smallfiles: a source checkout and a dependency install

Times a shallow git clone and two npm installs against the mount.

```bash
sudo ./smallfiles.sh
sudo GIT_REPO=https://github.com/you/yours.git ./smallfiles.sh
```

**Ask the operator for their own repository and packages.** Their codebase is the
workload they care about; the defaults exist so the script runs unattended.

**Known limitation, and it is a real one.** Both phases fetch from the network
inside the timed section, so the result includes GitHub and npm registry latency,
not only filesystem time. On a small repository that download dominates and the
clone figure says little about the mount. Treat the two npm phases as the
comparable pair and ignore the clone number for filesystem purposes.

The comparison worth making is whether files-per-second **holds** as the tree grows:
the in-repo install pulls a full dev-dependency tree, the fresh one only runtime
deps, so the first is several times larger. Roughly equal rates mean cost is scaling
linearly with file count. A markedly slower rate on the larger tree means something
degrades with directory size or depth, which is the more interesting finding.

## What makes a comparison meaningless

Each of these silently invalidates a run:

1. **A populated `node_modules`,** which turns npm into a no-op. Every run needs a
   fresh work root; `smallfiles.sh` creates one per invocation.
2. **A shared mount.** Another suite against the same mount means you measured
   contention. Run one thing at a time.
3. **A different network path.** A client inside the deployment's own network, or in
   another region, is not comparable to one outside it. State where the client sat.
4. **Cold against warm cache.** The first run after a mount pays for cache fill.
   Compare like with like, or run twice and report both.

## Storage locality dominates

Object-store round trips, not CPU, set the pace for these workloads. The same test
against distant object storage has been measured several times slower on faster
hardware.

A runtime is therefore only meaningful next to a baseline taken with the same
storage locality. A number without that context cannot be compared to anything,
including a later run of itself after someone moves a bucket.
