# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

- **Major**: the guidance changes in a way that would make an agent following the previous
  version do the wrong thing.
- **Minor**: new sections, new references, or materially expanded guidance.
- **Patch**: corrections, clarifications, and link fixes.

The skill loads current documentation from https://mountos.io on every use, so it tracks new
mountOS releases without a release here. A release here means the operational guidance
changed.

## 1.1.0

- Stage 2 (tenant) now notes that admin-level dashboard access (`superadmin`, `l1admin`,
  `l2admin`) needs no account user record, and recommends minting a Provider-signed
  sign-in token through the mountOS admin dashboard's `/tools/generate-login-token` page
  for the operator's own first login, rather than scripting an Admin API user for it.

## 1.0.0

First public release. Vendor-neutral: the skill body names no specific agent, and ships in
both a multi-file form and a single-file bundle (`deploy.bundle.md`) for agents that cannot
follow relative links. A Claude Code plugin manifest is included but purely additive.

- Context-loading protocol: load the live documentation from https://mountos.io before
  planning or acting, with an explicit rule that the live copy wins on any disagreement.
- Mental model, task routing, and the six-stage deployment spine with per-stage assertions.
- `references/architecture.md`: component interaction with diagrams. Topology, control plane
  against data plane, bring-up sequence, mount and I/O path, raft inside a cluster, and the
  access surfaces on one volume.
- `references/integration.md`: adding mountOS under a product that already has customers.
  Mapping an existing user base through `providerInfo`, the backend-mediated and short-lived
  credential shapes, the reconciliation loop, and SDK selection.
- `references/runbook.md`: the ordered bring-up from nothing to a mounted volume.
- `references/verification.md`: what "done" means at each stage and the check that proves it.
- `references/pitfalls.md`: twelve failure modes that report healthy while the system is
  broken, all found by deploying rather than by review.
- `references/clouds.md`: AWS proven end to end; GCP and Azure configuration-validated only,
  with a ten-item checklist for the first real run on either.
