# Cloud coverage, and how to extrapolate safely

The `mountos-io/deployment` package supports `aws`, `gcp`, and `azure` behind the same make
targets and the same bootstrap scripts. The **confidence** in each is not the same. Say so
to the operator before an unattended apply.

## What is proven, and how

| Cloud | Level | What that means |
| --- | --- | --- |
| AWS | Deployed and verified end to end | Hub, region, three-node quorum, volume, and a real mount from an external client. Every item in [pitfalls.md](pitfalls.md) was found here. |
| GCP | Configuration-validated only | The graph is schema-correct and lints clean. It has not been applied against a real project. |
| Azure | Configuration-validated only | Same as GCP. Not applied against a real subscription. |

The service-side root causes behind the pitfalls list are in shared code, so they apply to
every cloud. The AWS-proven fixes have been ported to the GCP and Azure trees. The **port**
is unverified at runtime, which is a different claim from the fixes being wrong.

## Checklist when you apply on GCP or Azure

Work through this before and during the first real apply. Each item is a place where the
provider differs enough that a correct AWS pattern can still fail.

1. **Instance metadata does not always carry the public address.** The private one is
   reliable everywhere. The public one is not. On **Azure** the instance-metadata field for
   a VM's own public IPv4 only ever served Basic-SKU addresses, and Basic SKU reached end of
   life in September 2025, so on any current deployment it is empty. The Load Balancer
   Metadata API does report an instance's own address, but returns 404 for a VM that is not
   behind a standard load balancer. A machine with a static public IP and no load balancer
   therefore has no metadata path to its own public address at all.

   Do not paper over this with a retry loop; it will time out on every boot forever. Supply
   the public address instead, through the variable that sets **only** the public role, so
   the private one is still auto-detected. Where the address is known when you provision
   (a static IP attached to the interface) template it in. Where it is allocated per
   instance from a pool, the instance has to ask the cloud's own API for it, using an
   instance identity rather than a stored credential.

   Whatever path you use, a missing value must cause a hard exit rather than an empty
   variable that flows onward into registration.
2. **Address attachment timing.** A static or reserved public address may attach slightly
   after the machine boots. A startup script that reads the address immediately can capture
   an ephemeral one. Poll until the expected address appears, and fail hard on timeout.
3. **Firewall model.** The rule that allows region service to region service on the peer RPC
   port must actually match. On GCP that means source and target tags or service accounts,
   not a source range. On Azure it means a network security group rule whose priority does
   not collide with an existing rule in the same group. Verify the chosen priority is free.
4. **Managed database password.** Neither GCP nor Azure has the AWS behaviour where the
   platform owns and rotates the master password and it never becomes a Terraform value. On
   GCP and Azure a provisioned database's master password **is** a Terraform value and is
   present in state. Bringing your own database avoids this entirely, and is the recommended
   production path on every cloud.
5. **Certificates.** Azure has no zero-touch DNS-validated managed certificate equivalent.
   The hub certificate must be supplied by the operator into the key vault.
6. **Secret name prefix.** If a resource prefix is in use, both the infrastructure and the
   service must agree on it. The service reads its secrets by name, so a prefix set on one
   side only produces a service that starts and then fails on missing configuration. This is
   invisible when the prefix is empty, because both sides then agree on the bare name.
7. **Instance group repair.** An auto-repairing instance group or scale set turns a service that cannot
   start into an endless recreate loop. This is exactly what [pitfalls.md](pitfalls.md) item
   2 causes when the schema install runs as a hard start pre-condition.
8. **One package per installer invocation.** The installer behaviour in
   [pitfalls.md](pitfalls.md) item 4 is provider-independent. Check every startup script.
9. **Port assignments for co-located services.** Item 3 is provider-independent as well.
   Check that the co-located service has its own HTTP port and an explicitly pinned RPC
   port, and that the firewall rule references the same RPC port.
10. **Test the mount from outside.** The address-routing limitation behind item 1 exists on
    GCP and Azure as well. A client inside the deployment network is not a valid test.

## If you are the first to run a cloud for real

Tell the operator plainly that they are the first, agree a small non-production environment
for the first attempt, and keep a record of what failed and why. That record is worth more
than the deployment. Feed it back to https://mountos.io/support so the next operator does
not repeat it.
