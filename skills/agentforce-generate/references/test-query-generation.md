# Test Query Generation

## Goal

Generate grounded agent-testing queries from the finalized schema, use-case→object mapping, and downloaded org data.

Core idea (relationship-graph grounding):

1. From use-case→object mapping, **generate sub-tasks and query templates** first (they may not exist yet).
2. Build the schema relationship graph and find its connected **subgraphs**.
3. For each subgraph, pick the **start object** (the object with no parent in that subgraph), sample a random start record, and **traverse child/related records** via foreign keys.
4. For each sub-task **template**, check whether the traversed record bundle covers every object that template needs.
5. If coverage succeeds, those records are the template’s **ground truth**; fill placeholders from them, derive the **ground-truth answer** from those records, and **paraphrase** into a natural user utterance.
6. Persist metadata: `objects_required`, `ground_truth_answer`, and when the query needs customer verification, correct `user_context` (`AccountId` and/or `ContactId`).
7. **Cover every template** — for each template, generate **2–3 grounded queries** (do not skip templates that can be grounded).

This stage runs after [Schema Selection](schema-selection.md) and [Schema Data Download](schema-data-download.md).

## Inputs

- `artifacts/schema-selection.json` (required):
  - `schema.objects` — objects, fields, relationships
  - `schema.use_case_object_mapping` — **use case → objects** (sub-tasks may be empty or absent)
- `artifacts/schema-data/*.csv` (required): downloaded records per object

**Assumption:** prior steps guarantee use cases and use-case→object mapping. They do **not** guarantee sub-tasks or query templates. Generate those in this stage before grounding.

## Output Artifacts

- `artifacts/test-query-subtasks.json` — generated sub-tasks per use case
- `artifacts/test-query-templates.json` — use case → sub-task → templates (before grounding)
- `artifacts/test-queries.jsonl` — one grounded test query per line
- `artifacts/test-queries-summary.json` — coverage counts, uncovered templates, subgraphs used

### Per-query metadata (required fields)

```json
{
  "query": "What's the status of my order 00001234?",
  "template_id": "Order Status Inquiry::by_order_number",
  "use_case_name": "Order Management",
  "sub_task_name": "Order Status Inquiry",
  "objects_required": ["Account", "Order", "OrderItem"],
  "ground_truth_records": {
    "Account": [{"Id": "001...", "Name": "..."}],
    "Order": [{"Id": "801...", "OrderNumber": "00001234", "AccountId": "001..."}],
    "OrderItem": [{"Id": "802...", "OrderId": "801..."}]
  },
  "replacements": {
    "[Order_OrderNumber]": "00001234"
  },
  "ground_truth_answer": "Your order 00001234 is Currently Shipping.",
  "requires_customer_verification": true,
  "user_context": {
    "AccountId": "001...",
    "ContactId": "003..."
  },
  "answerability": "answerable",
  "subgraph_id": "sg_0",
  "start_object": "Account"
}
```

Rules for metadata:

- `objects_required` must list every object the template needs (from mapping + template placeholders). Never omit.
- `ground_truth_answer` is required on every final constructed query:
  - For `answerability: "answerable"`, it must be the correct response derivable from `ground_truth_records` / downloaded field values for that query.
  - For `answerability: "unanswerable"`, it must state that the requested information is not available / cannot be answered from the data (or the expected refusal behavior).
- If `requires_customer_verification` is true, `user_context` **must** include the appropriate identity:
  - Prefer `ContactId` when Contact exists and the agent verifies the end user.
  - Include `AccountId` when Account is the customer root or Contact is missing.
  - Values must come from the same traversed record bundle (same customer), not unrelated rows.
- If verification is not required (catalog/product-only templates), set `requires_customer_verification: false` and omit or leave `user_context` empty.

## Required Algorithm

### Step 1 — Generate sub-tasks and templates from use-case→object mapping

Prior steps provide use cases and which objects each use case needs. Sub-tasks and templates are usually missing — generate them here before any grounding.

#### 1a. Generate sub-tasks

1. Load `schema.use_case_object_mapping` and `schema.objects`.
2. For each use case:
   - If `sub_tasks` already exist and comprehensively cover the use case, keep them and only add missing ones if needed.
   - Otherwise, propose concrete sub-tasks from:
     - use case name/description
     - mapped objects and their fields/relationships
   - Each sub-task must include:
     - `sub_task_name`
     - `sub_task_description`
     - `objects` — subset of the use case’s mapped objects required for that sub-task
