# Changelog

All notable changes to this plugin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- `guardrails.py` and `agent-validator.py` hooks now exit immediately when the working directory is not a Salesforce project (no `sfdx-project.json`, `force-app/`, or `aiAuthoringBundles/` in cwd or any ancestor). When the plugin is installed globally, hooks no longer observe Bash commands or file edits in unrelated projects. Behavior inside Salesforce projects is unchanged.
- `README.md` and `CLAUDE.md` updated to reflect the new plugin slug (`agentforce-adlc`) in install commands, skill namespace examples (`/agentforce-adlc:developing-agentforce`, etc.), and project-structure references.

### Added
- This `CHANGELOG.md`, plus a version-and-changelog workflow section in `CLAUDE.md`.

## [0.6.0] — 2026-05-01

### Changed
- **BREAKING** — Plugin slug renamed from `adlc` to `agentforce-adlc` in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` ([#9](https://github.com/SalesforceAIResearch/agentforce-adlc/pull/9)).

### Migration
Existing users must uninstall the old plugin and install under the new slug:
```bash
claude plugin uninstall adlc@agentforce-adlc
claude plugin install agentforce-adlc@agentforce-adlc
```
Skill invocations change from `/adlc:<skill>` to `/agentforce-adlc:<skill>`.

## [0.5.0] — Initial release

### Added
- Three consolidated skills: `developing-agentforce`, `testing-agentforce`, `observing-agentforce`.
- Four agents: `adlc-orchestrator`, `adlc-author`, `adlc-engineer`, `adlc-qa`.
- PreToolUse / PostToolUse hooks: `guardrails.py`, `agent-validator.py`.
- Discover / scaffold / deploy Python helpers under `scripts/`.
- File-copy installer (`tools/install.py`) for Cursor and legacy Claude Code.
- pytest test suite under `tests/`.

[Unreleased]: https://github.com/SalesforceAIResearch/agentforce-adlc/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/SalesforceAIResearch/agentforce-adlc/releases/tag/v0.6.0
[0.5.0]: https://github.com/SalesforceAIResearch/agentforce-adlc/releases/tag/v0.5.0
