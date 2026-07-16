# Reference Map and Consolidation Plan

> Meta document: describes how to use and maintain the reference set.

This file defines which references are primary vs supplemental so the skill stays
organized without risky deletions.

## Primary References (Authoritative)

- `agent-script-core-language.md` — syntax and execution model
- `agent-design-and-spec-creation.md` — design/spec workflow
- `patterns-by-requirement.md` — scenario-to-pattern selection
- `architecture-patterns.md` — architecture mechanics and migration
- `posture-and-determinism.md` — subagent posture guidance
- `salesforce-cli-for-agents.md` — command reference
- `agent-validation-and-debugging.md` — runtime validation/debug flow
- `deploy-reference.md` — draft-vs-release deployment lifecycle

## Adjacent Operational References (Keep)

- `agent-metadata-and-lifecycle.md`
- `agent-user-setup.md`
- `agent-access-guide.md`
- `data-library-reference.md`
- `known-issues.md`
- `production-gotchas.md`

## Supplemental References (Review for Merge/Prune Later)

- `examples.md` — long-form walkthroughs
- `actions-reference.md` — broad action property reference
- `action-prompt-templates.md` — prompt-template-specific action guidance
- `feature-validity.md` — utility-vs-target property validity matrix

## Current Recommendation (No Deletions Yet)

1. Keep all files for now.
2. Treat supplemental references as second-level docs.
3. In a future cleanup pass, consider:
   - keep `examples.md` as the single examples reference and avoid re-splitting minimal examples
   - folding `feature-validity.md` into `actions-reference.md`
   - keeping `action-prompt-templates.md` only if prompt-template depth remains valuable
