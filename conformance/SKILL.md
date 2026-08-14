---
name: conformance
description: Run filesystem conformance and data-integrity suites against a mounted mountOS volume on Linux. Use to verify a deployment with pjdfstest (POSIX conformance), LTP syscalls, and fsx (data-path consistency); to set up those suites natively on a fresh Linux host; or to interpret their results, including which reported failures are configuration rather than defects.
version: 1.0.0
license: Apache-2.0
---

# mountOS conformance testing

Prove a mountOS deployment behaves like a filesystem, using the standard suites the
rest of the world uses: **pjdfstest** for POSIX conformance, **LTP** for syscall
coverage, and **fsx** for data-path consistency.

These are third-party suites. mountOS does not grade its own homework here; a pass
means the same thing it means for ext4 or XFS.

## Step 0: load the live context first

| Order | URL | What it gives you |
| --- | --- | --- |
| 1 | https://mountos.io/skills/volumes.md | Mount flags, forks, access keys |
| 2 | https://mountos.io/ai/topics/troubleshooting.md | Symptom-indexed fixes if a mount misbehaves |
| 3 | https://mountos.io/skills/env.md | What a client variable does |

Where this repository and the live documentation disagree, the live documentation
wins.

## The flag that decides whether pjdfstest passes

**Mount with `--acl` or pjdfstest `open/26.t` will fail, and the failure looks
exactly like a POSIX bug.**

`open(path, O_CREAT, 0000)` must create a file with mode `0000`. Without `--acl`,
mountOS stores that as `0644`, because a zero mode is treated as "unset" and a
default applied. `--acl` (and `--umask`, and the explicit `--null-permissions`)
turn on exact mode preservation.

Every non-zero mode round-trips correctly either way, so the symptom is narrow and
easy to misread as a create-path defect. Check the mount flags before you file a
bug. A one-line assertion catches it in a second rather than after an 84-second
suite run:

```bash
python3 -c 'import os;os.close(os.open(".m",os.O_CREAT|os.O_WRONLY,0o000))'
stat -c %a .m   # want 0, not 644
rm -f .m
```

## Conformance mount

Cache TTLs are all zero on purpose. With caches on, the kernel answers from its own
attribute cache and a real coherence bug stays invisible; the suite then measures
the kernel rather than the filesystem.

```bash
mountos mount /mnt/mountos \
  --foreground \
  --meta-open-connections 4 \
  --attr-cache 0 --entry-cache 0 --dir-entry-cache 0 --negative-entry-cache 0 \
  --disable-cache-dir \
  --xattr --ioctl --acl \
  -o allow_other,allow_root,default_permissions
```

Credentials come from `MOUNTOS_ACCESS_KEY_ID`, `MOUNTOS_SECRET_ACCESS_KEY`, and
`MOUNTOS_DISCOVERY_URL`. Two environment notes that cost real time when missed:

- **`HOME` must be set.** Under a root shell with no `HOME` (a remote command
  runner, some CI agents) the client cannot resolve its cache directory and the
  mount fails with `no readiness signal`, which does not name the cause.
- **Run the suites on a machine outside the deployment's own network.** Discovery
  hands the client the cluster's client-facing address, and most clouds do not
  route an instance's public address back inside the same virtual network.

To keep test data out of a real volume's main fork, add `--fork-name <name>` or a
temporary fork.

## Setup

`setup.sh` in this directory installs the dependencies and builds all three suites.
It supports Debian/Ubuntu and RHEL-family hosts. Roughly ten minutes on 4 vCPU,
dominated by LTP.

```bash
sudo ./setup.sh
```

What it builds, and the traps it already handles:

| Suite | Source | Trap |
| --- | --- | --- |
| pjdfstest | github.com/pjd/pjdfstest | Needs the binary staged INSIDE the mount; the tests resolve it relatively |
| LTP | github.com/linux-test-project/ltp | `runltp` was REMOVED upstream. The runner is now `kirk`, which has no `--framework` argument |
| fsx | xfstests (`ltp/fsx`) | No standalone build: it includes `src/global.h`, which needs the autoconf-generated `config.h`, so the full configure chain runs. Needs `xfsprogs-devel`/`xfslibs-dev` or `configure` fails on a missing `xfs/xfs.h` |

Note fsx here is **xfstests'** fsx, not LTP's `fsx-linux`. They are different
programs with different flags; LTP's variant also needs the LTP test framework
headers and will not build standalone.

## Running

```bash
sudo ./run.sh              # pjdfstest, fsx, LTP, serialised
sudo ./run.sh pjdfstest    # just one
```

**Serialise them.** They share one mount, so running two at once makes latency and
throughput numbers meaningless and can trip LTP's own timeouts on load rather than
on a real hang.

## Reading the results

### pjdfstest

Pass is exit 0 with no `not ok` outside the known TODO. Expect **one** TODO for
`unlink()` on a directory: mountOS returns `EISDIR`, matching Linux, where POSIX
allows `EPERM`. That is a deliberate alignment, not a regression.

`chown/00.t` reporting `TODO passed` is also fine. It means the implementation is
better than the test expected, and prove counts it separately from a failure.

### fsx

fsx keeps an in-memory oracle of what the file should contain and exits non-zero
with an offset and length on the first divergence. A clean run prints:

```
All 100000 operations completed A-OK!
```

Any of `BAD DATA`, `SHORT READ`, or `OFFSET MISMATCH` is a real data-path defect
worth stopping for. Use a fresh random seed each run; reuse a seed only to
reproduce a known failure.

fsx reports `filesystem does not support ...` lines at startup for dedupe range,
exchange range, dontcache, and atomic writes. Those are capability probes, not
failures; fsx disables the op class and continues.

### LTP

`TCONF` means skipped, not failed. Expect a substantial number on any container or
non-x86 host: architecture-gated tests, missing kernel features, absent security
modules. Judge on failures, not on skips.

## Interpreting a failure

Before filing anything, rule out the two cheap causes:

1. **Mount configuration.** Re-read the flags above. `--acl` alone accounts for a
   pjdfstest failure that reads exactly like a create-path bug.
2. **The test host.** Confirm the suite passes on a local filesystem on the same
   host. If it fails there too, the finding is about the host, not mountOS.

Then narrow the layer: does it reproduce on a second client, on a second volume,
with caches enabled? A failure that only appears with caches off is a coherence
question; one that appears either way is a correctness question.

For deeper diagnosis, use the `troubleshoot` skill at
https://github.com/mountos-io/skills. For metadata rates and workload timing, which
report numbers rather than verdicts, use the `performance` skill in the same
repository.

## Measured runtimes

From a 4 vCPU aarch64 host against a same-region deployment:

| Suite | Wallclock | Scale |
| --- | --- | --- |
| pjdfstest `-j 4` | ~85 s | 8798 tests, 238 files |
| fsx | ~22 min | 100k ops, 256 KiB file |
| LTP syscalls | tens of minutes | ~4000 tests |

fsx runtime is dominated by object-store round trips, so it tracks storage
locality far more than CPU. The same suite against distant object storage has been
measured several times slower on faster hardware. Compare runs only against a
baseline taken with the same storage locality.
