# Common AgentScript Control-Flow Pitfalls

Use this checklist when authoring, reviewing, debugging, or optimizing an
AgentScript workflow. It focuses on mistakes that look reasonable in the source
but do not mean what their formatting suggests.

## Contents

- [The simple mental model](#the-simple-mental-model)
- [Prompt text that looks like code](#prompt-text-that-looks-like-code)
- [Step labels without runtime state](#step-labels-without-runtime-state)
- [Actions that escape their intended branch](#actions-that-escape-their-intended-branch)
- [Impossible same-turn sequences](#impossible-same-turn-sequences)
- [State written too early](#state-written-too-early)
- [Stale, raw, or missing action results](#stale-raw-or-missing-action-results)
- [Lifecycle code that overwrites later work](#lifecycle-code-that-overwrites-later-work)
- [Competing owners for one side effect](#competing-owners-for-one-side-effect)
- [Review checklist](#review-checklist)

## The simple mental model

AgentScript has three different execution surfaces:

1. Deterministic constructs such as `if`, `run`, `set`, `transition to`, and
   lifecycle hooks execute in the runtime.
2. Text introduced by `|` becomes instructions for the model.
3. Actions under `reasoning.actions` become tools the model may choose.

Do not rely on indentation, numbering, or imperative words inside prompt text
to behave like runtime control flow.

## Prompt text that looks like code

### Pitfall: indented prompt text appears scoped

```agentscript
if @variables.lookup_failed == True:
    | Failure path:
        Call {!@actions.create_ticket}.
```

The indentation after `|` formats model-visible prose. It does not place
`create_ticket` inside the deterministic `if`.

Fix:

- Use the `if` to select the prompt text.
- Use `available when` to select the action schema.

```agentscript
reasoning:
    instructions: ->
        if @variables.lookup_failed == True:
            | Explain that the lookup failed. If the customer asks to create a
              ticket, use the ticket action.
    actions:
        create_ticket: @actions.create_ticket
            available when @variables.lookup_failed == True
```

### Pitfall: prompt verbs are mistaken for commands

Inside a pipe block, these are ordinary words:

```text
Show | Ask | Call | Set | Stop | Continue | Go to
```

They may guide the model, but they do not:

- send a response deterministically;
- mutate a variable;
- execute an action;
- stop runtime resolution; or
- transition to another subagent.

Use runtime `set` and `transition to` for deterministic state-based behavior.
Expose an action when the model should judge whether to act.

### Pitfall: stronger wording is used as enforcement

Repeating `MANDATORY`, `DO NOT SKIP`, or `IMMEDIATELY` does not create a runtime
guarantee. If ordering or eligibility matters, represent it with machine-known
state, action inputs, `available when`, deterministic action chaining, or one
atomic implementation.

## Step labels without runtime state

### Pitfall: step numbers are treated as a workflow engine

```agentscript
if @variables.ready == True:
    | Step 4 — Submit the request.
```

The model may see “Step 4” without Steps 1–3. AgentScript includes only the
prompt branches that resolve true during the current reasoning iteration.
Numbering does not prove that earlier work happened.

Fix:

- Remove step numbers when they are only explanatory labels.
- If earlier work is a real prerequisite, gate the later action on trusted
  output from that work.

```agentscript
submit: @actions.submit_request
    available when @variables.validation_succeeded == True
```

### Pitfall: a prompt depends on missing context

Every resolved prompt fragment must make sense by itself. Avoid instructions
such as “continue to the next step,” “use the result above,” or “as described
earlier” when the referenced fragment may not survive conditional resolution.

Name the actual objective and relevant state in the branch:

```agentscript
if @variables.validation_succeeded == True:
    | Validation succeeded. Submit the verified request.
```

### Pitfall: stored state is assumed to be model-visible

Storing an action output in `@variables` makes it available to runtime
conditions and later bindings. It does not automatically insert the value into
model-facing instructions. When the model must read a stored value, inject it
explicitly:

```agentscript
if @variables.lookup_result != "":
    | Use this lookup result: {!@variables.lookup_result}
```

Prefer typed outputs and deterministic conditions when the value controls
authorization, eligibility, routing, or another consequential decision.

## Actions that escape their intended branch

### Pitfall: mentioning an action under one branch is assumed to scope it

Actions are defined for the reasoning scope, not nested under the visual prompt
paragraph that mentions them. Unless gated, an action remains available while
other branches are active.

```agentscript
reasoning:
    instructions: ->
        if @variables.validation_succeeded == True:
            | Use the {!@actions.submit} action.
    actions:
        submit: @actions.submit_request
```

The `submit` action is still available when `validation_succeeded` is false.

Fix:

```agentscript
submit: @actions.submit_request
    available when @variables.validation_succeeded == True
```

### Pitfall: an action remains available after it succeeds

If repeating an action would duplicate a write, charge, message, or external
commitment, gate it on a result or idempotency value.

```agentscript
submit: @actions.submit_request
    available when @variables.validation_succeeded == True
    available when @variables.submission_id == ""
    set @variables.submission_id = @outputs.submission_id
```

Do not depend only on prose such as “do not call this again.”

## Impossible same-turn sequences

### Pitfall: `setVariables` is followed by required work

`@utils.setVariables` ends the turn after it captures values. This sequence is
not a reliable same-turn workflow:

```text
Call the state-setting action.
Then call the submission action.
```

The second action does not automatically follow.

Fix with the smallest suitable option:

- bind current-turn values directly to the real action with `...`;
- set trusted values deterministically before reasoning;
- pass fixed values through a purpose-built transition or action;
- return the required values from the first real action; or
- combine inseparable writes into one atomic implementation.

### Pitfall: ask now and capture the future answer now

```text
Ask for the issue description.
Call the capture action with the issue description.
```

The answer does not exist when the question is asked. Give that branch one
outcome: ask. On the later turn, capture or use the answer.

### Pitfall: one branch requires several model-selected tools in order

The model may choose one tool, choose them in a different order, or stop after a
turn-ending tool. If the order protects authorization, correctness, or an
external side effect, do not encode it only as a tool list in prompt text.

Use deterministic post-action logic, gated actions with explicit intermediate
results, or one atomic action.

## State written too early

### Pitfall: “complete” means “started”

Do not set:

```agentscript
set @variables.operation_completed = True
```

before the consequential action has returned a successful result.

Prefer state names that match the evidence:

```text
validation_completed
operation_requested
operation_succeeded
```

If the runtime cannot observe the final external side effect, use a weaker name
such as `operation_initiated` instead of claiming completion.

### Pitfall: workflow state advances on failure

Do not advance a stage, close a gate, or hide retry behavior merely because an
action was attempted. Branch on the trusted action result and preserve a safe
retry or failure path.

### Pitfall: state exists only to imitate dialogue stages

Avoid `current_step`, `question_asked`, or `has_greeted` when conversation
history already supplies continuity. Add state only for a named deterministic
consumer with a complete reset, correction, and failure lifecycle.

## Stale, raw, or missing action results

### Pitfall: “checked” is set before the result is usable

Do not mark validation complete while its result still needs model-driven
parsing:

```agentscript
set @variables.validation_output = @outputs.raw_json
set @variables.validation_checked = True
```

Later conditions can read old/default structured values and choose the wrong
branch.

Fix:

- Prefer typed action outputs.
- Otherwise normalize the raw result deterministically.
- Mark the check complete only after all branch inputs are stored.

### Pitfall: raw JSON controls important branches

Do not ask the model to extract authorization, eligibility, confirmation, or
success flags from display-oriented text when those flags determine tool
availability or a consequential transition. Return typed, machine-checkable
outputs.

### Pitfall: the script branches on a value no producer returns

For every condition and `available when`, trace the value backward:

```text
consumer -> stored variable -> action output or deterministic assignment
```

If no reachable producer exists, the branch is dead or depends on an accidental
default.

### Pitfall: independent top-level conditions overlap

Sequential top-level `if` blocks are evaluated independently. If only one
branch should survive, make their predicates mutually exclusive or use a
supported `if / else if / else` chain.

## Lifecycle code that overwrites later work

### Pitfall: `before_reasoning` resets a value every turn

`before_reasoning` runs once per turn. An unconditional assignment there can
erase a value captured or inferred during the previous turn.

Review every lifecycle assignment by asking:

- Is this an initialization or an unconditional reset?
- Can a later branch legitimately change it?
- When and where is it cleared?

Initialize only when the value is unset, or let the destination subagent own its
own intent.

### Pitfall: a transition reprocesses the same customer message

A transition can start the target subagent during the same customer turn. The
target may receive the message that completed the prior gate, not a fresh
request. Make the target coherent for that arrival path or transition only when
the target has enough explicit state to act safely.

## Competing owners for one side effect

### Pitfall: two mechanisms both appear to perform the same operation

Examples:

- one action is named “validate and submit,” followed by another submit action;
- an external action performs transfer, followed by a utility escalation;
- a transition and a delegated subagent both own completion.

Choose one owner for each external side effect. Document whether other actions
prepare, validate, invoke, or verify it.

### Pitfall: model text is treated as proof

A promise, confirmation, or tool name in the model response is not evidence
that an external action occurred. Verify separately:

```text
configured -> available -> invoked -> executed -> effected
```

Advance consequential state only at the strongest layer the runtime can prove.

## Review checklist

For every reasoning branch:

- [ ] Does the resolved prompt make sense without hidden earlier “steps”?
- [ ] Is every stored value the model must read explicitly injected?
- [ ] Does the branch have one next outcome?
- [ ] Are `Show`, `Ask`, `Call`, `Set`, and `STOP` being used only as prose?
- [ ] Are material actions gated independently of the prompt paragraph?
- [ ] Can any action remain available after success and repeat?
- [ ] Does a `setVariables` call incorrectly precede required same-turn work?
- [ ] Does the branch ask for and consume the same future answer?
- [ ] Are ordered tool calls enforced by the runtime when order matters?
- [ ] Is every completion flag backed by a successful result?
- [ ] Is every condition value produced on every reachable path?
- [ ] Are typed outputs used for machine-controlled decisions?
- [ ] Can independent conditions resolve simultaneously?
- [ ] Can lifecycle logic overwrite a legitimate later value?
- [ ] Does exactly one mechanism own each external side effect?
- [ ] Do tests inspect action availability and external results, not only final
      model text?
