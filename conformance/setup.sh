#!/bin/bash
# Install and build the filesystem conformance suites natively on Linux:
# pjdfstest (POSIX conformance), LTP (syscalls), and fsx (data-path consistency).
#
# Native on purpose. These suites need no container on a Linux host; a container
# only helps when driving them from macOS or Windows.
#
# Run as root. Roughly ten minutes on 4 vCPU, dominated by LTP.
set -uo pipefail

PREFIX="${PREFIX:-/opt}"
LOG="${LOG:-/var/log/mountos-conformance-setup.log}"
exec > >(tee -a "$LOG") 2>&1

say() { echo; echo "=== $* ==="; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

say "packages"
if have apt-get; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    build-essential autoconf automake libtool pkg-config bison flex m4 \
    git curl ca-certificates jq \
    fuse3 libfuse3-dev acl libacl1-dev attr libattr1-dev \
    perl libtap-harness-archive-perl \
    libaio-dev libcap-dev libnuma-dev uuid-dev \
    xfslibs-dev libgdbm-dev python3 >/dev/null
elif have dnf; then
  dnf -y group install "Development Tools" >/dev/null 2>&1 || \
    dnf -y groupinstall "Development Tools" >/dev/null 2>&1
  # xfsprogs-devel is not optional: without <xfs/xfs.h> the xfstests configure
  # aborts, and fsx is built out of the xfstests tree.
  dnf -y install \
    autoconf automake libtool pkgconf-pkg-config bison flex m4 \
    git curl ca-certificates jq \
    fuse3 fuse3-devel acl libacl-devel attr libattr-devel \
    perl perl-Test-Harness perl-ExtUtils-MakeMaker \
    libaio-devel libcap-devel numactl-devel libuuid-devel \
    xfsprogs-devel e2fsprogs-devel gettext-devel python3 >/dev/null
else
  echo "unsupported package manager; install the build deps by hand"; exit 1
fi

for b in gcc make git autoreconf prove python3; do
  printf '  %-12s %s\n' "$b" "$(command -v "$b" || echo MISSING)"
done

say "fuse user_allow_other"
grep -q '^user_allow_other' /etc/fuse.conf 2>/dev/null || echo user_allow_other >> /etc/fuse.conf

say "unprivileged test users"
# pjdfstest needs real unprivileged uids to test permission semantics.
id nobody    >/dev/null 2>&1 || useradd -u 65534 -s /sbin/nologin nobody
id tests     >/dev/null 2>&1 || useradd -s /sbin/nologin tests
id pjdfstest >/dev/null 2>&1 || useradd -s /sbin/nologin pjdfstest

say "pjdfstest"
if [ ! -x "$PREFIX/pjdfstest/pjdfstest" ]; then
  rm -rf "$PREFIX/pjdfstest"
  git clone --depth 1 https://github.com/pjd/pjdfstest.git "$PREFIX/pjdfstest" 2>&1 | tail -1
  ( cd "$PREFIX/pjdfstest" && autoreconf -ifs >/dev/null 2>&1 && ./configure >/dev/null 2>&1 && make pjdfstest 2>&1 | tail -2 )
fi
[ -x "$PREFIX/pjdfstest/pjdfstest" ] && echo "  ok: $PREFIX/pjdfstest/pjdfstest" || echo "  FAILED"

say "fsx (from xfstests)"
# xfstests has no standalone fsx target: ltp/fsx includes src/global.h, which
# needs the autoconf-generated config.h, so the whole configure chain runs even
# though only one binary is wanted. This is xfstests' fsx, NOT LTP's fsx-linux;
# they are different programs and LTP's needs the LTP framework headers.
if [ ! -x /usr/local/bin/fsx ]; then
  rm -rf "$PREFIX/xfstests"
  git clone --depth 1 https://github.com/kdave/xfstests.git "$PREFIX/xfstests" 2>&1 | tail -1
  ( cd "$PREFIX/xfstests" \
      && make configure >/dev/null 2>&1 \
      && ./configure >/dev/null 2>&1 \
      && make -C include >/dev/null 2>&1 \
      && make -C lib >/dev/null 2>&1 \
      && make -C ltp fsx 2>&1 | tail -2 )
  cp "$PREFIX/xfstests/ltp/fsx" /usr/local/bin/fsx 2>/dev/null
fi
[ -x /usr/local/bin/fsx ] && echo "  ok: /usr/local/bin/fsx" || echo "  FAILED (is xfsprogs-devel/xfslibs-dev installed?)"

say "LTP syscalls"
if [ ! -d "$PREFIX/ltp/testcases/bin" ]; then
  rm -rf "$PREFIX/ltp-src"
  git clone --depth 1 https://github.com/linux-test-project/ltp.git "$PREFIX/ltp-src" 2>&1 | tail -1
  cd "$PREFIX/ltp-src" || exit 1
  make autotools >/dev/null 2>&1
  ./configure --prefix="$PREFIX/ltp" >/dev/null 2>&1
  # syscalls only: the full LTP tree is far larger than this harness needs.
  make -C testcases/kernel/syscalls -j"$(nproc)" >/dev/null 2>&1
  make -C testcases/kernel/syscalls install -j"$(nproc)" >/dev/null 2>&1
  for d in runtest lib testcases/lib; do make -C "$d" install >/dev/null 2>&1; done
fi
echo "  testcases: $(ls "$PREFIX/ltp/testcases/bin" 2>/dev/null | wc -l) binaries"

say "kirk (LTP runner)"
# Upstream REMOVED runltp; kirk replaces it. It has no --framework argument.
if [ ! -x "$PREFIX/kirk/kirk" ]; then
  rm -rf "$PREFIX/kirk"
  git clone --depth 1 https://github.com/linux-test-project/kirk.git "$PREFIX/kirk" 2>&1 | tail -1
fi
[ -x "$PREFIX/kirk/kirk" ] && echo "  ok: $PREFIX/kirk/kirk" || echo "  FAILED"

say "done"
echo "log: $LOG"
