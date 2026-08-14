---
name: smallfiles
description: Measure small-file workload speed on a mounted mountOS volume, the shape a dependency install or source checkout produces. Use to time a git clone and an npm install against a mount, to compare a deployment against a local filesystem or an earlier run, or to size the per-file overhead of a network filesystem. This measures speed, not correctness; for correctness use the conformance skill.
version: 1.0.0
license: Apache-2.0
---

# mountOS small-file speed

Thousands of small files, created and read in bursts, is where a network filesystem
is most likely to disappoint. A dependency install or a source checkout is exactly
that shape, and it is a far better predictor of how a deployment will feel than a
sequential throughput number.

**This measures speed, not correctness.** There is no pass or fail. For correctness
use the `conformance` skill at https://github.com/mountos-io/skills, which runs
pjdfstest, LTP, and fsx and does have verdicts.

## Step 0: load the live context first

| Order | URL | What it gives you |
| --- | --- | --- |
| 1 | https://mountos.io/skills/volumes.md | Mount flags, forks, access keys |
| 2 | https://mountos.io/skills/env.md | Client tunables and what each one does |

## Ask before you measure

**Ask the operator which repository and which packages to use.** Their own codebase
and their own dependency set are the workload they care about. The defaults exist so
the script runs unattended, not because they represent anyone in particular.

```bash
sudo ./run.sh                                            # defaults
sudo GIT_REPO=https://github.com/you/yours.git ./run.sh
sudo NPM_PACKAGES="react react-dom vite" ./run.sh
```

The script reports wallclock and file count per phase: a shallow clone, an install
inside that repository, and a fresh install in an empty project.

## Mount configuration matters more here than in correctness testing

Correctness suites deliberately run with every cache disabled, so the kernel cannot
answer from stale attributes and hide a bug. **Do not do that here.** A
cache-disabled mount measures the worst case and tells you nothing about how the
deployment performs in normal use.

Measure with the caches the operator actually runs. If you are comparing two
deployments, or a deployment against a local disk, confirm both sides use the same
cache settings before believing any ratio between them.

## What makes a comparison meaningless

Four things, each of which silently invalidates a run:

1. **A populated `node_modules`.** npm then does almost nothing and the number is
   noise. Every run needs a fresh work root; `run.sh` creates one per invocation.
2. **A shared mount.** Another suite running against the same mount means you
   measured contention. Run this alone.
3. **A different network path.** A client inside the deployment's own network, or in
   another region, is not comparable to one that is not. State where the client sat.
4. **A cold versus warm cache.** The first run after a mount pays for cache fill.
   Compare like with like, or run twice and report both.

## Reading the result

There is no threshold to pass. What to look at:

- **Time per file, not total time.** A clone of 3,000 files and one of 300 are not
  comparable; divide.
- **Clone against install.** A clone is mostly writes in one pass. An install is
  writes plus many small reads, metadata lookups, and rename churn, so it is the
  harsher of the two and usually the one that exposes per-operation latency.
- **The same workload on local disk on the same host.** This is the single most
  useful comparison, because it isolates the filesystem from the machine.

A result that looks slow is usually one of: storage locality (the object store is
far from the client), a cache-disabled mount, or genuine per-file overhead. Rule out
the first two before concluding the third.

## Storage locality dominates

Object-store round trips, not CPU, set the pace for this workload. The same test
against distant object storage has been measured several times slower on faster
hardware.

So a runtime is only meaningful next to a baseline taken with the same storage
locality. A number without that context cannot be compared to anything, including a
later run of itself after someone moves a bucket.
