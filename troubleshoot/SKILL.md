---
name: troubleshoot
description: Diagnose a mountOS deployment that is failing or behaving wrongly. Use when a mount will not work, a service will not register or keeps restarting, a cluster will not reach quorum, a gateway rejects requests, a node reports healthy but serves nothing, performance dropped, or an operator says "it worked yesterday". Covers what evidence to gather in what order, which checks are too weak to prove anything, and the mountOS failure modes that report healthy while the system is broken.
version: 1.0.0
license: Apache-2.0
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
hold, and does it".** [references/method.md](references/method.md) makes that concrete.

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
| Service will not register | [references/method.md](references/method.md), registration section |
| Service exits at boot | Its log first: config, license, and secret-store failures are distinct and each names itself |
| Quorum will not form | [references/method.md](references/method.md), quorum section |
| Node healthy but serving nothing | [references/method.md](references/method.md), the healthy-but-broken catalogue |
| Gateway rejects requests | Check the signing service name and the endpoint the signer saw |
| Everything is slow | [references/method.md](references/method.md), performance section |
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

- [references/method.md](references/method.md): the healthy-but-broken catalogue, and the
  per-area diagnostic procedures for registration, quorum, addressing, and performance.

Related skills in https://github.com/mountos-io/skills: `deploy` for standing a deployment
up, including the failure modes introduced at deploy time, and `integrate` for wiring
mountOS under an existing product.
