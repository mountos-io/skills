#!/usr/bin/env python3
"""
mosbench: concurrent mixed small-file and metadata workload for a mounted
network filesystem.

Eleven different workloads run at the same time against one directory tree:
an append-heavy log writer, a rename churner, a link farm, a truncate and
sparse-file worker, an xattr worker, a directory lister racing mutators,
a read-after-write pipeline, an open/close churner, a deep-path walker,
a full-tree metadata scanner, and a create/delete storm. The point of the
mix is that real hosts run a compile job, a log writer, a backup reader and
a scanner at once, and the interesting tail latencies only appear under
that interference.

Everything the run touches is generated locally before the timed window
(`prepare`), so no byte crosses the internet during measurement. Every
random choice derives from one seed, so two runs with the same seed and
shape are comparable. Results are per-operation latency distributions
(p50/p90/p99/max) plus ops/s, emitted as text and JSON; `compare` diffs
two JSON results and flags regressions on the stable metrics only.

Threads, not processes: every operation here is a filesystem syscall that
releases the GIL, and on a network filesystem per-op latency (0.1 ms to
tens of ms) dwarfs interpreter overhead (single-digit us). Threads keep
result aggregation and shared queues trivial.

Stdlib only, Python 3.8+, Linux first (xattr needs os.setxattr; the
workload self-disables elsewhere so the tool still runs on macOS for
development).
"""

import argparse
import hashlib
import json
import math
import os
import platform
import queue
import random
import shutil
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

TOOL_VERSION = "1.0.0"
SCHEMA = "mosbench/1"

# Corpus shape constants. Changing any of these changes what the numbers mean,
# so they are baked into the manifest and a mismatch refuses to run: silently
# comparing runs against different corpus shapes is how bad baselines happen.
POOL_DIRS = 40
POOL_FILES = 50          # per dir; 2000 files total
POOL_SIZES = [1024, 2048, 4096, 8192, 16384, 32768, 65536]
DEEP_CHAINS = 8
DEEP_DEPTH = 20
# Grace period for workers to notice the stop flag and exit. Shared across all
# threads, so a hung mount costs this once rather than once per thread.
JOIN_GRACE_S = 60
SENTINELS = 100

SPARSE_LEN = 8 * 1024 * 1024
APPEND_ROTATE = 8 * 1024 * 1024
APPEND_FSYNC_EVERY = 16
CHURN_BATCH = 100
ERROR_BACKOFF_S = 0.05   # a dead mount must not turn into a CPU-bound error loop


# ---------------------------------------------------------------------------
# latency histogram
#
# Log-spaced buckets, 40 per decade (about 6% relative width), spanning
# 0.1 us to 1000 s. Constant memory regardless of op count, so an hour-long
# run cannot exhaust RAM, and 6% resolution is far below run-to-run noise.
# ---------------------------------------------------------------------------

BPD = 40
LOW_US = 0.1
NBUCKETS = BPD * 10 + 1


class Hist:
    __slots__ = ("buckets", "count", "total_us", "min_us", "max_us")

    def __init__(self):
        self.buckets = [0] * NBUCKETS
        self.count = 0
        self.total_us = 0.0
        self.min_us = math.inf
        self.max_us = 0.0

    def add(self, us):
        if us <= LOW_US:
            i = 0
        else:
            i = min(NBUCKETS - 1, 1 + int(BPD * math.log10(us / LOW_US)))
        self.buckets[i] += 1
        self.count += 1
        self.total_us += us
        if us < self.min_us:
            self.min_us = us
        if us > self.max_us:
            self.max_us = us

    def merge(self, other):
        for i, c in enumerate(other.buckets):
            self.buckets[i] += c
        self.count += other.count
        self.total_us += other.total_us
        self.min_us = min(self.min_us, other.min_us)
        self.max_us = max(self.max_us, other.max_us)

    def percentile(self, p):
        if self.count == 0:
            return 0.0
        rank = max(1, math.ceil(self.count * p / 100.0))
        seen = 0
        for i, c in enumerate(self.buckets):
            seen += c
            if seen >= rank:
                # Report the bucket's upper edge: conservative, and stable
                # across runs because edges are fixed, not data-dependent.
                hi = LOW_US * (10 ** (i / BPD))
                return min(max(hi, self.min_us), self.max_us)
        return self.max_us


class Recorder:
    """Per-thread sink. No locks on the hot path; merged once after join."""

    def __init__(self, record_event):
        self.record = record_event
        self.hists = {}
        self.errors = {}
        self.counters = {}

    def add(self, op, us):
        # Samples before the warmup boundary are dropped: they measure cache
        # fill and thread ramp-up, not steady state, and poison the median.
        if not self.record.is_set():
            return
        h = self.hists.get(op)
        if h is None:
            h = self.hists[op] = Hist()
        h.add(us)

    def err(self, op):
        # Errors count for the whole run including warmup: an error during
        # warmup is still an error worth seeing.
        self.errors[op] = self.errors.get(op, 0) + 1

    def count(self, name, n=1):
        self.counters[name] = self.counters.get(name, 0) + n


def timeit(rec, op, fn):
    t0 = time.perf_counter_ns()
    v = fn()
    rec.add(op, (time.perf_counter_ns() - t0) / 1000.0)
    return v


# ---------------------------------------------------------------------------
# deterministic content
# ---------------------------------------------------------------------------

