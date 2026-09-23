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
- The hub's own reserved region and metadata cluster appear as self-registered.

Failure to watch for: the service starts, then fails to read its secrets and exits on
missing configuration. If a resource prefix is in use, the secret names the service reads
must carry the same prefix that the infrastructure created.

## Region services are up

**Invariant:** every node registered, and the metadata cluster has a real quorum.

- The metadata cluster reports ready.
- The node list shows every dataserv node **and** every gcserv node, healthy, at the version
  you expect. A missing gcserv is the port collision in [pitfalls.md](pitfalls.md) item 3.
- Exactly one dataserv node is the leader, and the others are joined to it. One node
  claiming leadership while the others loop on a join error is a single-node metadata
  cluster pretending to be a quorum.
- The advertised addresses are **two distinct addresses** per node, one public and one
  private, and the peer address used for replication is the private one. One address in
  both roles is [pitfalls.md](pitfalls.md) item 1.
- Restart counters are flat. A steadily climbing counter on a healthy-looking node is a
  crash loop.
- The arena size in the service's own startup log matches what you configured. Do not trust
  the configured value alone.

Give a cold fleet at least ten minutes before you diagnose a join problem. See
[pitfalls.md](pitfalls.md) item 7.

## Volume is usable

**Invariant:** the volume reads back with the region, metadata cluster, and storage you
intended, and a key pair was issued.

- Read the volume back by id and check its region, metadata cluster, and storage.
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

## Block storage network tuning

**Invariant:** every blockserv host has the network tuning from the host network tuning
section in [runbook.md](runbook.md).

- Open each blockserv node in the admin dashboard. The node detail shows these rows:

  | Row | Metadata key | Value |
  | --- | --- | --- |
  | Network Tuned | `net_tuned` | "Yes" when the host meets the target, "Below target" when it does not |
  | Congestion Control | `net_cc` | The TCP congestion control that block data connections use, for example `bbr` |
  | Queue Discipline | `net_qdisc` | The default queueing discipline, for example `fq`. A node in a container with its own network (for example a bridge network) does not show this row |
  | Receive Buffer Max | `net_rmem_max` | The third value of `net.ipv4.tcp_rmem` (bytes in the metadata). The dashboard shows it in binary units, for example "64 MB" for 67108864 |
  | Send Buffer Max | `net_wmem_max` | The third value of `net.ipv4.tcp_wmem` (bytes in the metadata). The dashboard shows it in binary units, for example "64 MB" for 67108864 |

  When the node cannot read a value, the node detail does not show that row. The node
  compares only the values that it can read with the target.

  - When one of these values is below the target, "Network Tuned" shows "Below target",
    and the node raises the alert.
  - When all of these values meet the target, but the node cannot read one of the target
    values, "Network Tuned" shows "Not reported". The node does not raise the alert, and it
    clears the alert of an earlier start.
  - When the node can read no value, "Network Tuned" is the only network tuning row in the
    node detail, and it shows "Not reported".
  - When the congestion control is the cause of "Below target", the node detail also shows
    the system default congestion control ("System Default"). In that case, when a
    per-process override is set, the node detail also shows that override ("Per-Socket
    Override").

- The target is 33554432 bytes (32 MiB) or more for both buffer maximums, and the `bbr`
  congestion control. The provided tuning file sets 67108864.
- "Network Tuned" must show "Yes" on every node. A node below target raises a health alert
  titled "Host network tuning below target". The alert message shows the current values and
  the target values. It shows the congestion control of the block data connections and the
  system default as two values. When a per-process override sets the congestion control, the
  message names that override as the source of the value. At startup, the node also writes
  `host network tuning below target` to its log.
- A client session shows a "Network Tuning" section in the admin dashboard. It shows the
  client host's settings. Use it when one client is slow and the others are not. On
  Windows, the section shows "not supported". On other systems, the client uses the same
  rule as the node. A value that the client can read and that is below the target shows the
  client as below target. A missing value, with all other values at the target, shows "not
  reported". On Linux, the section shows the congestion control in one row.

## After any addressing, clustering, or port change

Re-assert the specific thing you changed. Concretely:

| You changed | Assert |
| --- | --- |
| An advertised address | Two distinct addresses discovered per node, and replication using the private one |
| A firewall rule | The specific port is reachable between the specific pair of hosts, tested directly |
| A service port | The service is listening on the new port **and** its derived RPC port is where the firewall expects it |
| The node count | Leader elected, and every node joined, not just every node healthy |
| A binary version | The running version reported by the service itself, on every node, not the version you installed |
| A database pool setting | Total connections across every service against the database's own limit |
| Host network tuning | "Network Tuned" is "Yes" on every blockserv node (metadata `net_tuned` = `true`), and no "Host network tuning below target" alert is open |

## Before you report a stage complete

Ask yourself which of these is true:

- I checked the thing that was broken, not a general health endpoint.
- I checked it on every node, not on the first one.
- I checked it after the change had time to take effect, and I know how long that is.
- If the check passed for a reason other than my fix, I would be able to tell.

If you cannot answer the last one, the check is too weak.
