# Scorer Validation — AI Testing Center (NGT test suite)

The **test-suite** validation adapter for custom scorer authoring. Read `scorer-authoring.md`
first; this file covers Steps 6b/7/8 for the AI Testing Center mode.

> **STATUS — not yet wired into a live skill.** This adapter is documented and its runner is
> vendored, but it is **not** offered by `agentforce-observe`. It will be wired into
> `agentforce-test` once the NGT / AI Testing Center API supports **open scorers**.
>
> **Hard blocker today:** OpenEnded scorers (any `lightning_type` — the default for new authoring)
> are NOT supported by the Testing Center server-side. A run FAILS with *"One or more evaluation
> columns failed or were skipped."* Only legacy `scorerMultilabel` (Text) scorers, and Number
> scorers with `semantic_type: Measurement` (`scorerMeasurement`), run cleanly. So for any freshly
> authored (OpenEnded) scorer, `scorer-authoring.md` Step 6 silently steers to **Live sessions**
> (`scorer-validate-datacloud.md`) instead.
>
> This file exists so the mechanics are ready to lift into `agentforce-test` without rediscovery.

Assumes `$SCORER_DIR` and `$PY` are resolved (see `scorer-authoring.md`).

---

## Step 6b — Test-suite intake

Ask where test utterances come from:
```
1. Draft — I'll generate 5–10 candidate utterances aligned with the scorer's goal, propose an expected value per utterance, and you confirm/tweak.
2. File — an absolute path to an existing AiTestingDefinition XML, or a JSON matching build-test-definition.py's input schema.
3. Paste — a newline-separated list of utterances; I'll draft expected values, then we confirm.
```

Per utterance, propose an `expected_value` of the scorer's type (Text → one of `allowed_labels`;
Number → stringified int in range; OpenEnded → a sample output matching the subtype). Paste the
table for confirmation ("Ship as-is (1) or tweak (2)?"):

```
Test definition: {name}_Tests
Subject (agent): {agent_api_name}
Custom scorer:   {scorer_name}
Includes default quality scorers: coherence, conciseness, factuality, completeness

# | Utterance                     | Expected
1 | <utterance text>              | <value>
```

Deploy the scorer first (the test definition references it by name — see `scorer-validate-datacloud.md`
Step 7.1 for the `deploy-scorer` command). Then write the test input JSON to
`/tmp/scorer-tests/<scorer>/input.json`:

```json
{
  "test_def_name": "{scorer}_Tests",
  "test_def_description": "Test suite for {scorer}",
  "subject_name": "(filled in by the runner from $AGENT_NAME)",
  "scorer_name": "{scorer}",
  "include_default_scorers": true,
  "test_cases": [ {"utterance": "…", "expected_value": "<value or null>"} ]
}
```

## Step 7 — Run the bundled test runner

The test-suite path runs through the vendored bash runner, **not** `src/cli`. It deploys an
`AiTestingDefinition` (Metadata SOAP API), runs it via `POST /einstein/ai-testing/runs`, polls,
fetches results, and writes `manifest.json` (`kind: test-suite`) + `summary.json` under
`$SCORER_DIR/runs/<scorer>/test-<ts>-<sha>/`. Don't reimplement any of it.

```bash
ORG="<org>" \
SCORER_NAME="<scorer>" \
AGENT_NAME="<agent_api_name>" \
INPUT_JSON="/tmp/scorer-tests/<scorer>/input.json" \
bash "$SCORER_DIR/.claude/skills/scorer-create/scripts/ngt-test-runner.sh" run \
  2>&1 | tee /tmp/scorer-tests/<scorer>/run.log
```

Required env: `ORG`, `SCORER_NAME`, `AGENT_NAME`, `INPUT_JSON`. Optional: `TEST_DEF_NAME`
(default `<SCORER_NAME>_Tests`), `API_VERSION` (default 66.0, must be 66.0+), `POLL_INTERVAL` (15),
`MAX_POLL_ATTEMPTS` (40), `OUTPUT_DIR` (defaults to `$SCORER_DIR/runs/<scorer>/test-<ts>-<sha>/`).

> The runner computes its own repo root as `$SKILL_DIR/../../..`, which resolves to `$SCORER_DIR` —
> keeping its `runs/` output in sync with the Python `run_store.RUNS_DIR` so the UI Tests tab finds
> snapshots. This depends on the vendored `.claude/skills/scorer-create/scripts/` layout being
> preserved relative to `shared/scorer/`.

If the deploy step fails, show the tail of the SOAP response and ask before retrying.

Capture the snapshot id:
```bash
ls -t "$SCORER_DIR/runs/<scorer>/" | grep '^test-' | head -n 1   # → latest test run_id
```
Nudge: *"Test run saved. Results in the UI: http://localhost:8765/#scorer=<name>&testrun=<test_run_id>&tab=tests"*

## Step 8 — Present results

Read `$SCORER_DIR/runs/<scorer>/<test_run_id>/summary.json` and render:

| # | Utterance (truncated) | Expected | Custom scorer | Pass? | Reason |
|---|---|---|---|---|---|
| 1 | "show me my orders" | Compliant | Compliant | ✓ | matched policy on order disclosure |

Pull `Custom scorer` (label/value/raw_value) and `Pass?` (`PASS`→✓, `FAIL`→✗, else —) from the
first scorer in `scorers[]` (the user's custom scorer comes first); `Reason` = its
`reasoning`/`explanation`. Truncate utterances over 60 chars with `…`. Then a one-line default-scorer
average, e.g. `Quality avg: coherence 91, conciseness 88, factuality 95, completeness 86`.

## Step 9 iteration — compare

Drop two Tests-tab links side by side:
```bash
ls -t "$SCORER_DIR/runs/<scorer>/" | grep '^test-' | head -n 2   # prev, new
```
> "Previous: http://localhost:8765/#scorer=<name>&testrun=<prev>&tab=tests
> Latest:   http://localhost:8765/#scorer=<name>&testrun=<new>&tab=tests"

## Step 10 addendum

Mention the deployed test definition:
> "AiTestingDefinition `{test_def_name}` is deployed in `{org}`. Re-run any time with
> `bash $SCORER_DIR/.claude/skills/scorer-create/scripts/ngt-test-runner.sh run` (same env vars)."

---

## Integration TODO (for `agentforce-test`)

When NGT supports open scorers, wire this adapter into `agentforce-test`:
1. Add a scorer-creation intent that references `scorer-authoring.md` + this file.
2. Remove the "silently steer to Live sessions" guard in `scorer-authoring.md` Step 6 for the
   subtypes NGT then supports.
3. Verify `ngt-test-runner.sh`'s `API_VERSION` default still targets a version with open-scorer support.
