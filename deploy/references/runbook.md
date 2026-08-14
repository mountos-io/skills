# Bring-up runbook

The ordered path from nothing to a mounted volume. Read
https://mountos.io/skills/deploy.md, https://mountos.io/skills/provision.md, and
https://mountos.io/skills/volumes.md alongside this. Those documents are generated from the
current source and are authoritative for flags, variable names, and defaults. This file is
the sequence, the hand-off points, and the decisions that are easy to get wrong.

## Before you start

Confirm these with the operator. Do not infer them.

- **Cloud and region.** One of `aws`, `gcp`, `azure`. Pick the region closest to the people
  and the workloads that will use it.
- **Hub domain.** A name the operator controls, resolvable to the hub. Clients are given
  this name as their discovery URL, so it is hard to change later.
- **Secret store.** The cloud-native store is the default and the recommendation. The other
  option is a HashiCorp Vault that the operator already runs. This flow never installs one.
- **Database.** A managed PostgreSQL the operator already runs is the recommended
  production path. The package can also provision one.
- **Mode.** Production or non-production. Non-production relaxes high-availability and
  deletion-protection settings, which makes a test environment cheaper and stoppable.
- **Budget and lifecycle.** A running deployment costs money continuously. Agree up front
  whether an idle environment is stopped, scaled down, or destroyed, and who decides.

## Stage 1: cloud substrate and hub

Get the deployment package by cloning the public repository:

```
git clone https://github.com/mountos-io/deployment.git
```

`release.yaml`'s `version` records which package version you have. Set `MOS_VERSION`
explicitly in the answers rather than letting the fleet take whatever `latest` is that day;
that is what keeps the package, the binaries, the admin SDK, and the helper scripts on one
version. Do not mix versions.

Older instructions mention cloning a release tag or installing `--pkg deploy`. Neither works
yet: the repository publishes no tags and `deploy` is not a published installer package.
Clone the default branch. The `mos-verify` and `mos-keygen` helpers are likewise unpublished,
and the make targets build them from source automatically.

```
make interview          # scaffolds answers.env
# fill answers.env and clouds/<cloud>/terraform/terraform.tfvars
make plan
make apply
make bootstrap          # generates keys, seeds the secret store
make verify
```

Notes that are easy to miss:

- Set a remote state backend before the first apply. The sample is `backend.tf.sample`.
- `make bootstrap` runs **after** `make apply`, never before. On GCP the apply owns the
  empty secret containers, so seeding first makes the later apply fail with an
  already-exists error.
- `make bootstrap` writes fresh keys into `secrets.local.json`. The `admin_private` key in
  that file is the operator root credential. It stays offline. It is never committed and
  never pasted anywhere.
- For a provisioned database, no DSN is ever a Terraform value. Terraform outputs the host
  plus a reference to the stored password, and the seed script fetches the password itself.
  **On AWS only**, the platform owns and rotates that password, so it never enters Terraform
  state. On GCP and Azure the master password is a Terraform value and is present in state.
  Bringing your own database avoids this on every cloud. See
  [clouds.md](clouds.md), item 4.

**Assertion:** `make verify` is green. The hub answers `https://<hub_domain>/api/v1/*`,
rejects an unauthenticated call, and accepts a signed admin call.

## Stage 2: tenant

Use the Admin SDK (`@mountos-io/admin-sdk` for TypeScript, the Go module, or the Rust
crate) against the running hub, with the operator's admin private key.

Create the account, then add users to it.

**Assertion:** the account reads back by id.

## Stage 3: region

Create the region on the hub. This auto-creates its default cluster, named `uno`.

Read back the region cluster id. It is a UUID and you need it for stage 4.

**Assertion:** the region reads back, and you hold its cluster UUID.

Cluster `uno` is **not** ready yet. It becomes ready when the first cluster-scoped service
registers into it. That happens in stage 4.

## Stage 4: region services

