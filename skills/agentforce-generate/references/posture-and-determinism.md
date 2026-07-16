# Authoring Posture: Agentic vs Deterministic

This guide defines how to choose the right posture for each subagent.

Posture is the dial between model latitude (agentic) and authored control
(deterministic). Choose posture first, then choose subagent organization
(router-first architecture, verification gate, and so on).

## Core Principle

Default to the most agentic posture that still meets the requirement.

Pin determinism only with cause:

- Regulated, audited, or legally constrained steps
- Identity, trust, or authorization gates
- A failure mode observed in preview or production traces

Avoid defaulting to scripted instructions because they feel safer. Over-scripted
flows are brittle and expensive to maintain.

## Primary Controls

Three primitives control posture:

1. `available when`  
   Primary invariant tool. Hide actions when preconditions are false.
2. `with param = ...` vs `with param = value`  
   Default to `...`. Pin values only when sourced from controlled state
   (for example, verified `customer_id`) or when extraction has already failed.
3. `if` / `else` in `instructions: ->`  
   Use conditional instructions to adapt behavior by state. More branching means
   more authored control.

## Failure Mode to Avoid

Do not start with step-by-step **prose** directives like:

- `Step 1: invoke X`
- `Step 2: invoke Y`
- `CRITICAL: always invoke Z`

These ask the LLM to follow a fixed procedure via natural language — brittle
and easily ignored.

However, **deterministic `if/else` conditionals are not "scripted" prose** — they
are resolved by the runtime before the LLM sees the prompt. Using `if/else` to
branch instructions, load data, or transition subagents does NOT conflict with
agentic posture. It strengthens it by giving the LLM a clear, state-appropriate
prompt rather than asking it to self-select from a wall of conditional prose.

**Use `if/else` freely when:**
- The branch depends on known variable state (verified, loaded, approved)
- The behavior should be guaranteed regardless of LLM reasoning
- You are routing, gating, or injecting data

**Use prose instructions when:**
- The LLM needs judgment/flexibility (tone, phrasing, edge-case handling)
- The decision depends on unstructured user input the LLM must interpret
- There is no variable that captures the relevant state

## Posture Matrix

| Decision | Scripted | Mixed | Agentic |
|---|---|---|---|
| Action ordering | chained `available when` per step | `available when` on real invariants | `available when` on real invariants |
| Action parameters | mostly pinned | mixed pinned + `...` | mostly `...` |
| Instructions | step-by-step with many branches | guidance with targeted branching | high-level intent, minimal branching |

When uncertain, start mixed.

## Scripted Posture

Use when requirements are regulated, audited, or require strict traceability.

Signals in requirements:

- "regulated"
- "compliance"
- "auditable"
- "must trace every step"

Structural expectations:

- Heavy `available when` gating per stage
- Parameters mostly pinned to authored variables
- Detailed, stepwise branching in instructions

## Mixed Posture

Use for most production customer-facing agents.

Typical shape:

- Gate real invariants only (identity, entitlement, eligibility)
- Pin controlled values (for example `customer_id`), keep other values as `...`
- Use concise guidance, not full scripts

## Agentic Posture

Use for open-ended assistance where the model can safely carry more reasoning.

Typical shape:

- Minimal gating outside trust/security invariants
- Most parameters use `...`
- High-level intent instructions with minimal branching

## Review Checklist

For each subagent:

1. Which posture is selected?
2. Why that posture (regulation, trust gate, or observed failure)?
3. Which invariants are enforced with `available when`?
4. Which parameters are pinned, and what controlled source justifies each pin?
5. Which instructions can be simplified without losing required control?

If an answer cannot cite a requirement or observed failure, loosen posture.
