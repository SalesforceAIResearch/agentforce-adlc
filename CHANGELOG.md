# Changelog

All notable changes to this plugin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `/testing-agentforce` Mode B is now NGT (Next-Gen Testing) authoring via `sf agent test create --test-runner agentforce-studio`. Single-mode cutover — the skill no longer authors legacy `AiEvaluationDefinition` specs. Includes the v1 scorer catalog (11 entries), validator-error remediation table, and the canonical `sf agent test list` org-capability probe. Round-trip golden fixture lands in the same PR.
- `skills/testing-agentforce/assets/ngt-test-spec.yaml` — canonical NGT YAML fixture, byte-for-byte from the `salesforcecli/plugin-agent` PR #430 reference.
- `skills/testing-agentforce/references/legacy-testing-center.md` — archaeology doc with deprecation banner for users maintaining pre-existing `aiEvaluationDefinitions/` suites.

### Changed
- `skills/testing-agentforce/SKILL.md` — single-mode Mode B (NGT only). TRIGGER block, decision table, file-name convention (`<AgentApiName>-ngt.yaml`), and exit-code table updated to match `plugin-agent`'s structured codes (1 = NGT validator, 2 = ENOENT, 3 = infra, 4 = deploy). Bumped to `0.7.0`.
- `skills/testing-agentforce/references/batch-testing.md` — rewritten in place to cover NGT authoring. The legacy `AiEvaluationDefinition` schema content moved to `legacy-testing-center.md`. Includes an "Authoring guardrail tests" subsection with the `bot_response_rating` pattern.
- `skills/testing-agentforce/references/troubleshooting.md` — added an "NGT-specific issues" section covering the `INVALID_TYPE` capability-probe failure mode, `AmbiguousTestDefinition`, the legacy-default footgun, and the multi-agent handoff validator error.
- `skills/testing-agentforce/assets/guardrail-test-spec.yaml` — rewritten in NGT shape. Now an 8-probe template using `bot_response_rating` (off-topic, verification bypass, prompt injection, unsolicited PII, regulated-advice solicitation, escalation, multi-turn jailbreak).

### Removed
- `skills/testing-agentforce/assets/basic-test-spec.yaml` and `standard-test-spec.yaml` — legacy `AiEvaluationDefinition` authoring templates. Mode B is NGT-only as of v0.7.0; pin `agentforce-adlc@0.6.x` for legacy authoring.

### Migration
**`/testing-agentforce` Mode B authoring:** if the target org has `aFStudioTestingCenter` enabled, the skill now authors NGT YAML by default. Run the canonical probe (`sf agent test list --target-org <alias> --json`) to confirm; on a non-NGT org the probe returns `INVALID_TYPE: Cannot use: AiEvaluationDefinition in this organization` (definitive negative).

**Maintaining pre-existing `aiEvaluationDefinitions/` suites:** pin `agentforce-adlc@0.6.x` for the older skill that authors legacy specs. The schema is documented in `references/legacy-testing-center.md`. Plan a migration to NGT — manual rewrite, not an automatic conversion (`expectedTopic` ≈ `topic_sequence_match`, `expectedActions` ≈ `action_sequence_match`, `expectedOutcome` LLM-judge ≈ `bot_response_rating`).

**No-NGT-org workaround:** pin `0.6.x` until the target org has the testing-center capability enabled. To get an Agentforce-enabled org: sign up for a [free Agentforce Developer Edition][de-signup], or have your Salesforce admin enable testing-center on an existing sandbox (see the [Agentforce DX setup guide][dx-setup]). NGT is sandbox/scratch-only as of `@salesforce/agents@1.7.0`; production org rollout is server-side.

**Plugin-agent dependency:** the `--test-runner agentforce-studio` flag on `sf agent test create` requires `@salesforce/plugin-agent` ≥ 1.41.0. If your installed version is older, run `sf plugins install @salesforce/plugin-agent@1.41.0` (or newer).

## [0.6.1] — 2026-05-19

