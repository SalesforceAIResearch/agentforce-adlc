# Schema Selection -- Intent-to-Org Reference

## Overview

Select a Salesforce schema from a user prompt, extracted use cases, and an org. The output will subsequently be used to create an agent to answer user's queries. Based on the use cases, select all appropriate objects after querying the org that may be required to comprehensively answer user's queries. The org may contain many standard and custom objects. The goal is to select the relevant ones to have a schema that can be used by an agent to answer user's queries.

This stage runs after [Extract Use Cases](extract-usecases.md).

## Inputs

- `user_prompt` (required): raw user request
- `use_cases` (required): JSON output from `extract-usecases.md`
- `org_alias` (required): authenticated Salesforce org alias used for CLI queries

## Fetch Org Schema with SF CLI

### 1) Fetch object inventory and shortlist objects

```bash
sf sobject list --json -o <org_alias>
```

Based on this list first shortlist all the objects required for the use cases and user prompt based on the following 2 steps recall-precision procedure.
- Understand the scope and description of each use case.
- Go through each use case and think of the objects required to cover the use case.
- You should assume that each standard object is used as per its Salesforce documentation purpose only and do not intend to store any other type of data.
- If you think some use case cannot be covered by any object, then do not include any objects in your response for those use case.
- You should not include any object just because there are no other objects that are more relevant to some use case.
- Do not select an object based solely on its name or description. You should use your own knowledge of the fields that object has based on Salesforce documentation.
- A use case may require one or more than one object to be selected.
- Make sure you select object as well as all its lookup or parent objects that are required for functioning of the object.

Use a recall-then-precision flow:

1. **Stage S1 (recall):**
   - Run object selection. These objects should be the ones that are relevant to the use case.
   - Get metadata of each shortlisted object
```bash
sf sobject describe --json -o <org_alias> --sobject <ObjectApiName>
```
   - From each describe response, extract:

    - field name (`name`)
    - field type (`type`)
    - createability (`createable`)
    - nullability (`nillable`)
    - defaulted-on-create (`defaultedOnCreate`)
    - relationship target (`referenceTo`)
    - label/description when available

    ##### Guardrails and Exclusions

    Before object scoring or field selection:

    1. Consider only objects that are create-capable.
    2. Exclude setup/system/non-functional objects by policy.
    3. Exclude commonly non-business fields from final field lists:
      - `OwnerId`
      - `RecordTypeId`
    4. Never propose objects that are not available in the provided candidate object list.

    Default excluded patterns:

    - Suffixes: `Share`, `History`, `Feed`, `Tag`, `Layout`, `Settings`, `EmailTemplate`, `SharingRule`, `AuraDefinition`, `EventRelation`, `ProductSellingModel`, `Individual`, `DandbCompany`, `AssignmentRule`, `AssignmentRuleItem`, `ShareRule`, `Document`
    - Prefixes: `AccountPlan`, `Apex`, `Flow`, `Auth`, `User`, `Permission`, `Profile`, `Platform`, `Wave`, `Analytics`, `Tax`, `Territory`, `Content`
    - Exact names: `AuthorizationFormText`, `RecordType`, `EmailMessageRelation`, `CaseSolution`, `Solution`, `CaseTeamTemplate`, `CaseTeamTemplateMember`, `EmailRoutingAddress`, `Attachment`, `ActivityMetric`, `AgentWork`, `StaticResource`, `CustomNotificationType`, `Folder`, `ExternalDataSource`, `FeedItem`, `Group`, `MessagingSession`, `MessagingChannel`, `MessagingEndUser`

2. **Stage S2 (precision):**
   - Score each S1 candidate from `1` to `10`
   - Keep objects with score `>= 6`
   - Objects the use case CANNOT function without should score 9-10
   - 7-8  = IMPORTANT — Directly enables a core capability even without a required foreign key dependency. Removing it would leave a significant functional gap.
   - 5-6  = SUPPORTING — Enriches the model but the core use case functions without it.
   - 3-4  = PERIPHERAL — Tangentially related, generic utility.
   - 1-2  = NOT RELEVANT — Does not belong in this data model.

S2 scoring must include:

- use-case context
- child-parent relationship hints among candidates
- candidate frequency from S1 (confidence signal)

