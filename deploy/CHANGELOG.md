# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

- **Major**: the guidance changes in a way that would make an agent following the previous
  version do the wrong thing.
- **Minor**: new sections, new references, or materially expanded guidance.
- **Patch**: corrections, clarifications, and link fixes.

The skill loads current documentation from https://mountos.io on every use, so it tracks new
mountOS releases without a release here. A release here means the operational guidance
changed.

## 1.3.1

- Stage 6 says that the Linux client install also installs `pfkit` with its own version, that
  the installer does not start it, how to start it, and how to skip it with `--no-pfkit`.

## 1.3.0

- The runbook has a new host network tuning section for block storage nodes: the sysctl
  file that the provided Terraform writes, how to check it, how to apply it on hosts that the
  provided Terraform did not make, and what a container host must set.
- New pitfalls: an image with no `tcp_bbr` module, the send rate that drops after each idle
  period, and a non-root container that cannot select `bbr` by itself.
- The runbook states the tuning target (a buffer maximum of 32 MiB or more in `tcp_rmem`
  and `tcp_wmem`, and `bbr`) and checks those values on each host.
- Verification now covers the network tuning rows of each blockserv node in the admin
  dashboard, the "Host network tuning below target" alert, and the "Network Tuning" section
  of a client session. It also states the rule for a value that a node or a client cannot
  read. A value that can be read and is below the target shows "Below target" and raises
  the alert. A missing value, with all other values at the target, shows "Not reported" and
  raises no alert. The alert message shows the congestion control of the block data
  connections and the system default as two values. When the congestion control is the
  cause of "Below target", the node detail also shows the system default. In that case,
  when a per-process override is set, the node detail also shows that override. On
  Windows, the client section shows "not supported".
- The routing table has a row for host network tuning.

## 1.2.0

- Stage 2 (tenant) now documents the mountOS admin dashboard's native login extension as
  an alternative to the one-shot Provider-signed sign-in token for the operator's own
  first login: a real username/password login with mandatory two-factor authentication,
  seeded once with `make seed-admin`.

## 1.1.1

- Corrected a stale claim that a block storage is an active-active mesh of one to three
  members. A block storage is a fleet of copysets, and every copyset is a fixed
  two-server pair.
- Removed internal replication-mechanism language (named consensus algorithm,
  leader-election detail) from the architecture, pitfalls, verification, and runbook
  references, keeping only the operational facts an operator needs: real ports, env
  vars, and the exact troubleshooting log lines to search for.

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