### Changed
- `README.md` and `CLAUDE.md` updated to reflect the new plugin slug (`agentforce-adlc`) in install commands, skill namespace examples (`/agentforce-adlc:developing-agentforce`, etc.), and project-structure references.
- `/developing-agentforce` now prompts the user during agent authoring (after Spec approval, before code generation) about whether to ground the agent on a document corpus. If yes, the skill provisions a SFDRIVE Agentforce Data Library via the Einstein Data Libraries REST API and writes the `knowledge:` block + `AnswerQuestionsWithKnowledge` action into the first authored `.agent`. Includes a Data Cloud preflight (`SELECT COUNT() FROM DataKnowledgeSpace` + `GET /einstein/data-libraries` health check) with an A/B branch when DC is not provisioned and a distinct "DC up, ADL service broken" path.
- Skill responsiveness improvements based on the test-agent16 session:
  - ADL readiness now keys on `retrieverId` populating, not the lagging top-level `indexingStatus.status` flag (which can stay `IN_PROGRESS` for 10–30 minutes after the retriever is live).
  - Data Cloud preflight rewritten: primary check is `SELECT COUNT() FROM DataKnowledgeSpace` (the actual ADL pipeline dependency, queryable as soon as DC provisioning completes — pattern adopted from codey-cko2's `setting-up-help-agent`). Secondary check is `GET /einstein/data-libraries` to validate ADL service health. Replaces the prior `DataStream__dlm` query, which produced false-negatives on healthy DC orgs (verified across arc6 / arc2 / arc7).
  - Knowledge-grounded subagent now ships with an anti-hallucination guard: when `knowledgeSummary` is empty, the agent must refuse rather than compose. Also documented in the Wiring section of the Data Library reference.
  - The publish-500 quick-reference is now a four-cause triage (agent-type mismatch, missing `outputs:`, structural drift via diff-against-working-bundle, transient backend) rather than a single-cause hint.
  - New Rule 5 ("Don't stall") in `Rules That Always Apply` codifies that the skill should announce and start the next step automatically rather than waiting for "what's next?" prompts.
- Skill responsiveness improvements based on the test-agent17 session:
  - **ADL provisioning kicks off earlier.** The grounding question (and file-path capture) now lives inside the Design step (Step 1) of the "Create an Agent" workflow, so it gets surfaced during requirements gathering rather than post-Spec-approval. Provisioning starts in Step 3 (environment validation) and runs in the background through bundle generation, code authoring, and validation. By Step 8 (Validate behavior), `retrieverId` has typically populated. Same shape applied to "Modify an Existing Agent" (grounding question moves into Step 2 Update Agent Spec; provisioning kickoff into Step 4).
  - **Pre-publish permset audit added to Step 8 CHECKPOINT.** When the agent has a `knowledge:` block, the skill now verifies the Einstein Agent User has a Data Cloud permset/PSL assigned (one of `GenieDataPlatformStarterPsl` PSL, `GenieUserEnhancedSecurity` PS, `DataCloudUser` PS, or `DataCloudArchitect` PS) before allowing Publish. Without this, `AnswerQuestionsWithKnowledge` returns empty `knowledgeSummary` at runtime and the anti-hallucination guard refuses every utterance — caught by the user in test-agent17 instead of by the skill.
  - **New Step 3b in `agent-user-setup.md`** — discovery-then-assign procedure for the Data Cloud permset, with PSL and PS branches, post-assignment verification queries, and a Data Space scope manual fallback (UI-only — no API exists). The permset name is **not** hardcoded; the skill discovers which name exists in the org. Pattern informed by codey-cko2's `assigning-permission-sets` skill.
  - `data-library-reference.md` now documents the permission prerequisite in the Wiring section, and the "Common pitfalls" list calls out the empty-`knowledgeSummary` symptom for ADL-permission failures.
- `skills/developing-agentforce/assets/` reorganized ([#15](https://github.com/SalesforceAIResearch/agentforce-adlc/pull/15)) — relocated four templates that ARE referenced from `SKILL.md` / `agents/adlc-author.md` into `assets/agents/` so all complete-agent templates live in one place: `template-single-subagent.agent`, `template-multi-subagent.agent`, `local-info-agent-annotated.agent`, `hub-and-spoke.agent`. Updated `SKILL.md`, both READMEs, and `agents/adlc-author.md` to match; fixed a pre-existing stale `multi-topic.agent` reference (actual file is `multi-subagent.agent`). End-state top level is 4 starter files (`adl-api-spec.yaml`, `agent-spec-template.md`, `bundle-meta.xml`, `invocable-apex-template.cls`) plus `agents/` and `patterns/`.

### Added
- This `CHANGELOG.md`, plus a version-and-changelog workflow section in `CLAUDE.md`.
- `skills/developing-agentforce/references/data-library-reference.md` — full ADL provisioning flow (Steps 0–8) and Agent Script wiring guide (`knowledge:` block + `AnswerQuestionsWithKnowledge` action).
- `skills/developing-agentforce/assets/agents/knowledge-grounded.agent` — minimal copy-modify template demonstrating the wiring.
- `skills/developing-agentforce/assets/adl-api-spec.yaml` — ADL OpenAPI spec, used by the optional spec-validation appendix.

### Removed
- `skills/adl/` — folded into `/developing-agentforce`. Users who invoked the standalone skill should now use `/developing-agentforce` for end-to-end agent + ADL authoring.
- `skills/developing-agentforce/assets/` v1 debt ([#15](https://github.com/SalesforceAIResearch/agentforce-adlc/pull/15)) — pruned 9 orphan files and 3 unused subdirectories (`apex/`, `components/`, `metadata/`) left over from the v1→v2 transition. None had live references in `SKILL.md`, reference docs, scripts, or hooks. Removed: `README-legacy.md`, `deterministic-routing.agent`, `escalation-pattern.agent`, `flow-action-lookup.agent`, `minimal-starter.agent`, `prompt-rag-search.agent`, and an older 208-line duplicate of `verification-gate.agent` (the canonical 280-line copy lives under `assets/agents/`).

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

[Unreleased]: https://github.com/SalesforceAIResearch/agentforce-adlc/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/SalesforceAIResearch/agentforce-adlc/releases/tag/v0.6.1
[0.6.0]: https://github.com/SalesforceAIResearch/agentforce-adlc/releases/tag/v0.6.0
[0.5.0]: https://github.com/SalesforceAIResearch/agentforce-adlc/releases/tag/v0.5.0
[de-signup]: https://www.salesforce.com/form/developer-signup/?d=pb
[dx-setup]: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-dx-set-up-env.html
