# Optimization Pattern 2: Extract Deterministic Logic from Natural Language

## Detection Logic

Scan instructions blocks for three categories of logic that should be deterministic:

1. **Deterministic action calls**: Instructions saying "first do X", "do X before any action", "retrieve/get/call X" where actions should run unconditionally or based on a simple check.

2. **Variable conditionals**: Phrases like "If [variable] is [value], route/transition to [subagent]", "When [condition], set [variable]", "Don't [action] if..."

3. **Post-action logic**: Natural language describing what to do AFTER an action runs, like "If [action result]...", "After calling X, do Y..."

## How to Fix

Move procedural logic from natural language instructions to explicit deterministic code (`if`, `run`, `set`, `transition` constructs).

**Variable creation is often required**: When extracting deterministic logic, you frequently need to create new mutable variables to store action outputs. If the action has outputs and those are used in conditionals or passed to other actions, you MUST:
1. Create a new mutable variable with matching type if it doesn't exist
2. Add `set @variables.X = @outputs.Y` to store the output
3. Use `@variables.X` in the conditional or subsequent action

**Ordering**: Deterministic checks should happen BEFORE natural language instructions, not embedded within them.

## Example

**Before:**
```
variables:
    hotelCode: mutable string

subagent hotel_booking:
    reasoning:
        instructions: ->
            | If user is not known, always ask for their username and get their User record before making any booking. Help user check room availability with {!@actions.CheckAvailability}. If room is available, transition to payment.
        actions:
            IdentifyUserByUsername: @actions.identify_user_by_username
                with username = ...
            CheckAvailability: @actions.check_room_availability
                with roomType = ...
                with userRecord = ...
    actions:
        identify_user_by_username:
            description: "Get user tier"
            inputs:
                "username": string
            outputs:
                "userRecord": object
        check_room_availability:
            inputs:
                "roomType": string
                "userRecord": object
            outputs:
                "available": boolean
```

**After:**
```
variables:
    hotelCode: mutable string
    userRecord: mutable object
    roomAvailable: mutable boolean

subagent hotel_booking:
    reasoning:
        instructions: ->
            if @variables.userRecord is None:
                run @actions.identify_user_by_username
                    set @variables.userRecord = @outputs.userRecord
            | Help user check room availability with {!@actions.CheckAvailability}.
        actions:
            IdentifyUserByUsername: @actions.identify_user_by_username
                with username = ...
                set @variables.userRecord = @outputs.userRecord
            CheckAvailability: @actions.check_room_availability
                with roomType = ...
                with userRecord = @variables.userRecord
                set @variables.roomAvailable = @outputs.available
                if @variables.roomAvailable:
                    transition to @subagent.payment
    actions:
        identify_user_by_username:
            description: "Get user tier"
            inputs:
                "username": string
            outputs:
                "userRecord": object
        check_room_availability:
            inputs:
                "roomType": string
                "userRecord": object
            outputs:
                "available": boolean
```

**Key improvements:**
- Created new variables: `userRecord: mutable object` and `roomAvailable: mutable boolean`
- Extracted `run @actions.identify_user_by_username` with conditional guard from "before making any booking" natural language
- Stored action outputs in variables for downstream use
- Moved "if room is available, transition" to deterministic post-action logic
- Natural language instructions now only contain what the LLM needs to reason about (room availability conversation), not procedural control flow
