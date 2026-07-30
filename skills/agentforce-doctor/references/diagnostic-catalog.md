# AgentScript Diagnostic Catalog

Use this catalog after reconstructing the agent's use cases. A pattern is a
finding only when it has a source location, reachable consequence, affected
use case, minimal fix, and verification method.

## Contents

- [Language and structural validity](#language-and-structural-validity)
- [Instruction resolution](#instruction-resolution)
- [Prompt text that impersonates code](#prompt-text-that-impersonates-code)
- [Routing and reachability](#routing-and-reachability)
- [Action surface and contracts](#action-surface-and-contracts)
- [Outputs and trusted decisions](#outputs-and-trusted-decisions)
- [State and lifecycle](#state-and-lifecycle)
- [Turn sequencing](#turn-sequencing)
- [Transitions and message continuity](#transitions-and-message-continuity)
- [Authority and side effects](#authority-and-side-effects)
- [Architecture and prompt density](#architecture-and-prompt-density)
- [Use-case completeness](#use-case-completeness)
- [Capability honesty](#capability-honesty)
- [Evaluation integrity](#evaluation-integrity)
- [Non-findings](#non-findings)

## Language and structural validity

Check:

- unsupported blocks, hooks, utilities, conditional forms, or directives;
- malformed structural indentation or mixed indentation;
- missing required declarations in a complete bundle;
- references to undeclared variables, actions, subagents, or outputs;
- action targets or input/output schemas that disagree with implementations;
- syntax copied from a newer or different AgentScript dialect.

Evidence:

- Prefer parser, lint, compile, and implementation-contract output.
- Distinguish a complete bundle from an extracted fragment.

Fix:

- Use the smallest supported construct.
- Validate with the target runtime; do not patch around a parser failure with
  prompt wording.

Evaluate:

- Require zero relevant parse or compile errors.
- Re-run contract discovery when action definitions change.

## Instruction resolution

Check:

- a subagent `system.instructions` value unintentionally replaces global
  identity, safety, or scope instructions;
- global and local instructions demand incompatible outcomes;
- model-facing instructions mention runtime-only concepts the model cannot see;
- a conditional fragment assumes another fragment is present;
- repeated instructions conflict, dilute precedence, or exceed useful context.

Fix:

- Put durable invariants in the effective system instruction for every block
  that needs them.
- Remove duplicate or contradictory prose.
- Inject only the concrete values the model must read.

Evaluate:

- Inspect the effective prompt for each affected use case, not only the source
  file.
- Test one case per instruction override boundary.

## Prompt text that impersonates code

Check:

- indentation beneath `|` is treated as executable nesting;
- `Show`, `Ask`, `Call`, `Set`, `STOP`, or `Continue` is treated as a runtime
  directive;
- “Step 3” or “continue above” assumes prior prompt fragments survived;
- `MANDATORY` or `DO NOT SKIP` substitutes for gating or sequencing;
- an action visually placed under one prompt branch remains globally available.

Fix:

- Use real `if`, `else if`, `else`, `run`, `set`, `transition`, and
  `available when` constructs for machine-known behavior.
- Make every resolved prompt fragment understandable by itself.

Evaluate:

- Inspect both effective instructions and the available-action list for true
  and false versions of the branch condition.

## Routing and reachability

Check:

- independent conditions can resolve simultaneously;
- no condition handles a reachable state;
- precedence is stated in prose but not represented by predicates;
- a branch depends on an accidental default or a value with no producer;
- a route is unreachable because an earlier transition or reset always wins;
- a broad fallback steals a specific use case;
- routing descriptions disagree with reasoning instructions.

Fix:

- Use mutually exclusive predicates or a supported `if / else if / else`
  chain.
- Encode only machine-known precedence deterministically.
- Add a fallback only when the intended use cases require one.

Evaluate:

- Test each route positively and negatively.
- Test ambiguous boundary utterances against both neighboring routes.

## Action surface and contracts

Check:

- an action is referenced but undefined, or defined but unreachable;
- availability is broader than the use case;
- an action remains available after success and can repeat;
- descriptions overpromise capability or conflict with eligibility;
- required inputs have no conversation, variable, or literal producer;
- outputs are declared but not captured, or captured but never consumed;
- implementation inputs/outputs disagree with the `.agent` contract;
- a utility action is treated as though it returned action outputs.

Fix:

- Gate availability with trusted state.
- Return typed outputs and bind them to named consumers.
- Align the contract with the real implementation.
- Remove dead actions only after proving they serve no intended use case.

Evaluate:

- Check available, invoked, executed, and returned-output layers separately.
- Include negative cases where the action must be absent.

## Outputs and trusted decisions

Check:

- raw JSON or display text controls authorization, eligibility, routing, or
  success;
- the model is asked to parse a value that should be typed;
- a “checked” flag becomes true before every downstream value is stored;
- stale structured values survive a new raw result;
- the source output is not marked or shaped for planner use when required;
- the prompt assumes stored state is visible without explicit injection.

Fix:

- Prefer typed outputs.
- Normalize raw output deterministically before setting completion.
- Store related result fields atomically when possible.

Evaluate:

- Test true, false, malformed, missing, and stale-result cases.
- Confirm the branch reads the current result, not a default.

## State and lifecycle

Check:

- state merely remembers dialogue that already survives in history;
- `current_step`, `question_asked`, or similar variables imitate a workflow
  engine without deterministic consumers;
- completion means attempted or initiated rather than effected;
- request-scoped state leaks into a later request;
- reset, retry, correction, cancellation, logout, or expiry semantics are
  missing;
- `before_reasoning` unconditionally erases a legitimate prior-turn value;
- `after_reasoning` overwrites or advances state despite failure.

Fix:

- Remove unnecessary state.
- Name state after the evidence it represents.
- Give every mutable variable a producer, consumer, reset, and failure
  lifecycle.

Evaluate:

- Test the second request, retry, cancellation, and correction paths.
- Assert state transitions, not just response wording.

## Turn sequencing

Check:

- `@utils.setVariables` is followed by required same-turn work;
- one prompt asks a question and consumes the future answer immediately;
- several model-selected tools are required in an exact order;
- a turn-ending action is treated as a normal in-turn setter;
- post-action checks appear too late and competing first-entry instructions
  survive re-resolution.

Fix:

- Give each branch one next outcome.
- Bind current-turn inputs directly to the real action when persistence is not
  required.
- Use deterministic chaining or one atomic action when order protects
  correctness.

Evaluate:

- Run the actual multi-turn sequence and inspect each reasoning iteration.

## Transitions and message continuity

Check:

- the target subagent reprocesses the message that completed the source flow;
- transition state is incomplete for the target's arrival path;
- both source and target respond or perform the same work;
- a flow cannot return or exit when its supported use cases require it;
- a generic “stay” rule traps genuine topic switches.

Fix:

- Define one owner for the arrival turn.
- Pass explicit state only when the target needs it.
- Make continuation and exit predicates reflect real use cases, not exhaustive
  phrase lists.

Evaluate:

- Test entry, continuation, cancellation, pivot, and return paths as separate
  multi-turn cases.

## Authority and side effects

Check:

- a consequential action is gated by model-inferred or user-claimed authority;
- confirmation exists only in prose;
- two actions both appear to perform the same external effect;
- idempotency is absent for repeatable writes, transfers, messages, or charges;
- completion is set before a typed success result;
- simulated execution is treated as proof of a live effect.

Fix:

- Gate on trusted authorization and confirmation evidence.
- Choose one side-effect owner.
- Use idempotency keys or returned identifiers where supported.
- Claim only the strongest effect the runtime can verify.

Evaluate:

- Test unauthorized, unconfirmed, duplicate, failure, timeout, and retry cases.
- Verify the external record or system when live execution is authorized.

## Architecture and prompt density

Check:

- subagents exist without an objective, instruction, action, authority, or
  escalation boundary;
- routers duplicate behavior better handled in one execution block;
- state and transitions compensate for unclear instructions rather than real
  runtime needs;
- huge product lists, phrase lists, and repeated rules obscure higher-priority
  behavior;
- one subagent owns unrelated objectives or incompatible authority.

Fix:

- Start from the smallest architecture that satisfies the use cases.
- Remove a boundary only when its responsibilities and authority truly match.
- Prefer concise decision criteria over brittle phrase enumeration.

Evaluate:

- Compare routing and action behavior before and after simplification.
- Treat lower token count as supporting evidence, not proof of correctness.

## Use-case completeness

Check:

- only the happy path is defined;
- failure, retry, invalid input, repeated action, or cancellation is material
  but absent;
- a branch asks for information that no later branch consumes;
- an action result has no user-visible or machine-visible terminal outcome;
- a required capability has no reachable action or response path.

Fix:

- Add only the missing case required by the artifact or user intent.
- Keep each branch to one primary outcome.

Evaluate:

- Add a focused regression case for the missing path.
- Run it against both baseline and candidate.

## Capability honesty

Check:

- the agent promises a transfer, ticket, reset, refund, or follow-up without a
  supported implementation;
- a tool name implies a stronger effect than its contract returns;
- the response reports success after validation or initiation only;
- a fallback invents contact details, policies, or availability.

Fix:

- Match language to verified capability.
- Rename ambiguous actions or state when possible.
- Provide only configured, supported alternatives.

Evaluate:

- Compare the response claim with action output and external evidence.

## Evaluation integrity

Check:

- baseline and candidate use different cases, prompts, action modes, or
  evaluators;
- tests encode a newly preferred architecture or universal behavior;
- exact wording is graded when only the outcome matters;
- the candidate's tests were changed to match its implementation;
- multi-turn cases share sessions and contaminate one another;
- simulation is used for output-dependent behavior;
- only final responses are checked while wrong actions remain available;
- “parent” and “candidate” are not tied to exact revisions.

Fix:

- Freeze the use-case matrix and evaluator before editing.
- Separate regression requirements from proposed improvements.
- Identify both revisions and run the same cases.

Evaluate:

- Review the evaluation definition itself.
- Report changes to cases or metrics as changes to the contract, not as agent
  improvements.

## Non-findings

Do not report these without an affected use case and failure mechanism:

- subjective wording or formatting preferences;
- lack of a universal ambiguity, off-topic, or human-help branch;
- any particular number of subagents or variables;
- mutable state that has a valid deterministic consumer and lifecycle;
- an agentic decision that does not protect a machine-known invariant;
- response variation that preserves the required outcome;
- a compiler warning that is understood, bounded, and irrelevant to the
  intended runtime.
