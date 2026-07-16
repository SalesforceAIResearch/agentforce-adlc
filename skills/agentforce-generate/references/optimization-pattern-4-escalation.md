# Optimization Pattern 4: Add Proper Escalation Actions

## Detection Logic

**ONLY apply this pattern if escalation is explicitly mentioned in natural language instructions.** Look for specific phrases:

- "escalate to human"
- "transfer to live agent"
- "connect to support representative"
- "hand off to person"
- "escalate to agent"
- "contact human"

If NO escalation mention exists in instructions, skip this pattern entirely.

## How to Fix

1. Reference the escalation action using `{!@actions.go_to_escalation}` syntax in natural language instructions
2. Add the `go_to_escalation` action to `reasoning.actions` that transitions to the escalation subagent
3. The action should use `@utils.transition to @subagent.escalation` to properly route to escalation handling

## Example

**Before:**
```
subagent CustomerSupport:
    description: "Handles customer support requests"
    reasoning:
        instructions: ->
            | Help customers with their questions. If the request is too complex or the customer explicitly asks for a human, escalate to a live agent.
        actions:
            AnswerQuestion: @actions.AnswerQuestionWithKnowledge
                with query = ...
```

**After:**
```
subagent CustomerSupport:
    description: "Handles customer support requests"
    reasoning:
        instructions: ->
            | Help customers with their questions. If the request is too complex or the customer explicitly asks for a human, use {!@actions.go_to_escalation} to connect them with a live agent.
        actions:
            AnswerQuestion: @actions.AnswerQuestionWithKnowledge
                with query = ...
            go_to_escalation: @utils.transition to @subagent.escalation
                description: "Transition to the escalation subagent to handle the request."
```

**Key improvements:**
1. Referenced the escalation action using `{!@actions.go_to_escalation}` in natural language
2. Added `go_to_escalation` action to `reasoning.actions` with transition to escalation subagent
3. The action uses `@utils.transition to @subagent.escalation` for proper routing
