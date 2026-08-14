# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

- **Major**: the guidance changes in a way that would make an agent following the previous
  version do the wrong thing.
- **Minor**: new sections, new references, or materially expanded guidance.
- **Patch**: corrections, clarifications, and link fixes.

The skill loads current documentation from https://mountos.io on every use, so it tracks new
mountOS releases without a release here. A release here means the diagnostic guidance
changed.

## 1.0.0

First release. Deliberately not a symptom-to-fix catalogue: that lives in the live
documentation and is regenerated from source, so it stays correct on its own. This skill
carries the method that the catalogue cannot.

- The governing rule: a healthy status is not evidence that the thing works, so the question
  is always which specific invariant should hold and whether it does.
- An evidence-gathering order that starts with what changed and ends with the read-only MCP
  connector, each step cheap and ruling out a layer.
- A one-command-each split for isolating client from network from fleet from volume, plus the
  hang-versus-refuse distinction that identifies a dropped-packet firewall rule before any
  application log is read.
- What is normal and looks broken: cold-fleet quorum taking about six minutes, and
  registration retries being the expected state for a cluster that is not ready.
- Hard rules for diagnosis, including not restarting before capturing state, since several
  mountOS failure modes only appear on the second start.
- `references/method.md`: the healthy-but-broken catalogue as a table of what you see against
  what is true, and per-area procedures for registration, quorum, addressing, silently
  discarded configuration, gateways, and performance.