3. Save to `artifacts/test-query-subtasks.json`.

#### 1b. Generate templates for every sub-task

1. For each sub-task, generate a comprehensive list of **sample templates**: natural customer/user questions with placeholders for relevant schema fields (e.g. `"What is the status of my order [OrderNumber]?"`).
2. **Answerability constraint (mandatory):** every template must be answerable using only:
   - objects mapped to that use case (and the sub-task’s object subset), and
   - fields that exist on those objects in `schema.objects` **and** appear in the downloaded CSVs under `artifacts/schema-data/`.
   - Do not invent placeholders for fields that are missing from downloaded data.
   - Do not require objects outside the use case’s mapped object set.
   - Prefer placeholders whose values are actually populated in sampled downloaded rows (avoid fields that are always null/empty in the data).
3. Produce enough templates to cover the sub-task thoroughly (typically 10–20 when inventing from scratch; keep any existing sample questions and expand, filtering any that violate the answerability constraint).
4. Persist to `artifacts/test-query-templates.json` keyed by:

```text
use_case_name -> sub_task_name -> [templates...]
```

5. Every template must declare:
   - placeholder list (e.g. `[OrderNumber]`, `[Product2_Name]`, `[EffectiveDate]`)
   - `objects_required` (union of the sub-task’s objects and objects implied by placeholders; must be ⊆ use-case mapped objects)
   - `requires_customer_verification` (true when the utterance is about “my” / customer-owned data)

**Hard rule:** do not proceed to subgraph traversal until sub-tasks and templates exist for every use case. Then, for **every** template, generate **2–3** grounded queries (different record seeds and/or paraphrases). Do not stop at a single query per template.

### Step 2 — Build schema relationship graph and find subgraphs

From `schema.objects[*].relationships`, build an undirected multigraph:

- Node = object API name
- Edge = lookup/master-detail (`foreign_key` ↔ `parent_object` / `parent_object_field`)

Then:

1. Compute connected components → **subgraphs** (`sg_0`, `sg_1`, ...).
2. For each subgraph, identify the **start object**: the object that has **no parent object within that subgraph** (in-degree 0 under parent→child edges from `relationships`).
   - A start object is the subgraph root — traversal begins there and walks downward to children.
   - If multiple objects have no parent in the subgraph, treat each as a start object and run traversal from each.
   - If a cycle leaves no parentless object, break the cycle at a deterministic root (stable object-name order) and document that choice in the summary.
3. Orient relationships outward from the start object (parent → children) for traversal.

Isolated objects (no relationships) are singleton subgraphs; ground only templates whose `objects_required` ⊆ that singleton.

### Step 3 — Sample start records and traverse related records

For each subgraph:

1. Load CSV data for every object in the subgraph from `artifacts/schema-data/`.
2. Sample random start-object records (retry until coverage succeeds or retries exhaust). Typical: up to ~25 distinct start seeds per subgraph.
3. For each start record, BFS/queue-traverse relationships:
   - From current record, follow each related child via matching FK values.
   - Collect a **record bundle**: `{ ObjectApiName: [records...] }` plus relationship provenance.
   - Cap expansion depth/breadth to keep bundles usable (e.g. sample ≤ few children per edge), but do not drop objects needed for template coverage when they exist.

This record bundle is the candidate **ground-truth graph instance** for that seed.

### Step 4 — Match templates to traversed bundles

For each template (across all use cases / sub-tasks):

1. Let `needed = template.objects_required`.
2. Find traversed bundles whose object sets cover `needed` (all required objects present with ≥1 record).
   - Prefer bundles from the subgraph that intersects `needed` most strongly.
   - If multiple child records exist for a needed object, pick the appropriate one for the template (e.g. open Case for “current open case”, matching OrderItem for a product placeholder).
3. Produce **2–3 grounded queries per template**:
   - Prefer distinct start seeds / record bundles when available so queries are not identical clones.
   - If only one covering bundle exists, still produce 2–3 queries via paraphrase of the grounded utterance while keeping the same ground-truth records/answer (or regenerating answer if paraphrase does not change facts).
