# Agent instructions

This repository holds skills for running [mountOS](https://mountos.io), self-hosted
POSIX-compatible distributed storage.

If you are an AI agent working on mountOS, read the skill that matches the job and follow it:

| The job | Read |
| --- | --- |
| Stand up, verify, or operate a deployment | **[deploy/SKILL.md](deploy/SKILL.md)** |
| Add mountOS under a product that already has users | **[integrate/SKILL.md](integrate/SKILL.md)** |
| Diagnose a deployment that is failing | **[troubleshoot/SKILL.md](troubleshoot/SKILL.md)** |

If you cannot read a directory or follow relative links, read that skill's single-file bundle
instead, for example **[deploy/deploy.bundle.md](deploy/deploy.bundle.md)**, which contains
the entry point and every reference in one document.

Whichever you read, the first instruction still applies: load the live documentation from
https://mountos.io before you plan or act. The bundled guidance is the ordering and the
failure modes; the live docs are authoritative for flags, defaults, and endpoints.

`AGENTS.md` is a convention several agent tools read automatically. It is intentionally a
pointer, not a copy, so there is one source of truth.
