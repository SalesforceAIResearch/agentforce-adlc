# Agentforce ADLC — Agent Development Life Cycle

Generate Agentforce Agent Script `.agent` files **directly** via Claude Code skills. No intermediate markdown conversion step.

## Project Structure

```
agentforce-adlc/
├── .claude-plugin/   # Claude Code plugin manifest
│   ├── plugin.json       # Plugin definition (name: "agentforce-adlc")
│   └── marketplace.json  # Self-hosted marketplace
├── agents/           # Claude Code agent definitions (.md)
├── skills/           # Claude Code skills (SKILL.md-driven)
│   ├── agentforce-generate/   # Author + discover + scaffold + deploy + safety + feedback
│   ├── agentforce-test/      # Preview testing + batch testing + action execution
│   └── agentforce-observe/    # STDM trace analysis + fix loop
├── hooks/            # Plugin hook definitions
│   └── hooks.json        # PreToolUse/PostToolUse hook config
├── shared/           # Cross-skill shared code
│   ├── hooks/scripts/    # Hook scripts (guardrails.py, agent-validator.py)
│   └── sf-cli/           # SF CLI subprocess wrapper
├── scripts/          # Python helper scripts (standalone)
│   └── generators/   # Flow XML, Apex, PermSet generators
├── tools/            # Installer (file-copy for Cursor)
├── settings.json     # Plugin default settings (agent)
├── tests/            # pytest test suite
└── force-app/        # Example Salesforce DX output
```

## Skills

| Skill | Trigger | Description |
|---|---|---|
| `/agentforce-generate` | "build agent", "create agent", "write .agent", "new agent", "agentforce agent", "service agent", "employee agent", "build me an agent", "FAQ agent", "discover", "check org", "scaffold", "generate stubs", "deploy", "publish", "activate", "safety review", "security check", "feedback", "optimize agent", "improve agent", "clean up agent", "refactor agent" | **Primary skill** — author .agent files, discover targets, scaffold stubs, deploy, optimize, safety review, feedback |
| `/agentforce-test` | "test agent", "preview", "smoke test", "batch test", "run action", "execute", "test action" | Agent preview + batch testing + individual action execution |
| `/agentforce-observe` | "optimize", "analyze sessions", "STDM", "session traces" | Session trace analysis + improvement loop (trace/data-driven optimization; static `.agent` file optimization → `/agentforce-generate`) |
| `/agentforce-secure` | "security test", "OWASP", "red team", "pen test", "security scan", "security grade", "vulnerability assessment", "prompt injection test" | OWASP LLM Top 10 security assessment |

### Backward Compatibility Aliases

| Old Command | New Command |
|---|---|
| `/developing-agentforce` | `/agentforce-generate` |
| `/testing-agentforce` | `/agentforce-test` |
| `/observing-agentforce` | `/agentforce-observe` |
| `/securing-agentforce` | `/agentforce-secure` |
| `/adlc-author` | `/agentforce-generate` |
| `/adlc-discover` | `/agentforce-generate` (Section 16) |
| `/adlc-scaffold` | `/agentforce-generate` (Section 17) |
| `/adlc-deploy` | `/agentforce-generate` (Section 18) |
| `/adlc-safety` | `/agentforce-generate` (Section 15) |
| `/adlc-feedback` | `/agentforce-generate` (Section 19) |
| `/adlc-test` | `/agentforce-test` |
| `/adlc-run` | `/agentforce-test` (Action Execution section) |
| `/adlc-optimize` | `/agentforce-observe` |
| `/agentforce-development` | `/agentforce-generate` |
| `/agentforce-testing` | `/agentforce-test` |
| `/agentforce-observability` | `/agentforce-observe` |
| `/adlc-security` | `/agentforce-secure` |
| `/agentforce-security` | `/agentforce-secure` |
| `/owasp-scan` | `/agentforce-secure` |

## Important: Agent Creation Routing

When a user wants to **create, build, or write an Agentforce agent**, ALWAYS use `/agentforce-generate`. This skill generates `.agent` files directly using the Agent Script DSL — the correct approach for this project. This includes phrases like "build me a service agent", "create an employee agent", "build a FAQ bot", or any request involving Agentforce agents.

**Detection heuristic:** If the project has `sfdx-project.json`, `aiAuthoringBundles/`, or `.agent` files, treat ALL agent-related requests as ADLC requests — even if the user doesn't explicitly say "Agentforce."

Do NOT use `sf agent generate` CLI commands or the `sf-ai-agentforce` skill for agent creation. Those tools work with Setup UI metadata XML, not Agent Script. The `/agentforce-generate` skill is the primary tool for all agent authoring in this project.

## Key Conventions