4. If fewer than 2 covering attempts succeed, retry with more start seeds in the relevant subgraph(s).
5. If still uncovered after retries, record the template under `uncovered_templates` in the summary and continue (do not silently drop without reporting).

### Step 5 — Ground placeholders and attach ground truth

When a covering bundle is found:

1. Fill each template placeholder from the chosen records (human-facing values: order number, case number, product name, relative period from dates, etc.).
2. Store:
   - `ground_truth_records` — the minimal record set that answers the template
   - `replacements` — placeholder → concrete value
   - `objects_required` — unchanged from template metadata
3. **Construct `ground_truth_answer`** from `ground_truth_records`:
   - Derive the expected agent answer using only fields present in those records (and related records in the same bundle needed by the template).
   - The answer must directly resolve the grounded query (status, list of items, price, etc.).
   - Keep it concise and factual; do not invent values not present in the records.
   - Every final query written to `artifacts/test-queries.jsonl` must include `ground_truth_answer`.
4. If `requires_customer_verification`:
   - Resolve `AccountId` / `ContactId` from the same bundle (via Account/Contact rows or FKs on owned records).
   - Fail the grounding attempt if verification is required but identity cannot be resolved.

### Step 6 — Paraphrase

Paraphrase grounded utterances into natural variants while:

- Preserving meaning and answerability
- **Not** changing product names, order/case numbers, or other identity placeholders
- Simplifying datetimes to readable date forms when present
- Producing distinct wording across paraphrases of the same template structure

Keep both the grounded seed and paraphrased form linked to the same metadata, `ground_truth_records`, and `ground_truth_answer`.

### Step 7 — Optional unanswerable / negative variants

After answerable coverage is complete, optionally generate unanswerable variants by perturbing one critical grounded value (wrong id, wrong period, wrong product) while keeping user_context consistent. Mark `answerability: "unanswerable"` and set `ground_truth_answer` to the expected unanswerable/refusal outcome. Do **not** let this reduce coverage of answerable templates.

### Step 8 — Persist and report

Write:

1. `artifacts/test-queries.jsonl` — all grounded queries with full metadata
2. `artifacts/test-queries-summary.json` including:
   - subgraph count and start objects
   - template count vs grounded count
   - queries per template (target 2–3)
   - uncovered templates (by use case / sub-task)
   - verification coverage (how many queries have valid `user_context`)

Present a short coverage report to the user before continuing agent design.

## Coverage Requirements

- Every use case in the mapping must have generated sub-tasks before grounding.
- Every sub-task must have templates before grounding.
- Every template in `test-query-templates.json` must be attempted.
- Every successfully grounded template must yield **2–3** final queries in `test-queries.jsonl`.
- Every use case and every sub-task with templates must appear in output when grounding succeeds.
- Every grounded query must include accurate `objects_required`.
- Every final constructed query must include a non-empty `ground_truth_answer`.
- Every customer-owned query must include correct `user_context` identity fields.

## Validation Checks

Before finishing:

1. **Template coverage** — every template is attempted; each grounded template has 2–3 queries, or uncovered list is explicit and non-empty only for data sparsity.
   - Also report `queries_per_template` in the summary.
2. **Object integrity** — for each query, every name in `objects_required` appears in `ground_truth_records` keys (answerable only).
3. **Ground-truth answer integrity** — every final query has `ground_truth_answer`; for answerable queries, values asserted in the answer must be supported by `ground_truth_records`.
4. **Verification integrity** — if `requires_customer_verification`, `user_context.AccountId` and/or `ContactId` is present and matches FKs in ground-truth owned records.
5. **Subgraph integrity** — `objects_required` for a grounded query lie within one traversed subgraph instance (no mixing unrelated seeds).
6. **Paraphrase integrity** — identity tokens from `replacements` still appear unchanged in paraphrased `query`.

## Failure Handling

- Sparse object CSV → keep trying alternate start seeds; report which templates could not be covered.
- Missing relationship metadata → treat objects as isolated subgraphs; only ground single-object templates.
- Missing Contact when Account exists → use `AccountId` alone in `user_context` when that is sufficient for verification.
- Paraphrase failure → keep the grounded (pre-paraphrase) utterance rather than dropping the query.
- Cannot derive `ground_truth_answer` from records → treat grounding as failed for that template attempt and retry with another seed; do not emit the query without an answer.
