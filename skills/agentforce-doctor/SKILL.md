---
name: agentforce-doctor
description: "Audit and repair existing Agentforce Agent Script agents by reconstructing intended use cases, finding syntax, instruction, routing, action, state, lifecycle, safety, and evaluation defects, applying minimal evidence-backed fixes, and comparing baseline and candidate behavior. Use for an agent doctor or health check, a comprehensive `.agent` review, a common-pitfall scan, 'what is wrong with this agent?', or an audit-fix-evaluate request. Do not use to create a new agent from scratch, make one already-specified edit, analyze production session IDs or traces, or only author or run a predefined test suite."
---

# Agentforce Doctor

Repair an existing AgentScript agent without replacing its intended behavior
with generic preferences.

## Operating Contract

1. **Use cases define correctness.** A checklist can reveal risk; it cannot
   decide what the agent should do. Reconstruct the agent's intended use cases
   before recommending or making behavioral changes.
2. **Diagnose before editing.** Record the baseline, exact evidence, affected
   use cases, and smallest credible fix first.
3. **Make findings actionable.** Every finding must include a source location,
   runtime consequence, affected use case, proposed change, and verification
   method. Omit unsupported style opinions.
4. **Prefer the smallest repair.** Do not redesign the agent, add subagents,
   add persistent state, or add universal ambiguity, off-topic, or human-help
   behavior unless the use cases require it.
5. **Use a real AgentScript implementation.** Validate with the target-org
   compiler, supported public SDK, or pinned open-source source build. Never
   claim language validity from a regex or a home-grown parser.
6. **Compare like with like.** Run the same use cases and evaluators against
   the unchanged baseline and candidate. Label them explicitly.
7. **Distinguish availability, invocation, execution, and effect.** A good
   response or tool name does not prove that an external side effect occurred.
8. **Do not release.** Doctoring authorizes local edits and proportionate
   validation, not deployment, publication, activation, production execution,
   or live consequential actions.

Read [Diagnostic Catalog](references/diagnostic-catalog.md) before auditing.
Read [Evaluation Loop](references/evaluation-loop.md) before recording the
baseline or running tests.

## Workflow

### 1. Establish Scope and Evidence

- Locate the complete `.agent` bundle, its metadata, action implementations,
  Agent Spec, test specifications, and relevant repository instructions.
- Determine whether the input is a complete agent, one extracted subagent, or
  a pasted fragment. Do not report missing bundle scaffolding as a defect in an
  intentionally extracted fragment.
- Inspect the worktree before editing. Preserve unrelated user changes.
- Identify available validation surfaces: project commands, AgentScript SDK,
  Salesforce CLI and target org, preview, test suites, and session traces.
- Read the full agent and every directly referenced action contract needed to
  understand its behavior. Do not infer action outputs from names alone.
- Run the strongest available read-only parser, lint, or compile check and
  preserve its baseline diagnostics.

If only a fragment is available, perform a bounded semantic review and state
which structural, reachability, and runtime claims cannot be verified.

#### Scale the audit before reading a large agent

For an agent over 2,000 lines or 10 execution nodes:

1. Build a deterministic index first: block boundaries, variables, actions,
   action outputs, transitions, lifecycle hooks, and parser diagnostics.
2. Keep one audit ledger keyed by execution node and use-case ID. Do not rely on
   a single giant narrative summary.
3. Review every node, then run one cross-node pass for shared variables,
   instruction overrides, transition arrivals, action ownership, and reset
   behavior.
4. Rank the complete finding set before editing.
5. Repair at most three related causes in one batch. Run parser checks, the
   affected regression cases, and representative unaffected canaries before
   starting the next batch.
6. Report deferred accepted findings after every batch. Do not hold the first
   useful result until the whole file has been rewritten.

Large size is not itself a defect. Do not split an agent merely to make the
doctor's analysis easier.

### 2. Reconstruct the Use Cases

Build a use-case matrix before fixing anything. Prefer, in order:

1. user-supplied behavior and acceptance criteria;
2. an approved Agent Spec;
3. existing tests and evaluation definitions;
4. reachable behavior inferred from the agent and action contracts.

Label inferred use cases. Do not quietly turn them into new requirements.

For each user-facing objective, record:

- initial utterance and required follow-up turns;
- expected response, question, action, transition, refusal, or escalation;
- actions that must be available and actions that must be unavailable;
- trusted prerequisites and expected state changes;
- external side effect, if any, and which mechanism owns it.

