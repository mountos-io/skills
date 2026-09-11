# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

- **Major**: the guidance changes in a way that would make an agent following the previous
  version do the wrong thing.
- **Minor**: new sections, new suites, or materially expanded guidance.
- **Patch**: corrections, clarifications, and link fixes.

## 1.0.4

- `ltp-skip.txt`: added `ioctl_pidfd05`/`ioctl_pidfd06`. Both call `ioctl()`
  on a pidfd (a process file descriptor), not a file in the mount, so
  neither reaches the filesystem under test. Confirmed reproducible
  standalone against a Docker Desktop arm64 kernel: `ioctl_pidfd05` gets
  ENOTTY instead of EINVAL for `PIDFD_GET_INFO_SHORT`, `ioctl_pidfd06`
  gets EREMOTE instead of ESRCH for `PIDFD_GET_INFO`. A pidfd ioctl gap
  in that kernel, not filesystem behavior.

## 1.0.3

- Removed an em-dash sentence break and a negative-disclaimer sentence, restated as
  direct positive statements. No guidance change.

## 1.0.2

- Clarified that `--xattr`/`--ioctl`, not just `--acl`, are load-bearing: without
  `--xattr` on the mount, `setxattr`/`getxattr` return `ENOTSUP` and LTP's
  xattr/ACL test files fail in a way that reads like real syscall bugs. Same
  "flag-shaped failure that reads like a defect" trap `--acl` already documented
  for pjdfstest, one syscall family over.
- `run.sh`: added `check_xattr`, a one-second preflight before the LTP run
  (mirrors the existing `check_acl` preflight before pjdfstest), so a
  misconfigured mount fails fast with a clear remediation instead of burning a
  full LTP run on a flag problem.

## 1.0.1

- `setup.sh`: `dnf -y install ... curl ...` failed outright on a fresh AL2023
  instance whose mirror snapshot had accumulated enough past `curl-minimal` builds
  to make a plain `curl` install unresolvable, silently skipping the whole
  transaction. Fixed with `--allowerasing`.

## 1.0.0

First release. Written while running these suites against a real deployment from a
Linux client, so every trap below cost time before it was documented.

- Native, no container. The suites need no Docker on a Linux host; containers only
  help when driving them from macOS or Windows.
- `setup.sh` builds pjdfstest, LTP, and fsx on Debian/Ubuntu or RHEL-family hosts.
- `run.sh` runs them serialised against a mounted volume, with per-suite verdicts.
- **The `--acl` trap**, which is the headline. Without it a mode-0000 create is
  stored as 0644 and pjdfstest `open/26.t` fails in a way that reads exactly like a
  create-path defect. `run.sh` asserts this in one second before spending 84 on the
  suite.
- Three build traps that are not obvious: LTP upstream **removed** `runltp` in favour
  of `kirk` (which has no `--framework` argument); fsx must come from xfstests, not
  LTP's different `fsx-linux`, and has no standalone build because it needs the
  autoconf-generated `config.h`; and that configure chain needs
  `xfsprogs-devel`/`xfslibs-dev` or it aborts on a missing `xfs/xfs.h`.
- Result interpretation, including which reported failures are expected: the
  `unlink()`-on-directory TODO (mountOS returns EISDIR, matching Linux), `TODO
  passed` on `chown/00.t`, fsx capability probes, and LTP `TCONF` skips.
- Measured runtimes, with the caveat that fsx tracks storage locality far more than
  CPU, so runs are only comparable against a baseline with the same locality.
