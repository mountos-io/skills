# mountOS agent skills

Drop-in skills that teach an AI coding agent how to run [mountOS](https://mountos.io),
self-hosted POSIX-compatible distributed storage with native macOS, Linux, and Windows
mounts plus S3 and WebHDFS.

Each skill is one directory holding a `SKILL.md` and its references.

| Skill | For | Covers |
| --- | --- | --- |
| [`deploy`](deploy/) | Operator | Stand up, verify, and operate a deployment. Architecture and component interaction, the ordered bring-up, per-stage verification, and the failure modes that report healthy while the system is broken. |
| [`integrate`](integrate/) | Application developer | Add mountOS under a product that already has customers. Mapping an existing user base, credential-issuing shapes, the reconciliation loop, and picking a data surface per workload. |
| [`troubleshoot`](troubleshoot/) | On call | Diagnose a deployment that is failing. What evidence to gather in what order, which checks prove nothing, and the healthy-but-broken catalogue. |
| [`conformance`](conformance/) | Correctness testing | Run pjdfstest, LTP, and fsx against a mount, natively on Linux. Setup scripts, the mount flags that decide whether it passes, and which reported failures are configuration rather than defects. |
| [`performance`](performance/) | Measurement | Metadata rates with mdtest across directory shapes, and small-file workload timing. Read against a baseline; nothing here has a pass or fail. |

The skills are deliberately thin on reference detail. On every use they load the current
documentation from https://mountos.io, which is generated from the mountOS source, so
version-specific facts stay correct without this repository being republished.

## Install

The skills are plain Markdown and independent of each other. Nothing in them is specific to
one vendor's agent, so pick whichever route below matches your tool.

### Any agent, no install

Give it one line:

> Read https://raw.githubusercontent.com/mountos-io/skills/main/deploy/deploy.bundle.md and follow it.

Swap `deploy` for `integrate` or `troubleshoot` to load a different one. Each bundle is
self-contained.

[`deploy/deploy.bundle.md`](deploy/deploy.bundle.md) is that whole skill in one file, entry
point plus every reference, with the cross-links rewritten as in-document anchors. It works
with any agent that can fetch a URL or accept a pasted document, including ChatGPT, OpenAI
Codex, Gemini, Cursor, Windsurf, Continue, Aider, and a plain API call. Paste it into a
system prompt if your tool has no fetch.

### Clone, for the multi-file version

```bash
git clone https://github.com/mountos-io/skills.git ~/.mountos-skills
```

The multi-file form loads references on demand rather than all at once, so it costs less
context. Use it when your agent can read local files.

**Agents that read `AGENTS.md`** (OpenAI Codex, Cursor, Gemini CLI, Zed, and others) pick
this up on their own once the repository is in the workspace, because
[AGENTS.md](AGENTS.md) points at the skill.

**Claude Code**, global or per project:

```bash
for s in deploy integrate troubleshoot conformance performance; do
  ln -s ~/.mountos-skills/$s ~/.claude/skills/$s
done
```

Link only the ones you want; they are independent. Use `.claude/skills/` instead of
`~/.claude/skills/` for a single project. Each is then available by its name, for example
`/deploy`. If you already have a skill by one of these names, link it with a prefix
(`mountos-deploy`) and the agent will use that name.

**Anything else**: copy the skill directory into whatever skill or rules directory your tool
uses, or point the tool at its `SKILL.md`. Keep `references/` alongside it.

### Claude Code plugin

This repository is also a plugin marketplace, which handles install and updates for you:

```
/plugin marketplace add mountos-io/skills
```

```
/plugin install deploy@mountos
```

Each skill is a separate plugin, so `integrate@mountos` and `troubleshoot@mountos` install
the same way, independently.

The manifests live in `.claude-plugin/`. They are additive: every route above works whether
or not you use them, and they are ignored entirely by other agents.

## Versioning and upgrades

Each skill carries its own semantic version in `<skill>/VERSION`, `<skill>/skill.json`, and
the `SKILL.md` frontmatter. All three must agree; `make check` enforces that.

Two things go stale independently:

- **mountOS facts** refresh on every use, because the skill loads the current documentation
  from https://mountos.io before it acts. A new mountOS release needs no skill release.
- **The guidance in this repository** changes only when this repository does.

An agent checks for a newer release like this:

```bash
curl -fsSL https://raw.githubusercontent.com/mountos-io/skills/main/deploy/VERSION
```

and upgrades every linked skill at once:

```bash
git -C ~/.mountos-skills pull --ff-only
```

Each skill versions independently, so `integrate` can move without forcing a `deploy`
release. Version meaning is in each skill's changelog, for example
[deploy/CHANGELOG.md](deploy/CHANGELOG.md). In short: major means an agent following the
previous version would now do the wrong thing, minor means new or materially expanded
guidance, patch means corrections.

## Development

```bash
make deps      # install mermaid and jsdom for the checks
make check     # bundle freshness, diagrams, links, versions, names
make bundle    # regenerate the single-file bundles after editing a skill
make validate  # validate the Claude Code manifests, skipped if the CLI is absent
```

`make check` discovers skills by looking for `SKILL.md`, so a new skill directory is picked
up with no change to the scripts. It fails when a committed bundle is stale, so the
single-file form cannot silently drift from the multi-file one.

**Link rule, enforced by `make check`.** A relative link *inside* a skill is correct and
load-bearing: those files always ship together, so the multi-file form reads them from local
disk with no network. A relative link that *crosses* a skill boundary is rejected. Skills
install independently, so `../deploy/references/x.md` would resolve here in the repo, pass a
naive check, and be broken for anyone who installed only one skill. Reference another skill
by its absolute GitHub URL.

## Coverage and honesty

The AWS path has been deployed end to end and mounted from a genuinely external client. GCP
and Azure are validated at the configuration level and have not been applied against a real
project or subscription. The underlying service behaviour is shared across clouds, so the
failure modes apply everywhere; the cloud-specific porting is what remains unproven.
[deploy/references/clouds.md](deploy/references/clouds.md) states exactly what to check when
you are the first to run one for real.

## Related

- Documentation and topic index: https://mountos.io/llms.txt
- Install the client and the server binaries: https://mountos.sh/install
- Terraform deployment package: https://github.com/mountos-io/deployment
- Admin SDK, TypeScript, Go, and Rust: https://github.com/mountos-io/mountos-admin-sdk
- Admin dashboard: https://github.com/mountos-io/mountos-admin-client
- Support: https://mountos.io/support

## Contributing

Corrections from real deployments are the most valuable contribution, especially on GCP and
Azure. If a step failed for you, open an issue with what you ran, what happened, and what
the fix turned out to be.

## License

Apache-2.0. See [LICENSE](LICENSE).
