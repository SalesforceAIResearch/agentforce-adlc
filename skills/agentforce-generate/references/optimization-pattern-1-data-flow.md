# Optimization Pattern 1: Wire Action Outputs to Consuming Actions

## Detection Logic

Scan systematically across ALL subagents:

1. **Identify data producers**: Scan all actions in the `actions:` section. Any action with `outputs:` defined is a data producer. Note the output parameter names and types.

2. **Identify data consumers**: Scan all `reasoning.actions` for ANY action invocation with inputs using `...` placeholder. These are data consumers waiting for real data.

3. **Match producers to consumers**: For EACH `...` placeholder, check what input parameter name and type the consuming action expects. Then find if ANY other action in the same subagent produces an output with matching name/type.

## How to Fix

**MANDATORY 3-Step Process** — if a producer-consumer match is found, ALL THREE steps must be completed:

### Step A — Variable Creation (MANDATORY)

Check if a mutable variable with the matching name and type exists in the `variables:` section. **If it does NOT exist, you MUST add it.** Most of the time, the variable does NOT already exist — always check and create if needed.

### Step B — Store Output (MANDATORY)

Add `set @variables.X = @outputs.Y` statement AFTER the producing action in `reasoning.actions`.

### Step C — Use Variable (MANDATORY)

Replace the `...` placeholder with `@variables.X` in the consuming action.

## Example

**Before:**
```
variables:
    customerId: string
    orderNumber: mutable string
    newStatus: mutable string

subagent OrderManagement:
    reasoning:
        instructions: ->
            | When updating an order status, first retrieve the order details, confirm the new status, then update it.
        actions:
            GetOrderDetails: @actions.GetOrderByNumber
                with customerId = @variables.customerId
                with orderNumber = @variables.orderNumber
            UpdateStatus: @actions.UpdateOrderStatus
                with orderRecord = ...
                with status = @variables.newStatus
    actions:
        GetOrderByNumber:
            inputs:
                "customerId": string
                "orderNumber": string
            outputs:
                "orderRecord": object
        UpdateOrderStatus:
            inputs:
                "orderRecord": object
                "status": string
```

**After:**
```
variables:
    customerId: string
    orderNumber: mutable string
    newStatus: mutable string
    orderRecord: mutable object

subagent OrderManagement:
    reasoning:
        instructions: ->
            | When updating an order status, first retrieve the order details with {!@actions.GetOrderDetails}, confirm the new status, then update it with {!@actions.UpdateStatus}.
        actions:
            GetOrderDetails: @actions.GetOrderByNumber
                with customerId = @variables.customerId
                with orderNumber = @variables.orderNumber
                set @variables.orderRecord = @outputs.orderRecord
            UpdateStatus: @actions.UpdateOrderStatus
                with orderRecord = @variables.orderRecord
                with status = @variables.newStatus
    actions:
        GetOrderByNumber:
            inputs:
                "customerId": string
                "orderNumber": string
            outputs:
                "orderRecord": object
        UpdateOrderStatus:
            inputs:
                "orderRecord": object
                "status": string
```

**Key improvements:**
1. Identified data producer: GetOrderByNumber has `outputs: "orderRecord"`
2. Identified data consumer: UpdateStatus has `...` placeholder for `orderRecord` input
3. Matched producer/consumer: "orderRecord" output matches "orderRecord" input
4. Wired data flow — ALL THREE STEPS:
   - Step A: Created new variable `orderRecord: mutable object`
   - Step B: Added `set @variables.orderRecord = @outputs.orderRecord` after GetOrderDetails
   - Step C: Replaced `...` with `@variables.orderRecord` in UpdateStatus action
