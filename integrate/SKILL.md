---
name: integrate
description: Add mountOS storage under a product that already has customers, users, and an identity provider. Use for mapping an existing user base onto mountOS accounts, users, volumes, and access keys with the Admin SDK; for deciding between long-lived and short-lived credentials; for choosing between the filesystem mount, the S3 gateway, the WebHDFS gateway, the Kubernetes CSI driver, and the change-event feed for a given workload; and for onboarding an existing customer base without rebuilding identity or exposing the operator root key.
version: 1.0.0
license: Apache-2.0
---

# mountOS integration

You are wiring [mountOS](https://mountos.io) under a product that already exists. Your users
already have logins. Your tenants already have identities. The goal is that they keep both
and gain storage, without you rebuilding identity and without anyone outside your backend
ever holding the operator root key.

This skill is for the application developer. If you still need to stand the deployment up,
that is a different job and a different skill: `deploy`, at
https://github.com/mountos-io/skills.

## Step 0: load the live context first

**Do this before you plan or write anything.** This repository is deliberately thin. The
authoritative documentation is generated from the current mountOS source, so it is correct
for the version the operator is actually running. Where this repository and the live
documentation disagree, the live documentation wins.

| Order | URL | What it gives you |
| --- | --- | --- |
| 1 | https://mountos.io/skill.md | Entry point: the mental model and the task routing |
| 2 | https://mountos.io/skills/integrate.md | The data-plane surfaces, with exact flags |
| 3 | https://mountos.io/ai/topics/admin-sdk.md | The control plane, auth, pagination, errors |
| 4 | https://github.com/mountos-io/mountos-admin-sdk | `api.md` REST reference, `api.yaml` spec for codegen |

Fetch https://mountos.io/skills/s3.md when the workload is S3, and
https://mountos.io/skills/volumes.md when you need volume, fork, or key semantics.

If you have no network access, say so before you continue. You can work from the reference
here, but tell the developer that version-specific details are unverified.

## The one thing to get right first

mountOS is **not** your identity provider and does not want to be. It holds a thin record of
each tenant and each user so it can own quotas, keys, and audit. You map your identifiers
onto those records and keep your own.

**Store the mountOS id on your own record.** That mapping is load-bearing, and for users it
is the only direction that works. There is a `providerInfo` field for your own identifiers,
but it behaves differently on accounts and users in a way that will silently break a
reconciliation loop built on the wrong assumption. The details, and the workaround when you
cannot hold the mapping yourself, are in
[references/user-mapping.md](references/user-mapping.md).

## Decide these before you write code

Each of these is expensive to change later. Two of them are data migrations.

1. **Volume granularity.** One volume per tenant with shared access is the common shape. One
   volume per user isolates cleanly and makes quotas simple, but multiplies object count and
   administrative surface. Changing this after onboarding is a data migration.
2. **Credential lifetime.** A long-lived key pair for machine access from your backend, or a
   short-lived key for anything less trusted. Most products need both. Getting this wrong
   means either a credential you cannot revoke or a re-issue path you did not build.
3. **Who holds the admin key.** It is the root credential for the whole deployment. It stays
   on your server. If any design puts it in a browser, a mobile app, a CI log, or a client
   machine, that design is wrong and needs replacing rather than guarding.
4. **What happens when a plan changes.** Quotas are per volume. If you sell storage tiers,
   decide now how a tier change moves the quota.

## Route the task

| You are doing | Read |
| --- | --- |
| Mapping your tenants and users onto mountOS records | [references/user-mapping.md](references/user-mapping.md) |
| Issuing credentials to a backend, a browser, or an agent | [references/user-mapping.md](references/user-mapping.md), the two shapes |
| Onboarding an existing customer base | [references/user-mapping.md](references/user-mapping.md), the reconciliation loop |
| Picking a data surface for a workload | The table below, then https://mountos.io/skills/integrate.md |
| Tuning an S3 client | https://mountos.io/skills/s3.md |
| Standing up the deployment itself | The `deploy` skill, https://github.com/mountos-io/skills |

## Pick a surface per workload

Every surface below fronts the same bytes and the same metadata, and every one authenticates
with the same per-volume access key pair. All of them run from the `mountos` client binary
on the host that needs them. There is no separate gateway service to deploy.

| Workload | Surface | The constraint that bites |
| --- | --- | --- |
| Anything expecting a POSIX filesystem | Filesystem mount | Mount point is positional; the secret flag is a switch reading from prompt or stdin, never a flag value |
| Existing S3 SDK code | S3 gateway | Multipart parts at 8 MiB or more except the last; listings cap at 1000 keys per page |
| Spark, Hive, Trino, distcp, Flink | WebHDFS gateway, or the `hadoop-mountos` jar | Its SigV4 service name differs from S3's; do not point an S3 signer at it |
| Kubernetes PersistentVolumes | CSI driver `csi.mountos.io` | Key pair arrives through a node-stage secret |
| Reacting to change without walking the tree | Change-event feed | Per volume, and needs retention enabled on that volume |

Choose per workload rather than standardising on one. They are not tiers; they are different
shapes for different consumers of the same data.

## Hard rules

- **The admin private key never leaves your backend.** Not to a browser, not to a mobile
  app, not into a CI log, not into a repository. It is the root credential for the entire
  deployment, not a per-tenant secret.
- **A volume secret is returned once.** Store it in your own secret store if you must
  re-deliver it, or generate a fresh pair. Do not build a flow that assumes you can read it
  back.
- **Generating a new key pair can evict an older one.** The response tells you which. Treat
  that as the signal to invalidate anything caching the old pair.
- **Deactivate rather than delete** when a user leaves, so audit history stays attributable.
- **Never put credentials in a URL or a query string**, on any surface.
- **Prefer a short expiry to a revocation you have to remember to run.**

## Verify, do not assume

An integration that returns HTTP 200 everywhere can still be wrong in ways that only show up
as a support ticket. Before you call it done:

- A user of your product signs in with your existing login and reaches their data, with no
  mountOS-specific account-creation step in their way.
- Removing a user in your product removes their access, proven by an **actually denied
  request**, not by the revoke call returning success.
- Re-running the reconciliation loop creates nothing and changes nothing.
- A plan change moves the corresponding quota.
- The admin key appears in no client bundle, no log, and no repository. Grep for it.

## What is in this repository

- [references/user-mapping.md](references/user-mapping.md): the mapping model with diagrams,
  the two credential-issuing shapes, the reconciliation loop for an existing user base, SDK
  selection, and the completion checklist.
