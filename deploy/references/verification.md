# Verification: what "done" means at each stage

A command exiting zero is not an assertion. Several mountOS failure modes leave a service
reporting healthy while it is functionally broken, so each stage below names the specific
invariant and the check that proves it.

Run these against the operator's deployment with their own credentials. Do not print secrets
in the process of checking.

## Hub is up

**Invariant:** the Admin API answers, enforces auth, and reaches its database.

- An unauthenticated call to `/api/v1/*` is rejected. A 401 here is a pass, not a failure.
- A signed admin call returns data.
- The service log shows the database connection verified and the secret store initialised
  with the expected provider.
- The hub's own reserved region and cluster appear as self-registered.

Failure to watch for: the service starts, then fails to read its secrets and exits on
missing configuration. If a resource prefix is in use, the secret names the service reads
must carry the same prefix that the infrastructure created.

## Region services are up

**Invariant:** every node registered, and the cluster has a real quorum.

- The cluster reports ready.
- The node list shows every dataserv node **and** every gcserv node, healthy, at the version
  you expect. A missing gcserv is the port collision in [pitfalls.md](pitfalls.md) item 3.
- Exactly one dataserv node is the leader, and the others are joined to it. One node
  claiming leadership while the others loop on a join error is a single-node cluster
  pretending to be a quorum.
- The advertised addresses are **two distinct addresses** per node, one public and one
  private, and the raft peer address is the private one. One address in both roles is
  [pitfalls.md](pitfalls.md) item 1.
- Restart counters are flat. A steadily climbing counter on a healthy-looking node is a
  crash loop.
- The arena size in the service's own startup log matches what you configured. Do not trust
  the configured value alone.

Give a cold fleet at least ten minutes before you diagnose a join problem. See
[pitfalls.md](pitfalls.md) item 7.

## Volume is usable

**Invariant:** the volume reads back with the region, cluster, and storage you intended, and
a key pair was issued.

- Read the volume back by id and check its region, cluster, and storage.
- The generate call returned a key pair. Note whether it reported evicted keys; if it did,
  anything caching an older pair for that user must be updated.

## Mount works

**Invariant:** data written through the mount is real data in the backing store.

- Mount from a machine **outside** the deployment network.
- Write a file, read it back, and compare the content, not only the size.
- Confirm the object appears in the backing store.
- Unmount and remount, then read the same file again. This catches state that only existed
  in the client's cache.

A successful mount command alone proves discovery and auth, not the data path.

## After any addressing, clustering, or port change

Re-assert the specific thing you changed. Concretely:

| You changed | Assert |
| --- | --- |
| An advertised address | Two distinct addresses discovered per node, and raft using the private one |
| A firewall rule | The specific port is reachable between the specific pair of hosts, tested directly |
| A service port | The service is listening on the new port **and** its derived RPC port is where the firewall expects it |
| The node count | Leader elected, and every node joined, not just every node healthy |
| A binary version | The running version reported by the service itself, on every node, not the version you installed |
| A database pool setting | Total connections across every service against the database's own limit |

## Before you report a stage complete

Ask yourself which of these is true:

- I checked the thing that was broken, not a general health endpoint.
- I checked it on every node, not on the first one.
- I checked it after the change had time to take effect, and I know how long that is.
- If the check passed for a reason other than my fix, I would be able to tell.

If you cannot answer the last one, the check is too weak.
