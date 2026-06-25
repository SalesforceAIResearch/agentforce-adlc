# Architecture Patterns

> Architecture mechanics reference. Start with `references/patterns-by-requirement.md`
> to choose patterns by scenario, then use this file for implementation details.

> All architecture patterns below work for both `AgentforceServiceAgent` and `AgentforceEmployeeAgent`. The only difference is that employee agents cannot use `@utils.escalate` or `connection messaging:` — replace escalation with a `@utils.transition` to a help subagent or an action that creates a case/ticket.

## When to Use Each Pattern

| Pattern | Use When |
|---------|----------|
| Router-First Architecture | Agent has 2+ distinct subagents with different intents (most common) |
| Verification Gate | Sensitive data, payments, or PII require identity verification first |
| Post-Action Loop | Actions produce state that drives follow-up logic (e.g., risk scoring) |
| Single Subagent | Agent serves one focused purpose with no routing needed |

## Router-First Default

This file focuses on router-first mechanics and migration details:

- `start_agent agent_router` handles intent routing
- Domain subagents implement use-case behavior
- Linear sequencing is usually workflow-local, not whole-agent architecture

## Router-First Architecture Mechanics

A central `agent_router` routes to specialized subagents. Transition paths should be use-case-driven: subagent -> subagent when workflow continues naturally, and subagent -> router when the conversation needs reclassification.

```agentscript
start_agent agent_router:
	description: "Route user requests to the appropriate subagent"
	reasoning:
		instructions: |
			You are a router only. Do NOT answer questions directly.
			Always use a transition action to route immediately.
		actions:
			to_orders: @utils.transition to @subagent.order_support
				description: "Order questions"
			to_returns: @utils.transition to @subagent.return_support
				description: "Return or refund requests"
			to_general: @utils.transition to @subagent.general_support
				description: "General questions"

subagent order_support:
	description: "Handle order inquiries"
	reasoning:
		instructions: ->
			| Help the customer with their order.
		actions:
			lookup: @actions.get_order
				description: "Look up order"
			to_returns: @utils.transition to @subagent.return_support
				description: "Continue to return workflow when needed"
```

> **Routing lives in `start_agent`** -- put classification transitions in `start_agent agent_router:`. Do NOT create a separate routing-only subagent (e.g. `main_menu`, `central_hub`) -- that duplicates the router, adds an extra LLM hop (~3-5s latency), and confuses the platform. A transition back to router is optional and should only be added when the use case requires reclassification.

> **`instructions: |` in a router is probabilistic.** The LLM may respond conversationally instead of emitting a transition — especially in multi-turn flows. For strict routing (verification gates, security flows), prefer `instructions: ->` with explicit `transition to` statements so routing is deterministic and cannot be skipped.

## Verification Gate

Users must pass through identity verification before accessing protected subagents. Use when handling sensitive data, payments, or PII. Uses deterministic routing (`instructions: ->`) so the gate cannot be bypassed by LLM conversational drift.

```agentscript
start_agent agent_router:
	description: "Route through identity verification"
	reasoning:
		instructions: ->
			if @variables.is_verified == False:
				transition to @subagent.identity_verification

			| Select the best tool to call based on conversation history and user's intent.
		actions:
			to_account: @utils.transition to @subagent.account_mgmt
				description: "Account management"
				available when @variables.is_verified == True
			to_refund: @utils.transition to @subagent.refund_processor
				description: "Process a refund"
				available when @variables.is_verified == True

subagent identity_verification:
	description: "Verify customer identity"
	reasoning:
		instructions: ->
			if @variables.failed_attempts >= 3:
				| Too many failed attempts. Transferring to human agent.
				transition to @subagent.escalation

			if @variables.is_verified == True:
				| Identity verified! How can I help?

			if @variables.is_verified == False:
				| Please verify your identity.

		actions:
			verify_email: @actions.verify_identity
				description: "Verify customer email"
				set @variables.is_verified = @outputs.verified

			to_account: @utils.transition to @subagent.account_mgmt
				description: "Account management"
				available when @variables.is_verified == True

			escalate_now: @utils.escalate
				description: "Transfer to human"
```

## Post-Action Loop

The subagent re-resolves after an action completes. Place post-action checks at the TOP of `instructions: ->` so they trigger on the loop:

```agentscript
reasoning:
	instructions: ->
		# POST-ACTION CHECK (at TOP - triggers on re-resolution)
		if @variables.refund_status == "Approved":
			run @actions.create_crm_case
				with customer_id = @variables.customer_id
			transition to @subagent.confirmation

		# PRE-LLM: Load data
		run @actions.load_risk_score
			with customer_id = @variables.customer_id
			set @variables.risk_score = @outputs.score

		# DYNAMIC INSTRUCTIONS
		| Risk score: {!@variables.risk_score}
		if @variables.risk_score >= 80:
			| HIGH RISK - Offer retention package.
		else:
			| STANDARD - Follow normal process.
```

## Migrating to Router-First Architecture

When refactoring a flat agent (all logic in one subagent) into router-first architecture:

1. **Identify distinct intents** — each becomes a specialized subagent
2. **Move instructions and actions** from the monolithic subagent into specialized subagents. Each subagent needs BOTH its Level 1 action definitions (under `subagent > actions`) AND Level 2 action invocations (under `subagent > reasoning > actions`).
3. **Create `start_agent agent_router:`** with transition actions pointing to each specialized subagent
4. **Add transitions based on workflow needs** — subagent -> subagent for continuous workflows, or subagent -> router for reclassification turns
5. **Re-preview immediately** — verify subagent routing works before making further changes

**Common migration mistakes:**
- Creating a separate `main_menu` subagent instead of using `start_agent agent_router:` as the hub — adds an unnecessary LLM hop
- Leaving action definitions in `start_agent` instead of moving them to specialized subagents — all actions visible in all subagents, confusing the planner
- Routing everything back to router by default, even when a direct subagent-to-subagent transition better matches the workflow
- If trace shows `topic: "DefaultTopic"`, check that subagent descriptions contain keywords matching test utterances

## Multi-Intent Handling

When a user sends multiple intents in one message, the start_agent router should handle the first intent and queue the second:

```agentscript
instructions: |
	You are a router only. Do NOT answer questions directly.
	If the user asks about multiple subagents in one message, route to the first
	subagent. After that task is complete, remind the user about the other request.
```

## Handling Incomplete Action Inputs

- Use `with param = ...` (slot-fill) for inputs the LLM should extract from conversation
- Add instructions that tell the LLM to invoke the action with whatever data is available
- Anti-pattern: Making the LLM ask for ALL inputs before invoking

## Controlling Opportunistic Action Chains

In long action chains (A->B->C->D), the LLM may invoke downstream actions as soon as prerequisites are met. To control this:

- Add explicit gating in instructions: "Only invoke generate_resolution if the user explicitly asks"
- Use `available when` guards on downstream actions
- Distinguish between "analyze only" and "full resolution" workflows in instructions

Anti-pattern: Leaving action chains ungated so the LLM runs the entire pipeline for every query.
