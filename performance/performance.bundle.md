# mountOS performance skill (single-file bundle, version 1.0.0)

This file is the entire skill in one document: the entry point followed by every
reference it links to. It exists for agents that cannot follow relative links or read
a directory. The links below point at sections in this same file.

Source and updates: https://github.com/mountos-io/skills

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
