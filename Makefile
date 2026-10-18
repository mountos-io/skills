RUNNER := $(shell command -v bun 2>/dev/null || command -v node 2>/dev/null)

.PHONY: help check bundle bundle-check deps version validate

help:
	@echo "check         verify diagrams, links, versions, names, and bundle freshness"
	@echo "bundle        regenerate the single-file bundle for each skill"
	@echo "validate      validate the Claude Code plugin and marketplace manifests"
	@echo "deps          install the check dependency (pele)"
	@echo "version       print each skill's version"

deps:
	@command -v bun >/dev/null 2>&1 && bun add --dev pele || npm install --no-save pele

check: bundle-check
	@test -n "$(RUNNER)" || { echo "need bun or node on PATH"; exit 1; }
	@$(RUNNER) scripts/check.mjs

bundle:
	@test -n "$(RUNNER)" || { echo "need bun or node on PATH"; exit 1; }
	@$(RUNNER) scripts/bundle.mjs

bundle-check:
	@test -n "$(RUNNER)" || { echo "need bun or node on PATH"; exit 1; }
	@$(RUNNER) scripts/bundle.mjs --check

# Claude Code specific. Other agents need no manifest; see README.
validate:
	@command -v claude >/dev/null 2>&1 || { echo "claude CLI not installed; skipping"; exit 0; }
	@claude plugin validate .
	@for d in */; do [ -f "$$d/.claude-plugin/plugin.json" ] && claude plugin validate "./$${d%/}"; done; true

version:
	@for d in */; do [ -f "$$d/VERSION" ] && printf '%s %s\n' "$${d%/}" "$$(cat $$d/VERSION)"; done
