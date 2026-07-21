# Schema Data Download

## Goal

Download data for every object included in the finalized schema object set. Do not download data for only a subset of objects.

## Input

- `schema_selection_json` (required): output JSON from schema selection step (saved to `artifacts/schema-selection.json`)
- `org_alias` (required): authenticated Salesforce org alias

## Required Behavior

1. Parse `artifacts/schema-selection.json`.
2. Read all object API names from `schema.objects` keys.
3. For each object in that set:
   - Read selected field names from `schema.objects[<ObjectApiName>].fields[*].name`.
   - Build a comma-separated field list from those names only.
   - Limit records to at most **500** per object.
   - Run:

```bash
sf data query --query "SELECT <SelectedFieldList> FROM <ObjectApiName> LIMIT 500" --target-org <org_alias> --result-format csv
```

4. Save each query result to an artifact file under `artifacts/schema-data/` named `<ObjectApiName>.csv`.
5. Continue even if one object query fails; record failures and proceed with remaining objects.
6. At the end, report:
   - total objects in schema
   - successful downloads
   - failed downloads (with error summaries)
7. Enforce completion check:
   - `expected_objects = count(schema.objects keys)`
   - `downloaded_objects = count(csv files created for distinct object names)`
   - If `downloaded_objects != expected_objects`, treat as incomplete and list exactly which objects are missing (including parent-chain objects).

## Guardrails

- The download list must come from final `schema.objects`, not from relationship snippets alone.
- For each object, the query field list must come only from that object's selected schema fields; do not use `FIELDS(ALL)`.
- Record cap is mandatory: do not download more than 500 rows for any single object in this step.
- If `schema.objects` includes parent chain objects (for example `Order`, `Contact`, `Account`), download all of them.
- Do not skip parent or transitive parent objects once they are present in `schema.objects`.
- Parent objects are first-class objects for download; they are not optional enrichments.
