# mountOS troubleshoot skill (single-file bundle, version 1.0.0)

This file is the entire skill in one document: the entry point followed by every
reference it links to. It exists for agents that cannot follow relative links or read
a directory. The links below point at sections in this same file.

Source and updates: https://github.com/mountos-io/skills

---


# mountOS troubleshooting

Something is wrong with a running [mountOS](https://mountos.io) deployment. This skill is
about **method**: what to gather, in what order, and which checks prove nothing.

The symptom-to-fix catalogue lives in the live documentation and is regenerated from source,
so it stays correct. Read it, do not memorise it. What it cannot give you is the discipline
below, which is where unaided diagnosis usually goes wrong.

## Step 0: load the live context first

**Before you form a hypothesis.**

| Order | URL | What it gives you |
| --- | --- | --- |
| 1 | https://mountos.io/ai/topics/troubleshooting.md | Symptom-indexed catalogue with the fixes |
| 2 | https://mountos.io/skill.md | The mental model, so you route to the right layer |
| 3 | https://mountos.io/skills/env.md | What a variable actually does, when config is suspect |
| 4 | https://mountos.io/skills/operate.md | Day-2 procedures, when the fix is an operation |

Where this repository and the live documentation disagree, the live documentation wins.

## The rule that matters most

**A healthy status is not evidence that the thing works.**

Several mountOS failure modes produce a service that reports healthy and is functionally
broken: a single node that believes it is a quorum, a co-located service that crash-loops
while its host still reports healthy, an addressing feature that silently uses the wrong
address family, a per-service override that was discarded without an error.

So the diagnostic question is never "is it healthy". It is **"what specific invariant should
hold, and does it".** [references/method.md](#reference-method) makes that concrete.

## Gather before you theorise

In this order. Each step is cheap and rules out a layer.

1. **What changed, and when.** A deployment that "worked yesterday" changed: a version, a
   firewall rule, an instance replacement, a credential rotation, an ISP address. Get the
   timestamp of the first failure and what happened just before it.
2. **Which layer.** Client, network, or fleet. The next section splits this in one step.
3. **On the client**, `mountos check`. It verifies the mount backends on that machine and
   prints the exact fix for every failing check, per platform. Client logs are under
   `~/.mountOS/logs/` on macOS and Linux.
4. **On a node**, the service's own log and its restart counter. A climbing restart counter
   on a node that lists as healthy is the signature of a crash-looping co-located service.
5. **Live state**, without changing anything: `<service> dashboard` on a node,
   `mountos dashboard <mount-path>` on a client, and the admin dashboard's alerts and nodes
   views.
6. **The read-only MCP connector**, when an agent is doing the work. `mountos mcp install`
   registers it once. It exposes instances, identity, live stats and throughput, recent
   deletions, recovered files, configuration, diagnostics, and version history. It never
   reads file contents and never mutates state, so it is safe against production mounts.

## Split the problem in one step

Most time is lost working the wrong layer. This split costs one command each.

| Question | How to answer it | What it rules out |
| --- | --- | --- |
| Is it this client, or everyone? | Mount the same volume from a different machine | The client host, its backend, its local config |
| Is it the network, or the service? | Connect to the port directly from the same source | Everything above the transport |
| Is it this node, or the cluster? | Ask another node the same question | A single bad instance |
| Is it this volume, or all volumes? | Same operation on a second volume | Volume-specific state and quota |
| Is it auth, or the data path? | An unauthenticated call that should 401 | Credential problems entirely |

A connection that **hangs** rather than refusing is nearly always a firewall dropping
packets, not an application fault. Dropped packets produce a timeout with no error naming
the cause. That distinction is worth checking before reading any application log.

## Know what is normal before calling it broken

Two mountOS behaviours look like faults and are not:

- **A cold fleet takes minutes to reach quorum.** Records for terminated nodes linger, and a
  fresh node waits for those phantom peers to age out before it bootstraps. Measured on a
  three-node region: nodes healthy in about 90 seconds, full quorum at about six minutes.
  Wait at least ten minutes before diagnosing, and do not start deleting node records. The
  log lines during that window are nearly identical to a genuine firewall failure; the
  difference is whether the peer RPC port is actually reachable, which you can test.
- **Registration retries are the normal state** for a service whose cluster is not ready
  yet. It is only a fault if it never converges.

## Route the symptom

| Symptom | Start at |
| --- | --- |
| Mount fails, or the client cannot discover | `mountos check` on that host, then the live troubleshooting topic |
| Service will not register | [references/method.md](#reference-method), registration section |
| Service exits at boot | Its log first: config, license, and secret-store failures are distinct and each names itself |
| Quorum will not form | [references/method.md](#reference-method), quorum section |
| Node healthy but serving nothing | [references/method.md](#reference-method), the healthy-but-broken catalogue |
| Gateway rejects requests | Check the signing service name and the endpoint the signer saw |
| Everything is slow | [references/method.md](#reference-method), performance section |
| It worked yesterday | Start with what changed, above |

## Hard rules while diagnosing

- **Change one thing at a time**, and check the invariant after each. Two simultaneous
  changes mean you cannot attribute the result.
- **Read before you write.** Every step above is read-only. Nothing in diagnosis should
  mutate state until you have a hypothesis you can state.
- **Do not delete records to make an error go away.** Stale node records look like the cause
  of a stuck quorum and are usually not; deleting them removes the evidence and can "fix"
  something that was about to self-correct.
- **Never paste a secret into a shell, a log, or a ticket** while gathering evidence. Ask
  the operator to check credentials themselves.
- **Do not restart to see if it helps** before you have captured the current state. A
  restart destroys the evidence, and several of these failure modes only appear on the
  *second* start.

## Before you say it is fixed

- You checked the thing that was broken, not a general health endpoint.
- You checked it on every node, not the first one.
- You waited long enough for the change to take effect, and you know how long that is.
- **If the check would have passed for a reason other than your fix, you would be able to
  tell.** If you cannot answer this one, the check is too weak.

## What is in this repository

- [references/method.md](#reference-method): the healthy-but-broken catalogue, and the
  per-area diagnostic procedures for registration, quorum, addressing, and performance.

Related skills in https://github.com/mountos-io/skills: `deploy` for standing a deployment
up, including the failure modes introduced at deploy time, and `integrate` for wiring
mountOS under an existing product.


---

<a id="reference-method"></a>

## Diagnostic method by area

The procedures behind the `troubleshoot` skill. Each section names the invariant that should
hold, how to test it, and the failure that mimics it.

The symptom-to-fix catalogue is at https://mountos.io/ai/topics/troubleshooting.md and is
regenerated from source. This file is the part that catalogue cannot carry: what proves a
thing, and what only looks like proof.

### The healthy-but-broken catalogue

Every entry here reports healthy while being functionally broken. They are the reason the
first question is never "is it healthy".

| What you see | What is actually true | The check that distinguishes it |
| --- | --- | --- |
| Every node healthy, cluster ready | One node bootstrapped alone; the others never joined | Exactly one leader **and** every other node joined to it, not just N healthy nodes |
| Node healthy, a co-located service missing from the node list | That service crash-loops on a port collision | Its restart counter over time; flat is fine, climbing is not |
| Private-address feature enabled, peers still time out | One address was mirrored into both roles | Two **distinct** addresses discovered per node, and the peer path using the private one |
| A per-service override configured | It was silently discarded | Read the value the **process** holds, not the file it came from |
| Service registered and serving | It advertises an address nobody external can reach | Connect from genuinely outside the deployment network |
| Mount succeeds | Data path untested; only discovery and auth were proven | Write, read back, compare content, and confirm it reached the backing store |

The last one is the most common false positive in a first deployment. A successful mount
command proves the client found the cluster and authenticated. It proves nothing about
whether bytes move.

### Registration

**Invariant:** the service resolved its identity and addresses, reached the hub, and the hub
accepted it.

Registration failures are usually one of four things, and each names itself in the service's
own log if you read it before restarting:

1. **Config**: a required variable missing or malformed. Fails immediately and says which.
2. **Secret store**: the service started, then could not read its secrets. If a resource
   prefix is in use, both sides must agree on it; a prefix set on one side only produces a
   service that starts and then fails on missing configuration, which reads like a config
   bug but is not.
3. **Addressing**: no usable address discovered. On a platform whose metadata does not report
   a public address, this is expected and the address must be supplied.
4. **Topology**: the cluster id is unknown or deactivated. The service refuses deliberately,
   raises a topology alert, and retries. This is correct behaviour preventing it joining the
   wrong cluster, not a fault to work around.

**Retrying forever is only a fault if it never converges.** A service whose cluster is not
ready yet is supposed to retry.

### Quorum

**Invariant:** one leader elected, and every other node joined to that leader.

"All nodes healthy" does not imply this. A node that bootstrapped alone is healthy, serves
requests, and has no real consensus.

Two failures produce nearly identical logs:

- **A firewall gap.** The join handshake and the raft data plane use *different* ports. With
  only the data-plane port open, the lowest-id node bootstraps alone and every other node
  loops forever on a join error. Test the peer RPC port directly between two nodes.
- **Normal cold-start delay.** Records for terminated nodes linger, and a fresh node waits
  for those phantom peers to age out. This self-corrects in about six minutes on a three-node
  region.

The distinguishing test is reachability, not the log text. If the peer RPC port answers
between nodes, wait. If it does not, fix the rule.

Do not delete node records to accelerate this. It removes evidence and can "fix" something
that was about to correct itself, which teaches you the wrong lesson for next time.

### Addressing

**Invariant:** each node discovered two distinct addresses, and each is used for its own
role. Peers and internal RPC use the private one; clients use the public one.

The failure is silent by construction. When one address is mirrored into both roles, every
peer tries to reach a public address from inside the deployment network, and most clouds do
not route that back. The result is a timeout with nothing in the log naming addressing as
the cause, and the private-address machinery looks broken when it is not.

Test it directly: from one node, connect to another node's private address on the peer port,
then to its public address on the same port. If private connects and public hangs, you have
found it.

This is also why a test client must sit **outside** the deployment network. A client inside
it hits the same limitation and can fail for reasons unrelated to whether the deployment is
correct.

### Configuration that was silently discarded

**Invariant:** the value the process holds is the value you configured.

A per-service override can be accepted by the configuration system and then lost, with no
error anywhere. Two mechanisms do this:

- **Environment-file precedence.** Under systemd, `EnvironmentFile=` settings override
  `Environment=` settings regardless of the order the lines appear in the unit. An
  `Environment=` override of a key that a shared environment file also sets is discarded
  silently. Later `EnvironmentFile=` entries **do** override earlier ones, which is the
  mechanism that works.
- **A derived value moving.** Some ports derive from another port. Change the base and the
  derived one moves too, potentially outside the firewall rule that was written for it.

Always read back what the running process actually has, not the file you edited. On Linux:

```sh
tr '\0' '\n' < /proc/<pid>/environ | grep <VAR>
```

### Gateways

**Invariant:** the request was signed for the surface it reached.

The S3 and WebHDFS surfaces use different signing service names. Pointing an S3 signer at
the WebHDFS surface fails authentication in a way that reads like a credential problem.

Signatures also cover the host. If the endpoint the client signed differs from what the
gateway saw, for example because a proxy rewrote it, the signature will not verify. Check
what the gateway received, not what the client intended to send.

### Performance

**Invariant:** you measured, and you know which layer.

Before changing any setting, establish which layer is slow: metadata operations, byte
throughput, or the backing store. They have different causes and no shared fix, and tuning
the wrong one wastes the change budget and muddies the next measurement.

- Metadata-heavy workloads are bounded by the metadata service and its cache, not by
  throughput. If the working set exceeds the cache, the fix is sizing, not concurrency.
- Byte throughput is bounded by the client, the network, and the object store. The metadata
  service is not in that path for object-backed volumes.
- Connection pools are held **per service**. Count total demand across every service against
  the database's own connection limit before assuming there is headroom.

Confirm the value the service actually adopted, in its own startup log, rather than assuming
the configured value took effect. That single habit catches a large share of "the tuning did
nothing" reports.

### When you cannot reproduce it

- Get the exact timestamp of a real failure and look at that window, not at now.
- Ask what is different about the affected client: its network, its platform, its version.
- Check whether it correlates with an event: an instance replacement, a rotation, a rolling
  upgrade, an address change.
- If it is intermittent, prefer capturing state during a failure to reasoning about a
  healthy system. A mount's read-only connector can be queried while the problem is live.
