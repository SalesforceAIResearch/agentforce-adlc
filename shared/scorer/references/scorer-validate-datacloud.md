# Scorer Validation — Live Data Cloud Sessions

The **live-sessions** validation adapter for custom scorer authoring. Read
`scorer-authoring.md` first (intake, prompt, YAML, refine loop); this file covers Steps 7–8 for
the live-sessions mode. Used by `agentforce-observe`.

This mode scores the last N **real** Data Cloud sessions: the CLI lists sessions via Data Cloud
SQL, builds canonical STDM JSON per session (a Python port of Core's `StdmBuilder`), and invokes
the scorer's prompt template via the Einstein Prompt Template Generations Connect API. No Apex
helper is required — it's pure Data Cloud SQL. (This is a separate STDM path from the observe
skill's `AgentforceOptimizeService` Apex helper; both read the same DMOs but produce different
outputs — rich conversation data vs. canonical prompt-template input.)

Assumes `$SCORER_DIR` and `$PY` are resolved (see `scorer-authoring.md` → "Resolve the CLI
directory and interpreter"). All commands run from `$SCORER_DIR`.

---

## Step 7 — Deploy + validate

**7.0 Set the validation-set size.** After the user picked "Last N live sessions" in Step 6, ask:
*"How many sessions to run validations on? (default 3)"*. This is the **number of sessions to
score** (`--last N`), NOT the live `sampling_rate`.

**7.1 Deploy the full scorer** (template + `AiAgentScorerDefinition`):

```bash
(cd "$SCORER_DIR" && "$PY" -m src.cli deploy-scorer --org <org> \
    --scorer scorer_specs/<name>.yaml \
    --agent-api-name <agent> [--activate] [--sampling-rate 1.0] --force)
```

`--activate` sets `isActive=true` (per the Step 6 sampling question). On first deploy the prompt
template auto-deploys via the 3-step deploy→retrieve→activate flow (~30–60s); subsequent runs hit
the fast path.

**7.2 Score the validation set:**

```bash
(cd "$SCORER_DIR" && "$PY" -m src.cli score-and-fetch --org <org> \
    --scorer scorer_specs/<name>.yaml --agent <agent> --last <N> --json)
```

The `--json` output is an array of `{session_id, label, reason, raw_response_text, raw_value}`
objects. The CLI auto-saves a run snapshot under `$SCORER_DIR/runs/<name>/<timestamp>-<hash>/`.
Capture the newest run id:

```bash
ls -t "$SCORER_DIR/runs/<name>/" | grep -v '^test-' | head -n 1   # → latest run_id
```

Nudge once: *"Run saved. Results in the UI: http://localhost:8765/#scorer=<name>&run=<run_id>&tab=results — click any session to see its full STDM."*

## Step 8 — Present results

Parse the `score-and-fetch --json` array and render:

| # | Session ID | Value | Reason |
|---|---|---|---|
| 1 | abc12345…wxyz | "Customer wanted a refund…" | short reason |

- **Value** column = `raw_value` (populated for every OpenEnded scorer). **Do NOT render a Label
  column** — `label` is always null for OpenEnded scorers (it only carries meaning for legacy
  Text/Number YAMLs, which this flow no longer authors).
- **Session ID** = `short_id` style: first 8 chars + `…` + last 4 chars.
- Also show a **distribution** when the shape is enumerable (`Excellent:2, Poor:1` for label-style
  values; `mean length: 87 chars` for free-text summaries; mean/min/max for numeric).

If this is a later iteration, add a one-line comparison to the previous run (e.g. "Run 1: Poor ×3;
Run 2: Poor ×2, Adequate ×1 — one session flipped Poor → Adequate after adding the 'completeness'
dimension.").

## Step 9 iteration — compare link

After the second (or later) run snapshot, drop the Compare tab (shows YAML diff, rendered XML diff,
per-session value flips, and distribution deltas):

```bash
ls -t "$SCORER_DIR/runs/<name>/" | grep -v '^test-' | head -n 2   # prev, new
```

> "Compare: http://localhost:8765/#scorer=<name>&compare=<prev_run>,<new_run>&tab=compare"

---

## Notes

- **Needs a real org with Data Cloud + STDM DMOs and actual session data.** If `sessions` /
  `score-and-fetch` returns empty, there are no sessions to score — confirm the org and agent, and
  that STDM is active. (Per project memory: some pc-rnd orgs don't persist new-agent UI sessions to
  STDM — use an org with genuine session traffic.)
- **Default dataspace only.** The CLI's STDM SQL hardcodes `ssot__…__dlm` / `__c` prefixes for the
  default data space.
- **Wrong-endpoint trap:** scoring uses `POST /einstein/prompt-templates/{name}/generations` (Connect
  API), NOT `/actions/custom/generatePromptResponse/{name}` — the latter rejects `stdmDetailViewType`
  inputs with a misleading `$.sessionState missing` error. The CLI already uses the correct endpoint.