Put the region cluster id into the Terraform variables, along with the dataserv count, the
arena size, and the region database and secret-store choices. Then:

```
make apply              # provisions the region database and the dataserv fleet
make region-bootstrap   # seeds the region store, fans out service verifiers both ways
```

Decisions in this stage:

- **dataserv count.** Three nodes give a real quorum. One node works for a throwaway test
  but has no consensus and no failure tolerance.
- **arena size.** Size it to the metadata working set. The published rule is roughly five
  million files per GiB of arena, and that is the number to plan against. As a bring-up
  starting point before you know the working set, about half the machine's memory is a
  reasonable placeholder. Confirm the value the service actually adopted in its own startup
  log rather than assuming the configured value took effect.
- **gcserv co-location.** By default gcserv runs on the dataserv nodes. It needs its own
  HTTP port and its own RPC port. See [pitfalls.md](pitfalls.md), item 3.

**Assertion:** cluster `uno` reports ready, the node list shows every dataserv and gcserv
node healthy at the expected version, and exactly one dataserv node is the raft leader with
the other nodes joined to it. A single-node "quorum" with the others looping on a join
error is a real failure. See [verification.md](verification.md).

## Stage 5: storage and volume

The deployment package does not create your object store. That is deliberate. You bring a
bucket or container, and register it as a storage record.

1. Create the bucket or container in the same locality as the region.
2. Register it as a storage on the hub.
3. Create a volume on that storage.
4. Generate a volume access key pair for a user. The secret is returned once. The operator
   stores it; you do not.

For block-backed volumes, provision a block storage first, which yields member ids, then
enable blockserv in the Terraform variables with those members. Skip blockserv entirely for
object-backed volumes.

A block storage is an active-active mesh of one to three members. Once it is serving, do
**not** upgrade it with a plain apply: the members are individual machines rather than an
instance group, so one apply replaces every changed member at the same time and the whole
mesh goes down together. Roll them one at a time instead, keeping the others serving. The
deployment package ships `make block-roll` for exactly this.

**Assertion:** the volume reads back with the expected region, cluster, and storage.

## Stage 6: mount

Install the client with the public installer and mount the volume.

```
curl -fsSL https://mountos.sh/install | bash
```

Install one package per invocation. The installer honors only the last `--pkg` flag when
given several, with no error.

Mount from a machine that is **genuinely outside** the deployment network. Discovery hands
the client the cluster's public address, and most clouds do not route an instance's public
address back to a machine inside the same virtual network. A client placed inside the
deployment network therefore tests a path that no real user takes, and it can fail for a
reason that has nothing to do with the deployment being correct.

The mount point is a positional argument. The secret is never the value of a flag; the
secret flag is a switch that reads the value from a prompt or from standard input, which
keeps it out of the process list and the shell history. The access key id, the secret, and
the discovery URL each have an environment-variable equivalent, which is why operators keep
them in a profile file and source it for the session.

For production mounts, use the shipped mount helper and an fstab entry with an environment
file, rather than a login-shell command. See https://mountos.io/skills/volumes.md.

**Assertion:** write a file through the mount, read it back, compare the content, and
confirm the object appears in the backing store. A successful mount command alone is not
the assertion.

## Day 2

- **Upgrade.** Bump the version in the answers and the Terraform variables, then apply. The
  instance group or scale set rolls the fleet. No data is touched.
- **Re-run anything.** `apply`, `bootstrap`, and `region-bootstrap` are all idempotent.
- **Add capacity beyond the free tier.** Load a signed license through the Admin API. There
  is no redeploy.
- **Changing instance configuration needs replacement, not restart.** Startup scripts run
  once, at first boot. Editing the startup-script configuration of a running instance changes nothing on that
  instance, and a stop and start does not re-run it. Force a replacement, or roll the
  instance group or scale set. Note the converse: a stop and start preserves the private address, which
  matters when other services have that address in their configuration.
