# Extract Use Cases -- Prompt Analysis Reference

> Extracted from the use-case extraction prompt. This file is loaded on demand when classifying prompt specificity and producing structured use cases.

## Overview

Analyze a user-provided agent request prompt (optionally with org schema/data context), classify prompt specificity (`Level 1`, `Level 2`, or `Level 3`), then return a normalized JSON object containing detected use cases, sub-tasks, and mapped sample questions.

## Inputs

- `User Prompt`: the request describing what the agent should do
- `Org Context` (optional): schema and sampled records downloaded from the org after user approval

Input template:

```text
User Prompt: [USER_PROMPT]
Org Context (optional): [SCHEMA_AND_SAMPLE_DATA]
```

## Prompt Specificity Levels

### Level 1 (high-level, low specificity)
- Short and vague requests
- No sample questions, object references, guardrails, or edge cases
- Usually states only a broad intent (for example, "create a service agent")

**Required behavior:** Propose all plausible concrete use cases that fit the broad ask. If org context is available, prioritize use cases grounded in discovered objects and data.

### Level 2 (medium specificity)
- Contains sample questions, basic flows, and/or tone guidance
- Mentions some concrete capabilities but limited operational detail

**Required behavior:** Extract one or more use cases from prompt evidence; identify sub-tasks where implied or explicit; map sample questions to the correct use case and sub-task.

### Level 3 (low-level, detailed)
- Includes technical/operational detail such as objects, guardrails, edge cases, approvals, audit trail, synthetic data, policy constraints, or escalation logic

**Required behavior:** Extract one or more use cases directly from the prompt with explicit traceability to detailed statements; capture sub-tasks and map sample questions to sub-tasks.

## Extraction Rules

1. Classify prompt as exactly one level: `1`, `2`, or `3`.
2. If level is `1`, propose plausible use cases for the broad request, even when not explicitly listed.
3. If org context is present, prefer use cases and sub-tasks that map to available objects/fields and realistic record workflows.
4. If level is `2` or `3`, identify use cases from the prompt text (do not invent unrelated use cases).
5. Extract or identify sub-tasks under each use case when present.
6. If sample questions are provided, map each question to:
   - the correct `use_case_name`
   - the correct `sub_task_name`
7. If sample questions exist but sub-tasks are not explicit, propose sub-tasks that align with those questions.
8. If no sub-tasks or sample questions are present, return `sub_tasks: []`.
9. Keep `use_case_name` and `sub_task_name` concise and business-readable.
10. `prompt_statement` must preserve the prompt evidence used to identify each use case:
   - single statement (string), or
   - list of statements when multiple lines support one use case
11. Return exactly one JSON object in the required schema (no markdown, no extra keys, no commentary).

## Output Format (Strict)

Return a single JSON object with exactly these top-level keys:

- `detected_level`
- `use_cases`

Schema:

```json
{
  "detected_level": 1,
  "use_cases": [
    {
      "prompt_statement": "Handle order tracking requests",
      "use_case_name": "Order Management",
      "use_case_description": "Supports order status and shipment visibility workflows.",
      "sub_tasks": [
        {
          "sub_task_name": "Order Status Inquiry",
          "sub_task_description": "Collects order identifier and returns shipment status.",
          "sample_questions": [
            "Where is my package?"
          ]
        }
      ]
    }
  ]
}
```

## Output Constraints

- `detected_level` must be numeric: `1`, `2`, or `3`
- `use_cases` must always be an array (empty only if no meaningful use case can be inferred)
- `sub_tasks` must always be an array
- `sample_questions` is optional, but include it when user provided sample questions else make it empty
- Do not include trailing commas
- Do not include comments or additional metadata fields

## Mapping Guidance

### Use Case Identification
- Prefer domain outcomes (for example: "Order Management", "Returns and Refunds", "Case Management")
- Avoid naming use cases after vague verbs ("Help Customer")

### Sub-task Identification
- Represent actionable units inside a use case
- Good examples: "Verify Order Number", "Check Delivery Status", "Explain Return Policy", "Escalate Lost Package"

### Question-to-Sub-task Mapping
- Each sample question should map to the most specific sub-task
- If one question could fit multiple sub-tasks, choose the primary operational intent

## Decision Heuristics

Use this quick rubric when level boundaries are unclear:

- **Likely Level 1:** one sentence, broad ask, no examples, no constraints
- **Likely Level 2:** includes sample utterances, capability examples, or tone/style guidance
- **Likely Level 3:** includes policy/guardrail logic, object/entity references, edge-case handling, approvals, auditability, abuse controls, or test-data requirements

When ambiguous between two adjacent levels:
- Prefer `Level 2` over `Level 1` if sample questions are present
- Prefer `Level 3` over `Level 2` if operational guardrails and edge-case decisioning are explicit
