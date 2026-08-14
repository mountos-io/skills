# mountOS smallfiles skill (single-file bundle, version 1.0.0)

This file is the entire skill in one document: the entry point followed by every
reference it links to. It exists for agents that cannot follow relative links or read
a directory. The links below point at sections in this same file.

Source and updates: https://github.com/mountos-io/skills

---


# mountOS small-file speed

Thousands of small files, created and read in bursts, is where a network filesystem
is most likely to disappoint. A dependency install or a source checkout is exactly
that shape, and it is a far better predictor of how a deployment will feel than a
sequential throughput number.

This is a measurement. Read it against a baseline: the same workload on local disk
on the same host, or an earlier run of the same deployment. To verify behaviour
instead, use the `conformance` skill at https://github.com/mountos-io/skills.

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

## Measure the configuration the operator runs

Use the mount flags and cache settings the deployment actually uses in normal
operation. That is the configuration whose speed they care about, and it is the one
a result should describe.

When comparing two deployments, or a deployment against local disk, confirm both
sides use the same cache settings before believing any ratio between them.

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

Three comparisons carry the signal:

- **Time per file, not total time.** A clone of 3,000 files and one of 300 are not
  comparable; divide.
- **The two installs against each other, not against the clone.** The clone phase
  includes downloading the repository from the network, which is not filesystem
  work; on a small repository that download dominates and the resulting rate says
  little about the mount. The two npm phases are the comparable pair.
- **Whether the rate holds as the tree grows.** The in-repo install pulls a full
  dev-dependency tree and the fresh one pulls only runtime deps, so the first is
  several times larger. If files-per-second is roughly equal across both, cost is
  scaling linearly with file count. If the larger tree is markedly slower per file,
  something is degrading with directory size or depth, which is the more
  interesting finding.
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