def filler_block(seed, tag, size=1024):
    """Deterministic bytes from (seed, tag). sha256 chaining because it is
    fast enough in pure Python and reproducible across platforms, unlike
    random module byte generation across Python versions."""
    out = b""
    h = ("%s:%s" % (seed, tag)).encode()
    while len(out) < size:
        h = hashlib.sha256(h).digest()
        out += h
    return out[:size]


def deep_path(corpus, chain):
    parts = [corpus, "deep", "c%d" % chain]
    parts += ["l%02d" % l for l in range(1, DEEP_DEPTH + 1)]
    parts.append("payload")
    return os.path.join(*parts)


def pool_path(corpus, di, fi):
    return os.path.join(corpus, "pool", "d%03d" % di, "f%03d" % fi)


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------

def corpus_shape():
    return {
        "pool_dirs": POOL_DIRS,
        "pool_files": POOL_FILES,
        "pool_sizes": POOL_SIZES,
        "deep_chains": DEEP_CHAINS,
        "deep_depth": DEEP_DEPTH,
        "sentinels": SENTINELS,
    }


def manifest_path(root):
    return os.path.join(root, "manifest.json")


def load_manifest(root):
    try:
        with open(manifest_path(root)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def prepare_corpus(root, seed, log=print):
    """Build the fixed tree the workloads read. Runs entirely OUTSIDE the
    timed window. Reused across runs when seed and shape match; the manifest
    is written last so a crashed prepare is simply rebuilt."""
    want = {"schema": SCHEMA, "seed": seed, "shape": corpus_shape()}
    have = load_manifest(root)
    if have is not None:
        if have.get("seed") == seed and have.get("shape") == corpus_shape():
            log("corpus: reusing existing tree at %s" % root)
            return
        raise SystemExit(
            "corpus at %s was built with a different seed or shape "
            "(seed=%r). Run 'clean' first, then rerun." % (root, have.get("seed")))

    t0 = time.perf_counter()
    corpus = os.path.join(root, "corpus")
    rng = random.Random("%s:pool" % seed)
    nfiles = 0
    for di in range(POOL_DIRS):
        os.makedirs(os.path.join(corpus, "pool", "d%03d" % di), exist_ok=True)
        for fi in range(POOL_FILES):
            size = rng.choice(POOL_SIZES)
            block = filler_block(seed, "pool/d%03d/f%03d" % (di, fi))
            with open(pool_path(corpus, di, fi), "wb") as f:
                f.write(block * (size // len(block)))
            nfiles += 1

    for c in range(DEEP_CHAINS):
        p = deep_path(corpus, c)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(filler_block(seed, "deep/%d" % c, 4096))

    lst = os.path.join(corpus, "listdir")
    os.makedirs(lst, exist_ok=True)
    for i in range(SENTINELS):
        with open(os.path.join(lst, "s_%03d" % i), "wb") as f:
            f.write(filler_block(seed, "sentinel/%d" % i, 128))

    with open(manifest_path(root), "w") as f:
        json.dump(want, f, indent=1)
    log("corpus: built %d pool files, %d deep chains, %d sentinels in %.1fs (untimed)"
        % (nfiles, DEEP_CHAINS, SENTINELS, time.perf_counter() - t0))


# ---------------------------------------------------------------------------
# run context
# ---------------------------------------------------------------------------

class Ctx:
    def __init__(self, root, seed):
        self.root = root
        self.corpus = os.path.join(root, "corpus")
        self.work = os.path.join(root, "work")
        self.seed = seed
        self.stop = threading.Event()
        self.record = threading.Event()
        self.shared = {}
        self.fatal = []
        self.fatal_lock = threading.Lock()

    def rng(self, wl, role, idx):
        return random.Random("%s:%s:%s:%d" % (self.seed, wl, role, idx))

    def wdir(self, *parts):
        p = os.path.join(self.work, *parts)
        os.makedirs(p, exist_ok=True)
        return p


def run_loop(ctx, rec, errop, step):
    while not ctx.stop.is_set():
        try:
            step()
        except OSError:
            rec.err(errop)
            time.sleep(ERROR_BACKOFF_S)


# ---------------------------------------------------------------------------
# workloads
# ---------------------------------------------------------------------------

def wl_rename(ctx, rec, role, idx):
    a = ctx.wdir("rename", "w%d" % idx, "a")
    b = ctx.wdir("rename", "w%d" % idx, "b")
    payload = filler_block(ctx.seed, "rename", 512)
    seq = [0]

    def step():
        seq[0] += 1
        n = seq[0]
        src = os.path.join(a, "f%d" % n)
        mid = os.path.join(a, "g%d" % n)
        dst = os.path.join(b, "g%d" % n)

        def create(path):
            fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o644)
            try:
                os.write(fd, payload)
            finally:
                os.close(fd)

        timeit(rec, "rename.create", lambda: create(src))
        timeit(rec, "rename.same_dir", lambda: os.rename(src, mid))
        if n % 8 == 0:
            # Rename onto an existing target: the replace path is a different
            # server transaction (old target unlink folded in) than a fresh
            # cross-directory move, and is where lost-unlink bugs hide.
            create(dst)
            timeit(rec, "rename.cross_dir_replace", lambda: os.rename(mid, dst))
        else:
            timeit(rec, "rename.cross_dir", lambda: os.rename(mid, dst))
        timeit(rec, "rename.unlink", lambda: os.unlink(dst))

    run_loop(ctx, rec, "rename.step", step)


def wl_links(ctx, rec, role, idx):
    d = ctx.wdir("links", "w%d" % idx)
    payload = filler_block(ctx.seed, "links", 256)
    seq = [0]

    def step():
        seq[0] += 1
        n = seq[0]
        tgt = os.path.join(d, "t%d" % n)
        hrd = os.path.join(d, "h%d" % n)
        sym = os.path.join(d, "s%d" % n)
        with open(tgt, "wb") as f:
            f.write(payload)
        timeit(rec, "links.hardlink", lambda: os.link(tgt, hrd))
        st = timeit(rec, "links.stat_target", lambda: os.stat(tgt))
        rec.count("links.nlink_checked")
        if st.st_nlink != 2:
            # A wrong link count is a metadata consistency bug, not slowness.
            rec.count("links.bad_nlink")
        # Relative symlink target so resolution stays inside the directory
        # and measures traversal, not an absolute-path shortcut.
        timeit(rec, "links.symlink", lambda: os.symlink("t%d" % n, sym))
        timeit(rec, "links.readlink", lambda: os.readlink(sym))

        def open_follow():
            with open(sym, "rb") as f:
                return f.read(len(payload))

        data = timeit(rec, "links.open_via_symlink", open_follow)
        if data != payload:
            rec.count("links.symlink_content_mismatch")
        for p in (hrd, sym, tgt):
            timeit(rec, "links.unlink", lambda p=p: os.unlink(p))

    run_loop(ctx, rec, "links.step", step)


def wl_trunc(ctx, rec, role, idx):
    d = ctx.wdir("trunc", "w%d" % idx)
    head = filler_block(ctx.seed, "trunc", 4096)
    seq = [0]

    def step():
        seq[0] += 1
        p = os.path.join(d, "f%d" % seq[0])
        fd = os.open(p, os.O_CREAT | os.O_RDWR | os.O_EXCL, 0o644)
        try:
            os.write(fd, head)
            timeit(rec, "trunc.extend", lambda: os.ftruncate(fd, SPARSE_LEN))
            timeit(rec, "trunc.far_write",
                   lambda: os.pwrite(fd, head, SPARSE_LEN // 2))
            data = timeit(rec, "trunc.hole_read",
                          lambda: os.pread(fd, 4096, SPARSE_LEN // 4))
            rec.count("trunc.hole_checked")
            if any(data):
                # A hole must read as zeros; anything else means the extend
                # exposed stale data, which on an object-backed store is a
                # real failure mode worth a dedicated counter.
                rec.count("trunc.nonzero_hole")
            timeit(rec, "trunc.shrink", lambda: os.ftruncate(fd, 1024))
            if os.fstat(fd).st_size != 1024:
                rec.count("trunc.bad_size_after_shrink")
        finally:
            os.close(fd)
        os.unlink(p)

    run_loop(ctx, rec, "trunc.step", step)


def wl_append(ctx, rec, role, idx):
    d = ctx.wdir("append")
    if role == "writer":
        _append_writer(ctx, rec, d, idx)
    else:
        _append_tailer(ctx, rec, d)


def _append_writer(ctx, rec, d, idx):
    path = os.path.join(d, "w%d.log" % idx)
    filler = filler_block(ctx.seed, "append", 160)
    state = {"fd": os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644),
             "written": 0, "seq": 0}

    def step():
        state["seq"] += 1
        line = b"%d %d " % (idx, state["seq"]) + filler + b"\n"
        n = timeit(rec, "append.write", lambda: os.write(state["fd"], line))
        state["written"] += n
        if state["seq"] % APPEND_FSYNC_EVERY == 0:
            # fsync is the durability boundary: metadata commit plus data
            # flush. Its latency is what a database or log daemon feels.
            timeit(rec, "append.fsync", lambda: os.fsync(state["fd"]))
        if state["written"] >= APPEND_ROTATE:
            os.close(state["fd"])
            # Rotation renames a live, recently synced file, replacing the
            # previous generation: rename-over-existing on a hot inode.
            timeit(rec, "append.rotate", lambda: os.rename(path, path + ".old"))
            state["fd"] = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
            state["written"] = 0

    try:
        run_loop(ctx, rec, "append.step", step)
    finally:
        try:
            os.close(state["fd"])
        except OSError:
            pass


def _append_tailer(ctx, rec, d):
    """Concurrent reader against an active writer on the same inode. Measures
    how quickly appended bytes and the growing size become visible."""
    path = os.path.join(d, "w0.log")
    state = {"fd": None, "off": 0, "iters": 0}

    def reopen():
        # Invalidate before opening: if the open fails mid-rotation, a stale
        # closed descriptor left in state would EBADF every following fstat.
        if state["fd"] is not None:
            try:
                os.close(state["fd"])
            except OSError:
                pass
            state["fd"] = None
        fd = os.open(path, os.O_RDONLY)
        state["fd"] = fd
        # After rotation the path is a new, smaller inode; restart the tail.
        if os.fstat(fd).st_size < state["off"]:
            state["off"] = 0

    def step():
        state["iters"] += 1
        # The writer rotates by rename, which leaves this fd on the old
        # inode where no new data will ever arrive. Periodic reopen is the
        # only way to notice without inotify.
        if state["fd"] is None or state["iters"] % 400 == 0:
            try:
                if state["fd"] is None:
                    reopen()
                else:
                    timeit(rec, "append.tail_reopen", reopen)
            except FileNotFoundError:
                # Rotation window: the log was renamed away and the writer
                # has not recreated it yet. Not an error, retry shortly.
                time.sleep(0.005)
                return
        st = timeit(rec, "append.tail_stat", lambda: os.fstat(state["fd"]))
        if st.st_size > state["off"]:
            want = min(65536, st.st_size - state["off"])
            data = timeit(rec, "append.tail_read",
                          lambda: os.pread(state["fd"], want, state["off"]))
            state["off"] += len(data)
        else:
            time.sleep(0.002)

    try:
        run_loop(ctx, rec, "append.tail_step", step)
    finally:
        if state["fd"] is not None:
            try:
                os.close(state["fd"])
            except OSError:
                pass


def wl_xattr(ctx, rec, role, idx):
    d = ctx.wdir("xattr")
    files = []
    for k in range(16):
        p = os.path.join(d, "x%d_%d" % (idx, k))
        with open(p, "wb") as f:
            f.write(b"x" * 64)
        files.append(p)
    rng = ctx.rng("xattr", role, idx)

    def step():
        p = files[rng.randrange(len(files))]
        key = "user.mos%d" % rng.randrange(4)
        val = filler_block(ctx.seed, "xattr/%d" % rng.randrange(1024), 64)
        timeit(rec, "xattr.set", lambda: os.setxattr(p, key, val))
        got = timeit(rec, "xattr.get", lambda: os.getxattr(p, key))
        rec.count("xattr.roundtrips")
        if got != val:
            rec.count("xattr.mismatch")
        timeit(rec, "xattr.list", lambda: os.listxattr(p))
        if rng.random() < 0.25:
            timeit(rec, "xattr.remove", lambda: os.removexattr(p, key))

    run_loop(ctx, rec, "xattr.step", step)


def wl_readdir(ctx, rec, role, idx):
    d = os.path.join(ctx.corpus, "listdir")
    if role == "lister":
        def step():
            names = timeit(rec, "readdir.list",
                           lambda: [e.name for e in os.scandir(d)])
            rec.count("readdir.lists")
            seen = sum(1 for n in names if n.startswith("s_"))
            if seen < SENTINELS:
                # Sentinels are never deleted, so any listing that misses one
                # dropped a stable entry while the directory was mutating.
                rec.count("readdir.missing_sentinel")
        run_loop(ctx, rec, "readdir.list_step", step)
        return

    payload = filler_block(ctx.seed, "readdir", 128)
    own = deque()
    seq = [0]

    def step():
        seq[0] += 1
        p = os.path.join(d, "m%d_%d" % (idx, seq[0]))

        def create():
            with open(p, "wb") as f:
                f.write(payload)

        timeit(rec, "readdir.mutate_create", create)
        own.append(p)
        # Bound the directory so its size reaches a steady state instead of
        # growing without limit and making listing latency a moving target.
        if len(own) > 150:
            old = own.popleft()
            timeit(rec, "readdir.mutate_unlink", lambda: os.unlink(old))

    run_loop(ctx, rec, "readdir.mutate_step", step)


def wl_raw(ctx, rec, role, idx):
    d = ctx.wdir("raw")
    q = ctx.shared["raw.q"]
    if role == "writer":
        rng = ctx.rng("raw", role, idx)
        filler = filler_block(ctx.seed, "raw", 16384)
        seq = [0]

        def step():
            seq[0] += 1
            size = rng.choice((1024, 2048, 4096, 8192, 16384))
            tag = b"raw:%d:%d\n" % (seq[0], size)
            p = os.path.join(d, "f%d" % seq[0])

            def write():
                fd = os.open(p, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o644)
                try:
                    os.write(fd, tag + filler[:size - len(tag)])
                finally:
                    os.close(fd)

            timeit(rec, "raw.write", write)
            # A full queue means readers lag; blocking here self-throttles
            # the writer the way a real pipeline backs up.
            while not ctx.stop.is_set():
                try:
                    q.put((p, tag, size), timeout=0.2)
                    break
                except queue.Full:
                    continue

        run_loop(ctx, rec, "raw.write_step", step)
        return

    def step():
        try:
            p, tag, size = q.get(timeout=0.2)
        except queue.Empty:
            return

        def read():
            with open(p, "rb") as f:
                return f.read()

        try:
            data = timeit(rec, "raw.read", read)
        except FileNotFoundError:
            # The writer created it and closed it before enqueueing, so a
            # missing file is stale metadata, not a race in this harness.
            rec.count("raw.stale_enoent")
            return
        rec.count("raw.verified")
        if len(data) != size or not data.startswith(tag):
            rec.count("raw.stale_content")
        timeit(rec, "raw.unlink", lambda: os.unlink(p))

    run_loop(ctx, rec, "raw.read_step", step)


def wl_openclose(ctx, rec, role, idx):
    rng = ctx.rng("openclose", role, idx)
    paths = [pool_path(ctx.corpus, di, fi)
             for di in range(POOL_DIRS) for fi in range(POOL_FILES)]

    def step():
        p = paths[rng.randrange(len(paths))]
        fd = timeit(rec, "openclose.open", lambda: os.open(p, os.O_RDONLY))
        try:
            timeit(rec, "openclose.read_4k", lambda: os.read(fd, 4096))
        finally:
            timeit(rec, "openclose.close", lambda: os.close(fd))

    run_loop(ctx, rec, "openclose.step", step)


def wl_deep(ctx, rec, role, idx):
    rng = ctx.rng("deep", role, idx)
    paths = [deep_path(ctx.corpus, c) for c in range(DEEP_CHAINS)]

    def step():
        p = paths[rng.randrange(len(paths))]
        timeit(rec, "deep.stat", lambda: os.stat(p))

        def open_read():
            fd = os.open(p, os.O_RDONLY)
            try:
                return os.pread(fd, 1024, 0)
            finally:
                os.close(fd)

        timeit(rec, "deep.open_read", open_read)

    run_loop(ctx, rec, "deep.step", step)


def wl_walk(ctx, rec, role, idx):
    pool = os.path.join(ctx.corpus, "pool")

    def step():
        t0 = time.perf_counter_ns()
        n = 0
        for r, _dirs, files in os.walk(pool):
            for name in files:
                os.lstat(os.path.join(r, name))
                n += 1
            if ctx.stop.is_set():
                # A truncated walk would record as impossibly fast; drop it.
                return
        rec.add("walk.full_scan", (time.perf_counter_ns() - t0) / 1000.0)
        rec.count("walk.files_stated", n)

    run_loop(ctx, rec, "walk.step", step)


def wl_churn(ctx, rec, role, idx):
    d = ctx.wdir("churn", "w%d" % idx)
    payload = filler_block(ctx.seed, "churn", 64)
    seq = [0]

    def step():
        seq[0] += 1
        batch = [os.path.join(d, "c%d_%d" % (seq[0], i)) for i in range(CHURN_BATCH)]
        for p in batch:
            if ctx.stop.is_set():
                break

            def create(p=p):
                fd = os.open(p, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o644)
                try:
                    os.write(fd, payload)
                finally:
                    os.close(fd)

            timeit(rec, "churn.create", create)
        for p in batch:
            try:
                timeit(rec, "churn.unlink", lambda p=p: os.unlink(p))
            except FileNotFoundError:
                pass

    run_loop(ctx, rec, "churn.step", step)


# Default role counts are the concurrency mix: 18 threads total, weighted so
# metadata mutation dominates (that is where a network filesystem hurts) with
# steady background read pressure from the scanner, tailer and RAW readers.
WORKLOADS = {
    "rename":    {"fn": wl_rename,    "roles": {"churn": 2},
                  "why": "rename same-dir, cross-dir, and replace; each is a distinct metadata transaction"},
    "links":     {"fn": wl_links,     "roles": {"churn": 1},
                  "why": "hardlink and symlink create, readlink, resolution through a symlink, nlink accounting"},
    "trunc":     {"fn": wl_trunc,     "roles": {"churn": 1},
                  "why": "truncate extend and shrink, sparse far writes, hole reads must be zero"},
    "append":    {"fn": wl_append,    "roles": {"writer": 2, "tailer": 1},
                  "why": "append-heavy writes, fsync durability boundary, rotation, live tail of a growing inode"},
    "xattr":     {"fn": wl_xattr,     "roles": {"churn": 1},
                  "why": "xattr set/get/list/remove round trips against the metadata service"},
    "readdir":   {"fn": wl_readdir,   "roles": {"lister": 1, "mutator": 2},
                  "why": "full directory listing while two writers mutate it; sentinel entries must never vanish"},
    "raw":       {"fn": wl_raw,       "roles": {"writer": 1, "reader": 2},
                  "why": "read-after-write visibility of freshly written small files, plus staleness canaries"},
    "openclose": {"fn": wl_openclose, "roles": {"churn": 2},
                  "why": "open/close churn on a warm corpus: lookup and handle cost without data volume"},
    "deep":      {"fn": wl_deep,      "roles": {"churn": 1},
                  "why": "stat and open at directory depth 20: per-component traversal cost"},
    "walk":      {"fn": wl_walk,      "roles": {"walker": 1},
                  "why": "full-tree scandir plus lstat sweep: the backup or indexer noisy neighbor"},
    "churn":     {"fn": wl_churn,     "roles": {"storm": 1},
                  "why": "bursts of 100 creates then 100 unlinks: delete-storm pressure on the same parent"},
}


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

def probe_xattr(workdir):
    """Reason string when xattr cannot run on this target, else None."""
    if not hasattr(os, "setxattr"):
        return "os.setxattr not available on this platform"
    p = os.path.join(workdir, "xattr_probe")
    try:
        with open(p, "wb") as f:
            f.write(b"x")
        os.setxattr(p, "user.mosbench_probe", b"1")
        os.getxattr(p, "user.mosbench_probe")
        return None
    except OSError as e:
        return "xattr unsupported on target: %s" % e
    finally:
        try:
            os.unlink(p)
        except OSError:
            pass


def fs_info(target):
    info = {"target": target}
    try:
        real = os.path.realpath(target)
        best = None
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and (real == parts[1] or real.startswith(parts[1].rstrip("/") + "/") or parts[1] == "/"):
                    if best is None or len(parts[1]) > len(best[0]):
                        best = (parts[1], parts[2])
        if best:
            info["mountpoint"], info["fstype"] = best
    except OSError:
        pass
    return info


def build_mix(args):
    names = args.only or list(WORKLOADS)
    for n in names:
        if n not in WORKLOADS:
            raise SystemExit("unknown workload %r; choices: %s" % (n, ", ".join(WORKLOADS)))
    mix = {n: dict(WORKLOADS[n]["roles"]) for n in names}
    for spec in args.threads or []:
        try:
            name_role, cnt = spec.split("=", 1)
            wname, role = name_role.split(".", 1)
            cnt = int(cnt)
        except ValueError:
            raise SystemExit("bad --threads spec %r, want workload.role=N" % spec)
        if wname not in mix or role not in mix[wname]:
            raise SystemExit("unknown workload.role in --threads spec %r" % spec)
        if cnt < 0:
            raise SystemExit("thread count must be >= 0 in %r" % spec)
        mix[wname][role] = cnt
    return {n: r for n, r in mix.items() if sum(r.values()) > 0}


def reset_work_tree(ctx):
    """Fresh scratch tree per run so run N never lists or stats run N-1's
    leftovers; that is what keeps counts comparable between runs."""
    if os.path.isdir(ctx.work):
        shutil.rmtree(ctx.work)
    os.makedirs(ctx.work, exist_ok=True)
    lst = os.path.join(ctx.corpus, "listdir")
    if os.path.isdir(lst):
        for e in os.scandir(lst):
            if not e.name.startswith("s_"):
                os.unlink(e.path)


def format_us(v):
    if v >= 1000:
        return "%d" % round(v)
    return "%.1f" % v


def render_text(result):
    lines = []
    cfg = result["config"]
    host = result["host"]
    lines.append("mosbench %s  schema=%s" % (result["tool_version"], result["schema"]))
    lines.append("target=%s fstype=%s seed=%s duration=%ss warmup=%ss threads=%d label=%s"
                 % (cfg["target"], host.get("fstype", "?"), cfg["seed"],
                    cfg["duration_s"], cfg["warmup_s"], cfg["total_threads"],
                    cfg.get("label") or "-"))
    lines.append("host=%s kernel=%s python=%s started=%s"
                 % (host.get("hostname", "?"), host.get("kernel", "?"),
                    host.get("python", "?"), result["started_utc"]))
    lines.append("")
    lines.append("%-28s %9s %9s %10s %10s %10s %11s %6s"
                 % ("op", "count", "ops/s", "p50_us", "p90_us", "p99_us", "max_us", "errs"))
    for op in sorted(result["ops"]):
        o = result["ops"][op]
        lines.append("%-28s %9d %9.1f %10s %10s %10s %11s %6d"
                     % (op, o["count"], o["ops_per_sec"],
                        format_us(o["p50_us"]), format_us(o["p90_us"]),
                        format_us(o["p99_us"]), format_us(o["max_us"]),
                        result["errors"].get(op, 0)))
    extra_errs = {k: v for k, v in result["errors"].items() if k not in result["ops"]}
    if extra_errs:
        lines.append("")
        lines.append("errors outside timed ops: " +
                     " ".join("%s=%d" % kv for kv in sorted(extra_errs.items())))
    lines.append("")
    counters = result["counters"]
    bad = {k: v for k, v in counters.items()
           if v and any(s in k for s in ("stale", "mismatch", "missing", "nonzero", "bad_"))}
    lines.append("correctness counters: " +
                 ("CLEAN" if not bad else " ".join("%s=%d" % kv for kv in sorted(bad.items()))))
    if counters:
        lines.append("all counters: " + " ".join("%s=%d" % kv for kv in sorted(counters.items())))
    if result["skipped"]:
        lines.append("skipped: " + "; ".join("%s (%s)" % kv for kv in sorted(result["skipped"].items())))
    if result.get("stuck_threads"):
        lines.append("STUCK THREADS (did not exit within the join timeout, likely a hung filesystem op): "
                     + ", ".join(result["stuck_threads"]))
    lines.append("")
    lines.append("stable for run-to-run comparison: count, ops/s, p50, p90 (given same seed, mix, duration, host, cache settings)")
    lines.append("noisy, read with judgment: p99; max is a single sample, never a regression by itself")
    return "\n".join(lines) + "\n"


def cmd_run(args):
    if args.duration <= 0 or args.warmup < 0:
        raise SystemExit("duration must be > 0 and warmup >= 0")
    target = os.path.abspath(args.target)
    if not os.path.isdir(target):
        raise SystemExit("target %s is not a directory" % target)
    root = os.path.join(target, "mosbench")
    os.makedirs(root, exist_ok=True)
    prepare_corpus(root, args.seed)

    ctx = Ctx(root, args.seed)
    reset_work_tree(ctx)

    mix = build_mix(args)
    skipped = {}
    if "xattr" in mix:
        reason = probe_xattr(ctx.work)
        if reason:
            skipped["xattr"] = reason
            del mix["xattr"]
    if "raw" in mix:
        ctx.shared["raw.q"] = queue.Queue(maxsize=128)

    if not mix:
        raise SystemExit("nothing to run: every selected workload was skipped")

    threads = []
    recorders = []
    for wname, roles in sorted(mix.items()):
        fn = WORKLOADS[wname]["fn"]
        for role, cnt in sorted(roles.items()):
            for i in range(cnt):
                rec = Recorder(ctx.record)
                recorders.append(rec)

                def tmain(fn=fn, wname=wname, role=role, i=i, rec=rec):
                    try:
                        fn(ctx, rec, role, i)
                    except Exception as e:
                        # One broken worker must not abort the run; surface
                        # it loudly in the result instead.
                        rec.err("%s.fatal" % wname)
                        with ctx.fatal_lock:
                            ctx.fatal.append("%s.%s%d: %r" % (wname, role, i, e))

                t = threading.Thread(target=tmain, name="%s.%s%d" % (wname, role, i), daemon=True)
                threads.append(t)

    total = len(threads)
    print("run: %d threads (%s), warmup %ss, measuring %ss, seed=%s"
          % (total,
             " ".join("%s=%s" % (n, "+".join("%s:%d" % rc for rc in sorted(r.items())))
                      for n, r in sorted(mix.items())),
             args.warmup, args.duration, args.seed))
    started_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for t in threads:
        t.start()
    time.sleep(args.warmup)
    ctx.record.set()
    t0 = time.perf_counter()
    time.sleep(args.duration)
    # The window closes at stop-set; each thread may record at most one more
    # in-flight iteration, negligible against thousands of samples.
    window = time.perf_counter() - t0
    ctx.stop.set()
    # One SHARED deadline, not 60s per thread. On a genuinely hung mount every
    # thread is stuck in an uninterruptible syscall, and a per-thread timeout would
    # make shutdown cost 60s x thread count (18 minutes at the default mix) before
    # anything is reported. The threads are daemons, so whatever is still wedged
    # cannot hold the process open past this.
    join_deadline = time.perf_counter() + JOIN_GRACE_S
    stuck = []
    for t in threads:
        t.join(timeout=max(0.0, join_deadline - time.perf_counter()))
        if t.is_alive():
            stuck.append(t.name)

    hists, errors, counters = {}, {}, {}
    for rec in recorders:
        for op, h in rec.hists.items():
            if op in hists:
                hists[op].merge(h)
            else:
                hists[op] = h
        for op, n in rec.errors.items():
            errors[op] = errors.get(op, 0) + n
        for k, n in rec.counters.items():
            counters[k] = counters.get(k, 0) + n

    host = fs_info(target)
    host.update({
        "hostname": platform.node(),
        "kernel": "%s %s" % (platform.system(), platform.release()),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpus": os.cpu_count(),
    })
    result = {
        "schema": SCHEMA,
        "tool_version": TOOL_VERSION,
        "started_utc": started_utc,
        "config": {
            "target": target,
            "seed": args.seed,
            "duration_s": args.duration,
            "warmup_s": args.warmup,
            "label": args.label,
            "mix": mix,
            "total_threads": total,
            "corpus_shape": corpus_shape(),
        },
        "host": host,
        "measured_window_s": round(window, 3),
        "ops": {
            op: {
                "count": h.count,
                "ops_per_sec": round(h.count / window, 2),
                "mean_us": round(h.total_us / h.count, 1),
                "min_us": round(h.min_us, 1),
                "p50_us": round(h.percentile(50), 1),
                "p90_us": round(h.percentile(90), 1),
                "p99_us": round(h.percentile(99), 1),
                "max_us": round(h.max_us, 1),
            }
            for op, h in hists.items() if h.count
        },
        "errors": errors,
        "counters": counters,
        "skipped": skipped,
        "fatal": ctx.fatal,
        "stuck_threads": stuck,
        "stability": {
            "stable": ["count", "ops_per_sec", "p50_us", "p90_us", "mean_us"],
            "noisy": ["p99_us", "max_us", "min_us"],
            "must_be_zero": ["raw.stale_enoent", "raw.stale_content",
                             "readdir.missing_sentinel", "trunc.nonzero_hole",
                             "trunc.bad_size_after_shrink", "links.bad_nlink",
                             "links.symlink_content_mismatch", "xattr.mismatch"],
        },
    }

    # Default outside the current directory on purpose: this ships as a skill, and
    # running it from its own checkout used to write results into the repository.
    # MOSBENCH_OUT overrides for an unprivileged run with no /var/log access.
    out_root = os.environ.get("MOSBENCH_OUT") or (
        "/var/log/mountos-performance/mosbench"
        if os.access("/var/log", os.W_OK)
        else os.path.join(os.path.expanduser("~"), ".mosbench-results"))
    out = args.out or os.path.join(
        out_root,
        (args.label + "-" if args.label else "") + started_utc.replace(":", ""))
    os.makedirs(out, exist_ok=True)
    text = render_text(result)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    with open(os.path.join(out, "results.txt"), "w") as f:
        f.write(text)
    sys.stdout.write("\n" + text)
    print("results: %s" % os.path.join(out, "results.json"))
    if ctx.fatal:
        print("FATAL worker errors: %s" % "; ".join(ctx.fatal))
        return 1
    if stuck:
        print("WARNING: stuck threads: %s" % ", ".join(stuck))
        return 1
    return 0


def cmd_prepare(args):
    target = os.path.abspath(args.target)
    root = os.path.join(target, "mosbench")
    os.makedirs(root, exist_ok=True)
    prepare_corpus(root, args.seed)
    return 0


def cmd_clean(args):
    target = os.path.abspath(args.target)
    root = os.path.join(target, "mosbench")
    if not os.path.isdir(root):
        print("nothing to clean at %s" % root)
        return 0
    # Only remove a tree this tool built: the manifest is its ownership mark.
    if load_manifest(root) is None:
        raise SystemExit("%s has no mosbench manifest; refusing to delete it" % root)
    shutil.rmtree(root)
    print("removed %s" % root)
    return 0


def cmd_list(_args):
    print("%-10s %-22s %s" % ("workload", "roles", "exercises"))
    for n, w in WORKLOADS.items():
        roles = " ".join("%s:%d" % rc for rc in sorted(w["roles"].items()))
        print("%-10s %-22s %s" % (n, roles, w["why"]))
    return 0


def cmd_compare(args):
    with open(args.a) as f:
        a = json.load(f)
    with open(args.b) as f:
        b = json.load(f)
    for r, name in ((a, args.a), (b, args.b)):
        if r.get("schema") != SCHEMA:
            raise SystemExit("%s has schema %r, want %r" % (name, r.get("schema"), SCHEMA))
    for key in ("seed", "duration_s", "warmup_s", "mix", "corpus_shape"):
        if a["config"].get(key) != b["config"].get(key):
            print("WARNING: config %r differs (%r vs %r); comparison is weakened"
                  % (key, a["config"].get(key), b["config"].get(key)))

    # p99 and max are excluded from verdicts on purpose: on a network
    # filesystem a single GC pause or retransmit moves them run to run.
    metrics = [("p50_us", +1), ("p90_us", +1), ("ops_per_sec", -1)]
    if args.all:
        metrics.append(("p99_us", +1))
    regressions = []
    keys = sorted(set(a["ops"]) | set(b["ops"]))
    print("%-28s %-12s %12s %12s %9s" % ("op", "metric", "old", "new", "delta%"))
    for k in keys:
        oa, ob = a["ops"].get(k), b["ops"].get(k)
        if oa is None or ob is None:
            print("%-28s only in %s" % (k, "new" if oa is None else "old"))
            continue
        if min(oa["count"], ob["count"]) < args.min_count:
            continue
        for m, worse_dir in metrics:
            old, new = oa[m], ob[m]
            if old == 0:
                continue
            delta = (new - old) / old * 100.0
            flag = ""
            if delta * worse_dir > args.threshold_pct:
                flag = "  <-- REGRESSION"
                regressions.append("%s %s %+0.1f%%" % (k, m, delta))
            if abs(delta) > args.threshold_pct or flag:
                print("%-28s %-12s %12.1f %12.1f %+8.1f%%%s" % (k, m, old, new, delta, flag))

    bad = []
    for c in b.get("stability", {}).get("must_be_zero", []):
        v = b.get("counters", {}).get(c, 0)
        if v:
            bad.append("%s=%d" % (c, v))
    if bad:
        print("CORRECTNESS counters nonzero in new run: %s" % " ".join(bad))
    if regressions or bad:
        print("\n%d regression(s)" % (len(regressions) + len(bad)))
        return 1
    print("\nno regressions beyond %.0f%% on stable metrics" % args.threshold_pct)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="mosbench", description=__doc__.splitlines()[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_target(sp):
        sp.add_argument("--target", required=True, help="directory on the filesystem under test")
        sp.add_argument("--seed", default="42", help="reproducibility seed (any string)")

    sp = sub.add_parser("prepare", help="build the corpus only (untimed)")
    add_target(sp)
    sp.set_defaults(fn=cmd_prepare)

    sp = sub.add_parser("run", help="prepare if needed, then run the mixed workload")
    add_target(sp)
    sp.add_argument("--duration", type=float, default=60.0, help="measured seconds")
    sp.add_argument("--warmup", type=float, default=5.0, help="seconds discarded before measuring")
    sp.add_argument("--only", action="append", metavar="WORKLOAD",
                    help="run only this workload (repeatable); the single-workload isolation mode")
    sp.add_argument("--threads", action="append", metavar="WL.ROLE=N",
                    help="override a role's thread count (repeatable)")
    sp.add_argument("--out", help="output directory (default /var/log/mountos-performance/mosbench/<timestamp>, or ~/.mosbench-results when /var/log is not writable; MOSBENCH_OUT overrides)")
    sp.add_argument("--label", help="free-form tag stored in the result")
    sp.set_defaults(fn=cmd_run)

    sp = sub.add_parser("compare", help="diff two results.json files")
    sp.add_argument("a", help="old results.json")
    sp.add_argument("b", help="new results.json")
    sp.add_argument("--threshold-pct", type=float, default=25.0,
                    help="flag a stable metric moving more than this in the bad direction")
    sp.add_argument("--min-count", type=int, default=50,
                    help="skip ops with fewer samples than this in either run")
    sp.add_argument("--all", action="store_true", help="also judge p99 (noisy)")
    sp.set_defaults(fn=cmd_compare)

    sp = sub.add_parser("clean", help="remove the mosbench tree from the target")
    add_target(sp)
    sp.set_defaults(fn=cmd_clean)

    sp = sub.add_parser("list", help="describe the workloads and default mix")
    sp.set_defaults(fn=cmd_list)

    args = p.parse_args(argv)
    if sys.version_info < (3, 8):
        raise SystemExit("mosbench needs Python 3.8+")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
