#!/bin/bash
# Install the measurement tools: mdtest (metadata rates) and the dependencies the
# small-file workload needs.
#
# Self-contained on purpose. The skills in this repository install independently,
# so this cannot rely on the conformance skill's setup having run.
#
# Run as root. A few minutes; the IOR build dominates.
set -uo pipefail

PREFIX="${PREFIX:-/opt}"
IOR_VERSION="${IOR_VERSION:-4.0.0}"
LOG="${LOG:-/var/log/mountos-performance-setup.log}"
exec > >(tee -a "$LOG") 2>&1

say() { echo; echo "=== $* ==="; }
have() { command -v "$1" >/dev/null 2>&1; }

[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

say "packages"
if have apt-get; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    build-essential autoconf automake libtool pkg-config \
    git curl wget ca-certificates jq python3 \
    openmpi-bin libopenmpi-dev \
    nodejs npm >/dev/null
elif have dnf; then
  dnf -y group install "Development Tools" >/dev/null 2>&1 || \
    dnf -y groupinstall "Development Tools" >/dev/null 2>&1
  dnf -y install \
    autoconf automake libtool pkgconf-pkg-config \
    git curl wget ca-certificates jq python3 \
    openmpi openmpi-devel \
    nodejs npm >/dev/null
else
  echo "unsupported package manager; install the build deps by hand"; exit 1
fi

say "mdtest (ships with IOR)"
# mdtest is built as part of IOR, not as a separate project. MPI is what makes the
# parallel combinations possible; a serial build still runs every single-task one.
if ! have mdtest; then
  # RHEL-family installs openmpi under /usr/lib64/openmpi and does NOT put it on
  # PATH. Without this the configure below silently produces a serial build, and
  # the failure only surfaces later when a parallel combination refuses to run.
  for d in /usr/lib64/openmpi/bin /usr/lib/openmpi/bin; do
    [ -d "$d" ] && export PATH="$d:$PATH"
  done
  cd "$PREFIX" || exit 1
  rm -rf "ior-${IOR_VERSION}"
  wget -q "https://github.com/hpc/ior/releases/download/${IOR_VERSION}/ior-${IOR_VERSION}.tar.gz" -O ior.tgz \
    && tar xzf ior.tgz && cd "ior-${IOR_VERSION}" \
    && ./configure --prefix=/usr/local --with-posix >/dev/null 2>&1 \
    && make -j"$(nproc)" >/dev/null 2>&1 && make install >/dev/null 2>&1
fi

if have mdtest; then
  echo "  ok: $(command -v mdtest)"
  if have mpirun; then
    echo "  mpirun: $(command -v mpirun)"
  else
    echo "  NOTE: no mpirun on PATH. Single-task combinations work; the"
    echo "        shared-dir against unique-dir contention pair needs TASKS>1"
    echo "        and will be unavailable."
  fi
else
  echo "  FAILED"
fi

say "small-file workload deps"
for b in git npm node; do
  printf '  %-6s %s\n' "$b" "$(command -v "$b" || echo MISSING)"
done

say "done"
echo "log: $LOG"
