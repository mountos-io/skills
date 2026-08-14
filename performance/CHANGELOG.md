# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

## 1.0.0

First release. Holds the measurement tools, which report rates and wallclock read
against a baseline. Correctness lives in `conformance`, which produces verdicts.

The split is verdict against measurement. mdtest first sat in `conformance` because
it is a filesystem test, but it reports operations per second and has no pass or
fail, so it belongs here with the other numbers.

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
