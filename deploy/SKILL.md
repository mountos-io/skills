---
name: deploy
description: Deploy, verify, operate, and integrate a self-hosted mountOS storage system, and mount its volumes. Use for any task that mentions mountOS, appserv/dataserv/gcserv/blockserv, a mountOS hub, region, cluster, storage, volume, or access key; for standing up mountOS on AWS, GCP, or Azure with the mountos-io/deployment Terraform package; for explaining or diagramming the mountOS architecture and how its components interact; for adding mountOS under an existing product and mapping an existing user base onto mountOS accounts, users, volumes, and keys with the Admin SDK; for mounting a mountOS volume on Linux, macOS, or Windows, including /etc/fstab and the mount helper; and for diagnosing a deployment that looks healthy but does not work.
version: 1.0.0
license: Apache-2.0
---

# mountOS

mountOS is self-hosted, POSIX-compatible distributed storage. It gives native filesystem
mounts on macOS, Linux, and Windows over the same data, plus S3 and WebHDFS gateways, with
forks, time travel, and one-minute versioning. The operator runs it on infrastructure they
control.

This skill is the deployment and operations entry point. It carries what a real bring-up
teaches you and what the reference documentation cannot: the order of operations, the
assertions that prove each stage, and the failure modes that look like success.

## Step 0: load the live context first

**Always do this before you plan or run anything.** This repository is deliberately thin.
The authoritative documentation is generated from the current mountOS source and is
published on the web, so it is correct for the version the operator is about to install.
Where this repository and the live documentation disagree, the live documentation wins.

Fetch in this order:

| Order | URL | What it gives you |
| --- | --- | --- |
| 1 | https://mountos.io/skill.md | Entry-point skill: the mental model and the task-to-skill routing table |
| 2 | https://mountos.io/llms.txt | Topic index: one line per topic, with its URL |
| 3 | https://mountos.io/skills/deploy.md | Cloud substrate and hub bring-up |
| 4 | https://mountos.io/skills/provision.md | Account, region, cluster, region services |
| 5 | https://mountos.io/skills/volumes.md | Storages, volumes, access keys, mounting |

Fetch other task skills (`operate.md`, `integrate.md`, `s3.md`, `iceberg.md`, `env.md`) and
topic pages (`https://mountos.io/ai/topics/<slug>.md`) as the task needs them. The full
corpus is at https://mountos.io/ai/llms-full.txt, which is large; prefer the index and the
single topic you need.

If you have no network access, say so plainly before you continue. You can still work from
the references in this repository, but tell the operator that you are working from a cached
summary and that version-specific details are unverified.

## Keep this skill current

This skill is version `1.0.0`. Two different things go stale, and they are refreshed
differently.

- **mountOS facts** (flags, variable names, endpoints, defaults) refresh on every use,
  through step 0. Nothing to upgrade.
- **This guidance** (the runbook, the pitfalls, the diagrams) ships in the repository and
  only changes when the repository is updated.

Check for a newer skill release when a deployment task starts, or when guidance here does
not match what the operator sees:

```bash
curl -fsSL https://raw.githubusercontent.com/mountos-io/skills/main/deploy/VERSION
```

If that value is higher than `1.0.0`, tell the operator, point them at
https://github.com/mountos-io/skills/blob/main/deploy/CHANGELOG.md, and offer the upgrade:

```bash
git -C ~/.mountos-skills pull --ff-only
```

Adjust the path if the clone lives somewhere else. Do not silently continue on a
known-stale version when the changed guidance is relevant to the task in hand.

## Mental model

Enough to route correctly. The live documentation is authoritative for the detail.

- The **hub** is `appserv`. There is exactly one per deployment and it is multi-tenant. It
  owns the admin database and the hub secret store, serves the Admin API at
  `<hub>/api/v1/*`, and answers client discovery. Its domain is the discovery URL every
  client is given.
- An **account** is the tenant. It owns its regions, users, and storages.
- A **region** belongs to one account and owns one database and one secret store. It holds
  storages, each pointing at an S3-compatible or Azure object store.
- A **region cluster** partitions volume load inside a region. It shares the region's
  database and secret store. `dataserv`, `gcserv`, `blockserv`, and the gateways are
  cluster-scoped. Creating a region auto-creates its default cluster, named `uno`.
- A **volume** lives in one region on exactly one storage. Its data does not cross a region
  boundary at serving time.
- The client binary is `mountos`. It discovers at the hub, then talks to the owning cluster
  directly.

## Route the task

