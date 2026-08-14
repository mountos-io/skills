# Changelog

Versioning is semantic, applied to the skill itself, not to mountOS.

- **Major**: the guidance changes in a way that would make an agent following the previous
  version do the wrong thing.
- **Minor**: new sections, new references, or materially expanded guidance.
- **Patch**: corrections, clarifications, and link fixes.

The skill loads current documentation from https://mountos.io on every use, so it tracks new
mountOS releases without a release here. A release here means the operational guidance
changed.

## 1.0.0

First release. Split out of the `deploy` skill, which was serving two different readers: an
operator standing up infrastructure, and an application developer wiring mountOS under an
existing product. They need almost none of each other's context.

- The four decisions that are expensive to reverse: volume granularity, credential lifetime,
  who holds the admin key, and what a plan change does to quota.
- A surface-per-workload table carrying the constraint that actually bites for each one.
- Hard rules on credential handling, including that a volume secret is returned once and that
  generating a new pair can evict an older one.
- Completion checks that require a denied request rather than a successful revoke call.
- `references/user-mapping.md`: the mapping model with diagrams, the two credential-issuing
  shapes, the reconciliation loop for an existing user base, and SDK selection. Carries the
  correction that `providerInfo` is write-only on users, which silently breaks a
  reconciliation loop designed to read it back.