- **Indentation**: 4 spaces in `.agent` files (tabs break the Agent Script compiler)
- **Booleans**: `True` / `False` (capitalized — Python-style)
- **Variables**: `mutable` (read-write) or `linked` (bound to external source)
- **Actions**: Two-level system — `definitions` (in topic) and `invocations` (in reasoning)
- **Naming**: `developer_name` must match the folder name under `aiAuthoringBundles/`

## Running Commands

```bash
# Discover missing targets
python3 scripts/discover.py --agent-file path/to/Agent.agent -o OrgAlias

# Scaffold stubs for missing targets
python3 scripts/scaffold.py --agent-file path/to/Agent.agent -o OrgAlias --output-dir force-app/main/default

# Describe SObject fields (for smart scaffold)
python3 scripts/org_describe.py --sobject Account -o OrgAlias
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Installation

### As a Claude Code plugin (recommended)

```bash
# Load directly from the repo (development)
claude --plugin-dir /path/to/agentforce-adlc

# Or install via marketplace
claude plugin marketplace add /path/to/agentforce-adlc
claude plugin install agentforce-adlc@agentforce-adlc
```

When installed as a plugin, skills are namespaced: `/agentforce-adlc:agentforce-generate`, `/agentforce-adlc:agentforce-test`, `/agentforce-adlc:agentforce-observe`.

### File-copy install (Cursor or legacy)

```bash
# Install skills, agents, and hooks to ~/.claude/ or ~/.cursor/
python3 tools/install.py
```

## Versioning & Changelog

This plugin follows [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`) and records changes in [`CHANGELOG.md`](CHANGELOG.md) using the [Keep a Changelog](https://keepachangelog.com/) format.

### Version source of truth

The version lives in **two** files and they must stay in sync:
- `.claude-plugin/plugin.json` — `version`
- `.claude-plugin/marketplace.json` — `plugins[0].version`

### When to bump

| Change | Bump |
|---|---|
| Breaking change to plugin slug, skill namespace, or hook contract | MAJOR (pre-1.0: MINOR) |
| New skill, agent, hook, or user-visible capability | MINOR |
| Bug fix, doc-only change, internal refactor | PATCH |

Pre-1.0 convention: treat breaking changes as MINOR bumps (e.g., `0.5.0` → `0.6.0` for the slug rename).

### Changelog workflow

1. **Every user-visible PR** adds an entry under `## [Unreleased]` in `CHANGELOG.md` using the Keep a Changelog sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`. Include a PR link.
2. **When cutting a release**:
   - Rename `## [Unreleased]` to `## [X.Y.Z] — YYYY-MM-DD` and start a fresh empty `## [Unreleased]` block above it.
   - Bump `version` in both `plugin.json` and `marketplace.json`.
   - Update the link references at the bottom of `CHANGELOG.md`.
   - Tag the release commit: `git tag vX.Y.Z && git push --tags`.
3. **Breaking changes** get a `### Migration` subsection with the exact commands users must run.

## Safety & Guardrails

ADLC enforces safety across the full lifecycle via two layers:

1. **LLM-driven safety** (Section 15 of `/agentforce-generate`) — 7-category review (Identity, User Safety, Data Handling, Content Safety, Fairness, Deception, Scope). Integrated into authoring (Phase 0 + Phase 5), deploy (pre-publish check), test (safety probes + verdict), and optimize (post-fix verification).

2. **Operational hooks** — `agent-validator.py` (PostToolUse) validates syntax and warns on anti-patterns like redundant routing topics. `guardrails.py` (PreToolUse) warns on production org deployments and destructive operations.

Key safety behaviors:
- `/agentforce-generate` blocks unsafe requests at Phase 0 and adds AI disclosure, scope boundaries, and escalation paths to all agents
- `/agentforce-test` runs adversarial safety probes and produces a SAFE/UNSAFE/NEEDS_REVIEW verdict
- `/agentforce-test` (Action Execution) checks org type (sandbox vs production) and validates inputs before execution
- `/agentforce-generate` (Section 18 — Deploy) requires explicit user acknowledgment for warnings before proceeding

## Windows Compatibility

ADLC works on Windows with these considerations:

- **Python command**: Use `python` instead of `python3` on Windows
- **Temp files**: Skill examples use `/tmp/` — substitute `%TEMP%\` (cmd) or `$env:TEMP\` (PowerShell)
- **Shell examples**: SKILL.md bash examples work in Git Bash or WSL; PowerShell equivalents are noted where applicable
- **Path resolution**: All Python scripts use `pathlib.Path` and are cross-platform
- **Installer**: `python tools/install.py` works on all platforms (the bash `install.sh` wrapper is macOS/Linux only)
- **Hook scripts**: Already handle `sys.platform == "win32"` for stdin reading