Include the relevant boundaries:

- positive path;
- missing or invalid input;
- failure and retry;
- cancellation or topic switch when the flow supports it;
- repeated request or repeated action;
- multi-turn continuation;
- transition arrival with the current customer message;
- explicit negative action-availability cases.

Do not mechanically add every boundary to every agent. A boundary belongs in
the matrix only when the artifact or user intent makes it material.

### 3. Audit Every Reachable Path

Trace each use case through:

```text
effective instructions
-> available actions
-> selected action or response
-> returned output
-> stored state
-> next reasoning iteration or transition
-> externally observable result
```

Apply every relevant category in the Diagnostic Catalog. Pay special attention
to:

- structural indentation versus indentation inside `|` text;
- subagent system instructions replacing global instructions;
- independent conditions that overlap or leave gaps;
- action availability that is broader than the prompt branch mentioning it;
- required work after `@utils.setVariables`;
- raw or stale outputs controlling consequential decisions;
- state that duplicates conversation history or lacks reset semantics;
- lifecycle hooks that overwrite legitimate later state;
- unsupported syntax or lifecycle constructs;
- two mechanisms claiming the same side effect;
- tests that encode a new preference instead of existing intent.

Rank findings by observable harm, not visual ugliness:

- **Critical:** unsafe or unauthorized effect, data exposure, or systemic
  inability to perform the primary objective.
- **High:** wrong routing, wrong action, duplicate effect, dead primary path,
  or trusted decision based on untrusted data.
- **Medium:** reachable failure, retry, continuation, or maintenance defect
  with bounded impact.
- **Low:** concrete clarity or resilience defect with a plausible failure mode.

No location, consequence, use case, and verification plan means no finding.

### 4. Capture the Baseline

- Run parser, lint, and compile checks before editing.
- Run the use-case matrix against the unchanged agent when a safe execution
  surface is available.
- Use a fresh session for each independent case. Keep one session only for the
  turns of a deliberate multi-turn case.
- Use simulated actions only for routing, instruction, and action-selection
  checks. Do not use simulation to claim that output-dependent branches or
  external effects work.
- Run live actions only with explicit user approval, a confirmed non-production
  environment, and safe test data.
- If runtime testing is unavailable, record a static baseline and state the
  limitation. Do not invent a score.

Preserve baseline results separately from candidate results.

### 5. Apply Minimal Repairs

Fix one coherent cause group at a time:

1. syntax, structural, and unsupported-language failures;
2. authorization, safety, and duplicate-side-effect failures;
3. dead, overlapping, or incorrectly gated paths;
4. output, state, lifecycle, and continuation failures;
5. unnecessary complexity that has a demonstrated failure mode.

For a large agent, take only the highest-ranked batch through evaluation before
continuing. A doctor run may produce several independently validated batches;
it must never construct one monolithic patch from the entire finding list.

For each group:

- change the narrowest runtime construct that owns the problem;
- use `available when`, typed outputs, deterministic assignments, or an atomic
  implementation when prose cannot enforce the invariant;
- remove state that has no named deterministic consumer;
- set completion only from the strongest result the runtime can prove;
- keep logic changes separate from broad formatting cleanup;
- preserve unrelated behavior and wording.

If the user requested diagnosis only, stop before editing and provide the
repair and evaluation plan.

### 6. Evaluate and Iterate

After each coherent repair group:

1. rerun parser, lint, and compile checks;
2. replay the same baseline use cases with the same evaluator;
3. run the new regression case that exposes the repaired defect;
4. inspect effective instructions, action availability, invocation, outputs,
   state changes, transitions, and effects—not only final response text;
5. compare baseline and candidate for every unaffected case;
6. keep the change only when the target case improves and unrelated cases are
   no worse.

If a candidate regresses, narrow or revert that repair and repeat. Do not
change the evaluator to make the candidate pass.

### 7. Report the Result

Return:

1. **Health summary:** what is broken, risky, or sound.
2. **Use-case matrix:** explicit versus inferred cases and their expected
   outcomes.
3. **Findings:** severity, location, evidence, affected cases, and disposition.
4. **Changes:** the minimal repair made for each accepted finding.
5. **Baseline versus candidate:** same cases, same evaluator, exact results.
6. **Validation:** parser/compiler, preview/test mode, action mode, and limits.
7. **Remaining risks:** only evidence-backed unresolved items.

State “no actionable finding” when that is the evidence. A doctor is not
required to prescribe a change.
