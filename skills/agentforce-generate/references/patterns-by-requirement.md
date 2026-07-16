# Patterns by Requirement

Use this guide to choose patterns based on product requirements, not topology labels.

Default shape for most agents:

- Router-first architecture using `start_agent agent_router`
- Subagent-specific posture (scripted, mixed, agentic)
- Deterministic controls only where justified

Read this file first when deciding architecture and flow patterns. Then use:

- `references/architecture-patterns.md` for architecture mechanics and migration guidance
- `assets/patterns/` for concrete pattern snippets

## Quick Selection Table

| Requirement / Scenario | Recommended Pattern | Why | Reference Assets |
|---|---|---|---|
| Agent handles multiple intents/domains | Router-first architecture | Fast intent routing, clean separation of subagents | `references/architecture-patterns.md`, `assets/agents/router-first.agent`, `assets/agents/template-multi-subagent.agent` |
| Identity/trust gate before protected operations | Verification gate | Enforces trust invariant before sensitive actions | `references/architecture-patterns.md`, `assets/patterns/open-gate-routing.agent` |
| Need deterministic follow-up after action | Action callbacks (`run`) | Guarantees ordered post-action execution | `assets/patterns/action-callbacks.agent` |
| Need setup/cleanup every reasoning turn | Lifecycle events | Consistent pre/post reasoning hooks | `assets/patterns/lifecycle-events.agent` |
| Need specialist consultation and return | Bidirectional routing/delegation | Keeps workflow continuity across subagents | `assets/patterns/bidirectional-routing.agent`, `assets/patterns/delegation-routing.agent` |
| Complex action input strategy required | Advanced input bindings | Mixes slot filling, variable binding, output chaining | `assets/patterns/advanced-input-bindings.agent`, `assets/patterns/critical-input-collection.agent` |
| Dynamic instruction behavior by context | Context-aware instruction layering | Combines stable `system` baseline with subagent-level conditional instructions by segment/time/state | `assets/patterns/system-instruction-overrides.agent`, `assets/patterns/procedural-instructions.agent` |
| Multi-step workflow inside one use case | Workflow-local linear steps | Enforces sequence where needed without making whole agent linear | `assets/patterns/multi-step-workflow.agent`, `assets/patterns/procedural-instructions.agent` |
| Prefer LLM-led flexibility with minimal pinning | LLM-controlled actions | Keeps implementation agentic by default | `assets/patterns/llm-controlled-actions.agent` |
| Prompt-template-backed action usage | Prompt template action pattern | Standardized prompt action wiring | `assets/patterns/prompt-template-action.agent` |

## Decision Rules

1. **Choose posture first (per subagent).**
   - Start agentic or mixed.
   - Move scripted only when required by regulation, trust, or observed failure.
   - See `references/posture-and-determinism.md`.

2. **Choose architecture second.**
   - Start with router-first architecture.
   - Add verification gates for protected operations.
   - Add workflow-local linear sequencing only where required.

3. **Choose implementation patterns third.**
   - Add lifecycle/callback/input-binding patterns to solve concrete behavior gaps.
   - Prefer the smallest pattern that satisfies the requirement.

## Common Compositions

### Customer Service Baseline

- Router-first architecture
- Verification gate for protected actions
- Advanced input bindings for action parameters
- Lifecycle events for analytics/telemetry

### Regulated Flow

- Router-first architecture
- Verification gate
- Scripted posture on regulated subagent
- Action callbacks for deterministic post-action chain

### Open-Ended Assistant

- Router-first architecture
- Agentic posture for most subagents
- Minimal deterministic controls
- LLM-controlled actions and selective input pinning

## Anti-Patterns

- Modeling the entire agent as linear when only one workflow needs sequencing
- Creating a separate router subagent instead of using `start_agent agent_router`
- Routing every turn back to router by default instead of using direct subagent transitions when workflow intent is clear
- Overusing deterministic controls without requirement or observed failure
- Pinning all action inputs by default instead of using `...` where safe