Default inclusion override:
- If the request is for a customer service agent, service/support workflows, or otherwise needs access to customer information, include `Account` and `Contact` by default. This is mandatory to identify the customers.
- Apply this override before parent closure so downstream relationship expansion can build correctly.


### 2) Mandatory parent object closure (transitive)

For shortlisted objects, parent/lookup expansion is required (not optional). Final schema must include all required parent objects and any transitive parents needed for realistic read/write workflows.

Use the following deterministic algorithm:

1. Initialize `final_objects = S2_selected_objects`.
2. For each object in `final_objects`, read its describe metadata and inspect all reference fields (`type=reference`).
3. For each reference field:
   - Add every valid business parent from `referenceTo` when either:
     - the field is non-nillable (required foreign key), or
     - the field is nullable but parent context is needed for identity, customer/account context, lifecycle context, ownership context, joins, or workflow execution.
4. Repeat step 2-3 for every newly added parent object until no new objects are added (fixed-point closure).
5. Never drop a parent that is required by any selected child in the closure.

Object materialization requirement:
- Every object discovered during closure must be materialized in `schema.objects` (with `fields`, `description`, and `relationships`), not only referenced from another object's `relationships`.
- If `Child.relationships[*].parent_object == X`, then `schema.objects.X` must exist in final output.
- Apply field selection rules (Section 5) to all materialized parent objects as well.

Hard rule and example:
- If `Order` is selected, include `Contact` and `Account` when relationship metadata indicates those parent chains are required for business context/workflows.
- In general, include parent-of-parent objects whenever the intermediate parent depends on them.

Filtering constraints after closure:
- You may remove optional parents only if removing them does not break referential integrity or core workflow understanding/queryability/writability.
- After any filtering, recompute closure and re-add all required parents before finalizing.

Pre-output integrity check (must pass):
1. Build set `R = { all relationships[*].parent_object across schema.objects }`.
2. Build set `O = { all keys in schema.objects }`.
3. Require `R ⊆ O`. If not, add missing objects to `schema.objects`, run closure again, and re-run this check.
4. Ensure transitive chains are closed: if `A -> B` and `B -> C` are required, final objects include `A`, `B`, and `C`.

### 3) Map use cases to selected objects

Map each use case and sub-task to selected objects after S2 selection, then update mappings after parent closure so every retained parent object is attached to at least one relevant use case/sub-task.

Rules:
1. Objects can appear in multiple use cases.
2. Only selected objects may be used.
3. Every selected object must be mapped to at least one use case or sub-task.
4. If sub-tasks exist, include object mappings at sub-task level.
5. Use-case-level objects must be the union of that use case's sub-task objects.

### 4) Field selection per object

For each final object:

1. Start from createable fields.
2. Remove defaulted/system-only fields where applicable.
3. Preserve relationship fields needed by retained object relationships.
4. Select the most relevant business fields for use cases.
5. Limit to **maximum 15 fields per object**.
6. Always include required-on-create fields from org describe metadata.
7. Keep object coverage complete: every final object must appear in output.

If a reference field points to an object not retained in the final object set, remove that reference field.

## Special Selection Rule (Object-Explicit Prompts)

If the user prompt explicitly names object(s) with restrictive wording like `only`, `just`, or `only for`, keep exactly those named objects and skip adding supporting objects unless user intent clearly requires relationship traversal.

## Output Contract

Return a single JSON object with this shape:

```json
{
  "schema": {
    "objects": {
      "Account": {
        "fields": [
          { "name": "Name", "type": "string", "description": "..." }
        ],
        "description": "...",
        "relationships": [
          { "foreign_key": "ParentId", "parent_object": "Account", "parent_object_field": "Id" }
        ]
      }
    },
    "use_case_object_mapping": [
      {
        "use_case_name": "Order Management",
        "objects": ["Account", "Order"],
        "sub_tasks": [
          { "sub_task_name": "Order Status Inquiry", "objects": ["Order"] }
        ]
      }
    ]
  }
}
```

## Runtime Behavior and Fallbacks

- If S2 scoring fails, use S1 union.
- If parent filtering fails, keep all optional parents.
- If field selection fails for an object, keep required fields plus essential relationship fields.