| The operator wants to | Read |
| --- | --- |
| Understand the architecture, or draw it | [references/architecture.md](references/architecture.md), plus https://mountos.io/ai/topics/architecture.md |
| Add mountOS under an existing product and an existing user base | [references/integration.md](references/integration.md) |
| Create cloud infrastructure and bring up the hub | https://mountos.io/skills/deploy.md, then [references/runbook.md](references/runbook.md) |
| Create the tenant, region, and region services | https://mountos.io/skills/provision.md |
| Create storages, volumes, and access keys, and mount | https://mountos.io/skills/volumes.md |
| Mount in production, with fstab or a mount helper | https://mountos.io/skills/volumes.md, section on the mount helper |
| Inspect a running deployment or a live mount | https://mountos.io/skills/operate.md, plus the client's read-only MCP connector |
| Use S3, WebHDFS, Kubernetes CSI, or the change feed | https://mountos.io/skills/integrate.md |
| Understand what an environment variable does | https://mountos.io/skills/env.md |
| Work out why a healthy-looking deployment does not work | [references/pitfalls.md](references/pitfalls.md) |
| Deploy on GCP or Azure rather than AWS | [references/clouds.md](references/clouds.md) |
| Prove a stage actually completed | [references/verification.md](references/verification.md) |

## Deployment spine

The order is load-bearing. Each stage has an assertion that must pass before the next one
starts. Do not treat "the command exited 0" as the assertion.

1. **Substrate and hub.** Drive the `mountos-io/deployment` package. Do not hand-roll
   Terraform or systemd. Assertion: the hub answers the Admin API with auth enforced.
2. **Tenant.** Create the account, then the users. Assertion: the account reads back with
   its id.
3. **Region.** Create the region, which auto-creates cluster `uno`. Assertion: you can read
   back the region cluster id, a UUID. You need this value for the next stage.
4. **Region services.** Put the region cluster id into the deployment configuration and
   apply again, then seed the region secrets. Assertion: cluster `uno` reports ready, and
   the node list shows every dataserv and gcserv node healthy.
5. **Storage and volume.** Register the object store as a storage, create a volume on it,
   then generate a volume access key pair. Assertion: the volume reads back and the key
   pair is returned once.
6. **Mount.** Install the client on a machine that is genuinely outside the deployment
   network and mount the volume. Assertion: write a file, read it back, and confirm the
   object landed in the backing store.

Full commands and per-stage assertions are in [references/runbook.md](references/runbook.md)
and [references/verification.md](references/verification.md).

## Hard rules

- **Never destroy a production deployment.** The deployment package has no destroy target
  by design. `apply` and the bootstrap scripts converge forward and are safe to re-run.
  Decommissioning is a separate human decision.
- **Never install or launch HashiCorp Vault as part of this flow**, and never suggest it.
  The supported secret stores are the cloud-native one (recommended) or a Vault the
  operator already brings and operates.
- **Never handle the operator's secrets.** The admin private key is the root credential.
  Do not print it, commit it, paste it into chat, or write it into instance configuration,
  Terraform variables, or state. Volume access keys are the same. Ask the operator to place
  credentials themselves, in their own session.
- **Do not pass credentials through a remote-command API.** Parameters to cloud
  run-command services are recorded in the provider's audit log. Use an interactive session
  instead.
- **The operator owns their cloud account, their Terraform state, their keys, and their
  DNS.** Confirm before anything that costs money or is hard to reverse.
- **No license file is needed to start.** A deployment runs the free tier automatically.
  Capacity is raised by loading a signed license through the Admin API, with no redeploy.

## Verify, do not assume

Several mountOS failure modes produce a service that looks healthy and is functionally
broken: a single-node cluster that believes it is a quorum, a co-located service that
crash-loops while the node still reports healthy, an addressing feature that silently uses
the wrong address family. After any change to addressing, clustering, or ports, assert the
specific invariant rather than the general health check. See
[references/verification.md](references/verification.md).

## What is in this repository

- [references/architecture.md](references/architecture.md): how the components interact,
  with diagrams you can show an operator. Control plane against data plane, the bring-up
  sequence, the mount and I/O path, raft inside a cluster, and the access surfaces.
- [references/integration.md](references/integration.md): adding mountOS under a product
  that already has customers. Mapping an existing user base, the two credential-issuing
  shapes, the reconciliation loop, and which SDK to use.
- [references/runbook.md](references/runbook.md): the ordered bring-up, with the commands
  and the hand-off points between stages.
- [references/verification.md](references/verification.md): what "done" means at each
  stage, and the exact check that proves it.
- [references/pitfalls.md](references/pitfalls.md): failure modes that present as success.
  Read before a first deployment.
- [references/clouds.md](references/clouds.md): what was proven on which cloud, and the
  checklist to work through when you extrapolate to a cloud that has not been run for real.

## Provenance

The operational content here comes from real bring-ups, not from review. The AWS path has
been deployed end to end and mounted from a genuinely external client. GCP and Azure are
validated at the configuration level only. [references/clouds.md](references/clouds.md)
states exactly what that means and what to check.
