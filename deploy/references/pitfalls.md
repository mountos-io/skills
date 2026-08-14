# Failure modes that present as success

Every item here was found by deploying, not by review. They share one property: the system
reports healthy while it is functionally broken, so you lose hours unless you know them
first. The root causes are in shared service code, so they apply to every cloud even though
most were first hit on AWS.

The live copy of this list is in https://mountos.io/skills/deploy.md, under "Known traps".
If the two disagree, the live copy wins.

## 1. Never set an explicit advertised address on a host that has both a public and a private address

Supplying an explicit advertised address forces explicit-address mode, which mirrors that
**one** address into **both** the public and the private role. Pin it to a public address
and every peer, raft included, tries to reach that public address from inside your own
network. Most clouds do not route an instance's public address back to a machine in the same
virtual network. The failure is a silent timeout, not an error that names the cause, and the
private-address machinery looks broken when it is not.

Leave it unset so the service auto-detects the public and the private address separately
from instance metadata. The one exception is a host whose only reachable address is private,
where pinning the private address is correct.

When only the **public** half needs supplying, and that is the normal case on Azure because
its metadata does not report a VM's own public IP, use the variable that sets the public role
alone. The private address then still comes from metadata and the two roles stay distinct.
Reaching for the both-roles variable there reintroduces exactly the failure above.

Symptom: peers time out with no error text that names addressing. A dial to the same port on
the private address connects instantly.

## 2. `<svc> db install` is not idempotent

It exits non-zero with "already installed" once the schema exists. That happens on a
restart, on a replacement instance, and on the second node that shares the database. If it
runs as a hard start pre-condition, the service is blocked forever after the first
successful install.

Make it best-effort. Under systemd, prefix the `ExecStartPre=` line with `-`. This affects
appserv against the admin database and dataserv against the region database, and it only
appears on the **second** start, so a first deploy looks fine.

## 3. Co-located gcserv and dataserv collide on one port

They share one environment file and neither sets the HTTP port, so both bind the same
health and metrics port. Whichever loses crash-loops, invisibly, while the node still
reports healthy.

Give gcserv its own HTTP port **and** pin its RPC port explicitly. The RPC port derives from
the HTTP port, so moving the HTTP port alone silently moves the RPC port out from under your
firewall rules. Keep the two values well apart so later services have room.

**Deliver those overrides as a second environment file, not as systemd `Environment=` lines.**
`systemd.exec` specifies that `EnvironmentFile=` settings override `Environment=` settings
regardless of the order the lines appear in the unit. So an `Environment=` override of any key
the shared file also sets is silently discarded, and you get the shared value with no error.
Later `EnvironmentFile=` entries **do** override earlier ones, so the working pattern is a
per-service file listed after the shared one. An `Environment=` line appears to work only
while the key is absent from the shared file, which makes this fail later, when someone adds
that key.

Symptom: a node lists as healthy, but the co-located service never appears in the node list,
and its restart counter climbs steadily. For the silent-override case there is no symptom at
all; check the value the process actually received.

## 4. The installer honors only the last package flag

Passing two package flags in one invocation installs only the second one, with no error. Use
one invocation per package.

Symptom: a missing binary and a service that cannot start, with a message that points at the
service rather than at the install.

## 5. Open the peer RPC port, not only the raft port

Raft's data plane is one port, but a joining node dials an existing peer's RPC port to ask
for admission. Allow region service to region service on **both**.

With only the raft port open, the lowest-id node bootstraps alone and every other node loops
on "no peer accepted join request". You get a single-node quorum that reports healthy per
node while the cluster has no real consensus.

## 6. Client-facing ports are internet-facing by design

Client discovery, the client mount path, the client byte plane, and the admin dashboard must
be reachable from arbitrary networks. Access control is at the **application** layer:
encrypted transport plus per-volume access keys on the data path, a signed JWT on the Admin
API, token auth on the dashboard. A source-address allowlist adds nothing there and breaks
real clients.

If you do pin an allowlist to an operator's own address, note that a dynamic or residential
address rotation locks the entire environment out, and because cloud firewall rules drop rather
than reject, every request simply hangs with no error. Narrow it only for a genuinely
private deployment behind a VPN or a fixed range.

## 7. A cold fleet takes minutes to reach quorum, and that is usually normal

Records for terminated nodes linger, and deactivation can lag many hours. A fresh node waits
for those phantom peers to age out of the participant set before it bootstraps.

Measured on a three-node region: nodes healthy in about 90 seconds, full quorum at about six
minutes. The difference is staleness timeouts, not a fault.

Do **not** conclude "deadlock" and start deleting node records. Wait at least ten minutes
before you diagnose. The log lines during that window look identical to the genuine failure
in item 5. The difference is whether the peer RPC port is actually reachable, which you can
test directly.

## 8. Changing instance configuration needs replacement, not restart

Startup scripts run once, at first boot. Editing that configuration on a running instance updates
the stored attribute and changes nothing on the machine, and a stop and start does not re-run
it either. Force a replacement, or roll the instance group or scale set.

The converse matters too: a stop and start **preserves** the private address. When another
service has that address in its configuration, an in-place binary upgrade is safer than
replacing the node.

## 9. Connection pools are sized per service, and the floor dominates on small nodes

Each service holds its own pool. A three-node region with co-located gcserv is six pools,
plus the hub's. The default is derived per CPU but floored, so a small two-CPU node takes the
same pool as a much larger one.

Count total demand against the database's own connection limit, which is itself derived from
the database instance size, before you assume it fits. Override per service if you need to.
Do **not** pin a single-primary number on a distributed engine, which wants more connections,
not fewer.

When two services share an environment file, a per-service pool override has to reach the
process through a later `EnvironmentFile=`, for the reason in item 3. Assert the value the
process actually holds rather than the value you configured.

## 10. Verify the fix, not the deploy

Several of these produce a healthy-looking service that is functionally broken: a single-node
"quorum", a crash-looping co-located service, an addressing feature silently using the wrong
address family. After any addressing, clustering, or port change, assert the specific
invariant. See [verification.md](verification.md).

## 11. Test the mount from outside the deployment network

Discovery hands the client the cluster's client-facing address. A test client placed inside
the deployment's own network hits the same address-routing limitation as item 1, so it can
fail for a reason unrelated to whether the deployment is correct, or pass only because an
internal-preference setting routed it a way no real user takes.

Put the test client somewhere genuinely external. A small instance in a different network in
the same account is enough.

## 12. Do not pass secrets through a remote-command API

Parameters to a cloud provider's run-command service are recorded in that provider's audit
log. Use an interactive session, and have the operator place credentials themselves.
