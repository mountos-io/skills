# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

## 1.0.0

First release. Split out of `conformance`, which answers a different question.
Timing belongs against a baseline; behaviour belongs against a verdict. Keeping them
apart makes each one easier to read.

- `run.sh` times a shallow git clone and two npm installs against a mount, with
  wallclock and file counts per phase, and a fresh work root per run so a populated
  `node_modules` cannot turn npm into a no-op.
- Instructs the agent to ask the operator for their own repository and packages
  before falling back to defaults.
- Measure with the caches the operator actually runs, since that is the
  configuration whose performance they care about.
- The four conditions that make a comparison meaningless: a populated
  `node_modules`, a shared mount, a different network path, and cold versus warm
  cache.
- Storage locality, not CPU, sets the pace, so a runtime without a same-locality
  baseline cannot be compared to anything.
