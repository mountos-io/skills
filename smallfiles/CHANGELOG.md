# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

## 1.0.0

First release. Split out of `conformance`, which answers a different question:
conformance has verdicts, this has none. Mixing them invited reading a slow run as
a failure.

- `run.sh` times a shallow git clone and two npm installs against a mount, with
  wallclock and file counts per phase, and a fresh work root per run so a populated
  `node_modules` cannot turn npm into a no-op.
- Instructs the agent to ask the operator for their own repository and packages
  before falling back to defaults.
- States plainly that this must NOT use the cache-disabled mount the conformance
  suites use, since that measures the worst case rather than normal operation.
- The four conditions that make a comparison meaningless: a populated
  `node_modules`, a shared mount, a different network path, and cold versus warm
  cache.
- Storage locality, not CPU, sets the pace, so a runtime without a same-locality
  baseline cannot be compared to anything.
