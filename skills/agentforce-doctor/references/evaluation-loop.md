# AgentScript Doctor Evaluation Loop

Use this reference to prove that a repair improves the intended use cases
without teaching the evaluation to prefer the candidate.

## Contents

- [Define the contract](#define-the-contract)
- [Build the use-case matrix](#build-the-use-case-matrix)
- [Identify baseline and candidate](#identify-baseline-and-candidate)
- [Choose the validation surface](#choose-the-validation-surface)
- [Capture the baseline](#capture-the-baseline)
- [Evaluate the candidate](#evaluate-the-candidate)
- [Judge results](#judge-results)
- [Iterate safely](#iterate-safely)
- [Report limitations](#report-limitations)

## Define the contract

Separate three kinds of expectations:

1. **Existing requirements:** explicitly supplied by the user, Agent Spec, or
   approved tests.
2. **Recovered behavior:** inferred from reachable agent and action behavior.
3. **Proposed improvements:** new behavior that may be desirable but is not yet
   part of the contract.

Regression evaluation may enforce the first category. It may use the second
category to preserve compatibility, but must label uncertainty. It must not
silently encode the third category.

When a proposed fix materially changes policy, scope, authority, or customer
outcomes, obtain user approval before making that expectation part of the
evaluation.

## Build the use-case matrix

Use this shape:

| ID | Source | Turns | Expected outcome | Must be available | Must be unavailable | State/effect |
|---|---|---|---|---|---|---|
| UC-01 | Agent Spec | one | answer supported question | knowledge action | write action | no write |
| UC-02 | action contract | multi | collect ID, then look up | lookup after ID | lookup before ID | result stored |
| UC-03 | inferred | one | explain validation failure | retry | submit | no submission |

For each consequential action, include:

- a positive eligibility case;
- a negative eligibility case;
- a repeated or replayed request;
- a returned failure or missing-output case;
- a success case whose external result can be verified when live testing is
  authorized.

For each transition, include:

- the entry utterance;
- the message that completes the source flow;
- the target's same-turn arrival behavior;
- a supported continuation and exit case.

Do not create a generic “off-topic,” “ambiguity,” or “human help” case unless
the agent's intended scope makes it a real requirement.

## Identify baseline and candidate

Tie labels to exact artifacts:

```text
baseline = unchanged file content or exact parent commit
candidate = proposed file content or exact candidate commit
```

Do not use “parent” to mean upstream `main` unless it is actually the candidate
commit's parent. Do not use “candidate” for a worktree whose uncommitted state
was not captured.

Before editing:

- record `git status`;
- record the relevant commit IDs;
- preserve the exact baseline file or run it from a clean worktree;
- freeze the use-case matrix, evaluator, CLI mode, model/runtime, and test data.

If the baseline cannot run because it does not parse, record the parser failure
as its baseline result. Do not fabricate behavioral scores.

## Choose the validation surface

Use the strongest applicable layer.

### 1. Target-org validation

Use the deployment runtime as release truth when an org is available:

```bash
sf agent validate authoring-bundle --json --api-name <BundleName>
```

This checks syntax and structure, not customer behavior.

### 2. Supported public SDK or pinned source

Use an existing repository command backed by the public AgentScript SDK. If the
published package is unavailable or older than the repository's declared
minimum, use the repository's pinned open-source source-build command.

In this repository:

```bash
node tests/validate_agent_assets_from_source.mjs \
  skills/agentforce-generate/assets
```

Do not substitute a Python or regex approximation for the AgentScript parser.

### 3. Local preview

Use programmatic preview, never the interactive REPL:

```bash
sf agent preview start --json \
  --authoring-bundle <BundleName> \
  --simulate-actions

sf agent preview send --json \
  --authoring-bundle <BundleName> \
  --session-id <SessionId> \
  --utterance "<message>"

sf agent preview end --json \
  --authoring-bundle <BundleName> \
  --session-id <SessionId>
```

Use `--simulate-actions` for routing and model-behavior checks only. Use
`--use-live-actions` on `preview start` only when the user explicitly approves
it, the org is confirmed non-production, and the case needs real outputs.

### 4. Testing Center

Use an existing Testing Center suite when it represents the frozen use-case
contract. Creating or changing a suite changes the evaluation contract and
must be reviewed separately from the candidate fix.

### 5. Static path evaluation

When runtime execution is unavailable, inspect:

- resolved instruction branches;
- action availability predicates;
- typed output producers and consumers;
- state transitions and reset paths;
- transition targets and side-effect owners.

Report this as static evidence, not a behavioral pass.

## Capture the baseline

For every case, record:

```text
case ID
revision
parser/compiler result
effective instruction fragments
available actions
invoked actions
returned outputs
state changes
transition path
response outcome
external effect
limitations
```

Use a fresh session per independent case. For one multi-turn case, keep one
session only for that case's turns. Never feed expected assistant responses
back into the live agent as conversation history.

Do not overwrite baseline output files with candidate output files.

## Evaluate the candidate

Run, in order:

1. parser, lint, and compile checks;
2. the exact frozen baseline cases;
3. the focused regression case for each accepted finding;
4. negative action-availability cases;
5. live effect verification only when authorized and required.

New regression cases must also run against the baseline. A useful regression
case demonstrates that the defect existed before the fix.

Keep settings equal:

- same use-case text and turn boundaries;
- same runtime and model where controllable;
- same target org and test data;
- same simulated or live action mode;
- same evaluator and thresholds;
- same session-isolation policy.

## Judge results

Prefer observable outcome checks:

- correct route or transition;
- required action available;
- forbidden action unavailable;
- correct action invoked no more than intended;
- typed result consumed;
- expected state change occurred;
- external effect occurred exactly once;
- response makes no stronger claim than the evidence.

Use semantic response grading only where the use case is genuinely about
language. Avoid exact-string grading unless exact wording is a stated product
requirement.

A candidate passes when:

- the target regression improves;
- all required structural checks pass;
- no unaffected frozen case regresses;
- no new consequential action becomes available incorrectly;
- claims about live effects are backed by live evidence.

Lower prompt size, fewer variables, or fewer subagents can support a result,
but they are not pass criteria by themselves.

## Iterate safely

When a candidate fails:

1. identify the smallest repair group responsible;
2. narrow or revert that group;
3. keep the evaluator frozen;
4. rerun structural checks;
5. rerun the affected case and all previously passing regression cases.

Do not:

- weaken an expected outcome after seeing the candidate fail;
- delete a failing case without showing it was outside the contract;
- change from live to simulated actions to obtain a pass;
- combine unrelated cleanup with a behavioral repair;
- declare improvement from aggregate score while a critical case regresses.

Stop and report a blocker when evaluation requires unavailable org access,
missing action implementations, production-only side effects, or a material
product-policy decision.

For a large agent, use bounded repair batches:

```text
complete audit
-> ranked finding backlog
-> batch of at most three related causes
-> full parser/compiler check
-> affected regression cases
-> unaffected canary cases
-> keep, narrow, or revert
-> next batch
-> final frozen-matrix regression
```

Do not keep a large candidate unvalidated while accumulating fixes. Do not
rescan the entire source manually after each batch: rerun whole-file mechanical
checks, inspect changed paths and shared consumers, and reserve the full
semantic matrix for the final candidate.

## Report limitations

State explicitly:

- which artifact revisions were compared;
- which cases were explicit versus inferred;
- which parser or compiler ran;
- which cases used simulation or live actions;
- whether external effects were independently verified;
- which branches could not be executed;
- whether the runtime, model, test data, or evaluator differed.

Use “not evaluated” instead of “passed” when evidence is unavailable.
