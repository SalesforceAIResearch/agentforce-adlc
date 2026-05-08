# Changelog

All notable changes to this plugin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- `README.md` and `CLAUDE.md` updated to reflect the new plugin slug (`agentforce-adlc`) in install commands, skill namespace examples (`/agentforce-adlc:developing-agentforce`, etc.), and project-structure references.
- `/developing-agentforce` now prompts the user during agent authoring (after Spec approval, before code generation) about whether to ground the agent on a document corpus. If yes, the skill provisions a SFDRIVE Agentforce Data Library via the Einstein Data Libraries REST API and writes the `knowledge:` block + `AnswerQuestionsWithKnowledge` action into the first authored `.agent`. Includes a Data Cloud preflight (`SELECT COUNT() FROM DataKnowledgeSpace` + `GET /einstein/data-libraries` health check) with an A/B branch when DC is not provisioned and a distinct "DC up, ADL service broken" path.
- Skill responsiveness improvements based on the test-agent16 session:
  - ADL readiness now keys on `retrieverId` populating, not the lagging top-level `indexingStatus.status` flag (which can stay `IN_PROGRESS` for 10–30 minutes after the retriever is live).
  - Data Cloud preflight rewritten: primary check is `SELECT COUNT() FROM DataKnowledgeSpace` (the actual ADL pipeline dependency, queryable as soon as DC provisioning completes — pattern adopted from codey-cko2's `setting-up-help-agent`). Secondary check is `GET /einstein/data-libraries` to validate ADL service health. Replaces the prior `DataStream__dlm` query, which produced false-negatives on healthy DC orgs (verified across arc6 / arc2 / arc7).
  - Knowledge-grounded subagent now ships with an anti-hallucination guard: when `knowledgeSummary` is empty, the agent must refuse rather than compose. Also documented in the Wiring section of the Data Library reference.
  - The publish-500 quick-reference is now a four-cause triage (agent-type mismatch, missing `outputs:`, structural drift via diff-against-working-bundle, transient backend) rather than a single-cause hint.
  - New Rule 5 ("Don't stall") in `Rules That Always Apply` codifies that the skill should announce and start the next step automatically rather than waiting for "what's next?" prompts.

### Added
- This `CHANGELOG.md`, plus a version-and-changelog workflow section in `CLAUDE.md`.
- `skills/developing-agentforce/references/data-library-reference.md` — full ADL provisioning flow (Steps 0–8) and Agent Script wiring guide (`knowledge:` block + `AnswerQuestionsWithKnowledge` action).
- `skills/developing-agentforce/assets/agents/knowledge-grounded.agent` — minimal copy-modify template demonstrating the wiring.
- `skills/developing-agentforce/assets/adl-api-spec.yaml` — ADL OpenAPI spec, used by the optional spec-validation appendix.

### Removed
- `skills/adl/` — folded into `/developing-agentforce`. Users who invoked the standalone skill should now use `/developing-agentforce` for end-to-end agent + ADL authoring.

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
