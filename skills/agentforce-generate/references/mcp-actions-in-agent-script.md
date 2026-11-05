# MCP Tools in Agent Script

Add tools from a registered MCP server to an Agent Script `.agent` file. The
result is the same action block that the Agentforce Builder UI writes. This
reference backs the **Add MCP tools to an agent** step of the **Manage MCP
Servers** task domain in `SKILL.md`.

Use [MCP Server Management](mcp-management-reference.md) first to register the
server and allowlist its tools. This reference starts after that.

**Scope:** third-party (3P) MCP tools with target type `mcpTool`. First-party
(1P) `platformMcpTool` tools are not covered. HYPOTHESIS: the 1P target rule
(`platformMcpTool://<devName>`) also works headless. No 1P tool was tested
headless, and `discover.py` labels its 1P check "1P match rule not verified
against a UI sample".

## Terms

| Term | Meaning |
|---|---|
| ESR | `ExternalServiceRegistration`. One per MCP server. `sf agent mcp list` returns its `name` (the ESR DeveloperName) and `id` (the ESR Id, `0Le` prefix) (verified on a dev org, 2026-11-04). |
| Named Credential | The credential that the ESR uses. Read it from the ESR Tooling field `NamedCredential`. It can have a different name from the ESR (verified on a dev org, 2026-11-04). |
| ESO | `ExternalServiceOperation`. One per tool. DeveloperName is `mcptoolx5fx5f<tool>` in lowercase, with each `_` written as `x5f`. |
| GenAiFunction | The agent action record for one allowlisted tool (`GenAiFunctionDefinition`). Its DeveloperName is the action key. |
| Action key | `"a"` + UUIDv3(MD5(`"<ESR DeveloperName>:McpTool__<tool>"`)), 32 hex digits after the `a`. |

## Prerequisites

1. The MCP server is registered. `sf agent mcp list -o <org> --json` shows it.
2. Each tool you want is allowlisted with `sf agent mcp asset replace`. This
   creates the GenAiFunction for the tool. A deploy of only the ESR metadata
   creates the ESOs but no GenAiFunctions (verified on a dev org, 2026-11-04:
   0 GenAiFunctions after the ESR deploy, 2 GenAiFunctions after
   `asset replace`).
3. The `sf` CLI is `@salesforce/cli >= 2.142.1` (plugin-agent `>= 1.43.0`) for
   `sf agent mcp`. `mcp_action.py` stops with `need @salesforce/cli >= 2.142.1`
   on an older CLI (`scripts/mcp_action.py`, `MIN_SF` and `_check_sf`).

Two `asset replace` traps (verified on a dev org, 2026-11-04):

- The running user needs a permission set that grants principal access to the
  server's External Credential. Without it, `asset replace` fails with
  `Error fetching server definition <Named Credential>`.
- Each active asset in the payload must include `description`, and the value
  must equal the `sf agent mcp fetch` description after HTML unescape (`&#39;`
  becomes `'`, `&quot;` becomes `"`). `fetch --json` returns the escaped text.
  `asset replace` rejects the escaped text ("description in your request
  doesn't match current remote state") and rejects a missing description
  ("is missing the description field"). The unescaped text succeeds.

## Workflow

1. Get the ESR DeveloperName. Run `sf agent mcp list -o <org> --json` and read
   `result.mcpServers[].name` (the ESR DeveloperName) and `id` (the server id).
2. Get the tool names. Run `sf agent mcp asset list -i <server id> -o <org> --json`
   and read each active asset `name`. Remove the `McpTool__` prefix.
3. Render the blocks. Run the helper with one `--tool` for each tool:

   ```bash
   python3 scripts/mcp_action.py -o <org> --server <ESR DeveloperName> --tool <tool> [--tool <tool> ...]
   ```

   Add `--json` to get `key`, `source`, `target`, `actionBlock`, and
   `reasoningReference` for each tool.
4. Paste the `# subagent actions:` output into the subagent `actions:` section.
   The helper indents it for that position (8 spaces).
5. Paste the `# reasoning actions:` output into the same subagent's
   `reasoning:` > `actions:` section (12 spaces).
6. Keep each `with <input> = ...` line. `...` lets the LLM fill the value. To
   bind a value, replace `...` with a variable reference.
7. Do not edit the key, `source`, `target`, `inputs`, or `outputs`. Paste the
   helper output exactly. The output has whitespace-only lines. The helper
   reproduces them from the Builder UI output. The compiler ignores them: the
   local compiler (`@sf-agentscript/agentforce` 2.9.27) gave the same
   diagnostics and index for a Builder UI bundle with and without them
   (verified 2026-11-04).
8. Run `discover.py` to check the MCP identity against the org:

   ```bash
   python3 scripts/discover.py --agent-file path/to/Agent.agent -o <org>
   ```

9. Fix every MCP problem that `discover.py` reports. See
   [discover.py messages](#discoverpy-messages).
10. Compile the agent locally (`SKILL.md` rule 14). Fix every severity-1
    diagnostic and run it again until it is clean:

    ```bash
    node <skill-directory>/scripts/index-agent.mjs <agent-file>
    ```

11. Validate the bundle:

    ```bash
    sf agent validate authoring-bundle --json --api-name <Agent_API_Name> -o <org>
    ```

12. Publish the bundle:

    ```bash
    sf agent publish authoring-bundle --json --api-name <Agent_API_Name> -o <org>
    ```

13. Get explicit user approval to run live actions, and verify that the org is
    not a production org. Live actions call the real MCP server (`SKILL.md`
    rule 3, "Diagnose in proportion to the change").
14. Start a preview session with live actions, so that the MCP tool runs.
    Record the session ID that the command returns
    ([Validation & Debugging](agent-validation-and-debugging.md), section
    "Step 1: Start a Session"). Use `--simulate-actions`
    instead if the user does not approve live actions:

    ```bash
    sf agent preview start --json --authoring-bundle <Agent_API_Name> --use-live-actions -o <org>
    ```

15. Send a message that needs the tool ([Deploy](deploy-reference.md),
    section "Post-Deployment Testing"):

    ```bash
    sf agent preview send --json --authoring-bundle <Agent_API_Name> --session-id <SESSION_ID> -u "<MESSAGE>" -o <org>
    ```

16. End the session ([Deploy](deploy-reference.md), section
    "Post-Deployment Testing"):

    ```bash
    sf agent preview end --json --authoring-bundle <Agent_API_Name> --session-id <SESSION_ID> -o <org>
    ```

The flags in steps 11, 12, 14, and 15 match `sf` 2.146.3 `--help`.

HYPOTHESIS: `sf agent validate|publish authoring-bundle` do not check MCP keys
or targets. The `@salesforce/cli` client code shows no such check. A
server-side compile with a wrong key was not tested. Always run `discover.py`
(step 8) before step 11. See also
[Known Issues](known-issues.md) Issue 22: validate and publish return 404 on
orgs that `api.salesforce.com` does not route.

## Identity rules

| Field | Rule | Source |
|---|---|---|
| Action key | `"a"` + UUIDv3(MD5(`"<ESR DeveloperName>:McpTool__<tool>"`)). Use the ESR name, not the Named Credential name. | `scripts/mcp_action.py` (`action_key`). Dev-org run, 2026-11-04 (UI parity when the two names differ: HYPOTHESIS, the UI samples in hand use the same name for both): ESR `P0Esr` with Named Credential `P0Nc` gave GenAiFunctions `afa0b58c...` and `aa46908a...`, which equal the ESR-name hash. The Named Credential hashes do not exist. |
| `source:` | Equal to the action key. | Builder UI output, 2026-11-04; `scripts/mcp_action.py` (`render_action_block`); `scripts/discover.py` (`_check_mcp_tools`) |
| `target:` | `mcpTool://<Named Credential DeveloperName>/<ESO DeveloperName>` | dev-org run of the helper, 2026-11-04 (ESR `P0Esr`, Named Credential `P0Nc`). UI parity when the two names differ: HYPOTHESIS (the UI samples in hand use the same name for both); `scripts/mcp_action.py` (`target_uri`); `scripts/discover.py` (`_check_mcp_tools`) checks the Named Credential |
| GenAiFunction DeveloperName | Equal to the action key. Never rename a GenAiFunction. | Builder UI output and a dev-org run, 2026-11-04: the UI action key equals the GenAiFunction DeveloperName (the UI samples in hand use the same name for ESR and Named Credential). |
| `inputs:` / `outputs:` | One entry for each top-level property of the tool `inputSchema` / `outputSchema`. No `outputs:` section when the tool has no `outputSchema`. | `scripts/mcp_action.py` (`render_action_block`); `tests/test_mcp_action.py` (`test_no_output_schema_omits_outputs`) |
| Reasoning reference | `<key>: @actions.<key>` plus one `with <input> = ...` line for each input. | `scripts/mcp_action.py` (`render_reasoning_ref`) |

The helper reads the tool schema from the Tooling field
`ExternalServiceRegistration.Schema` and the label and description from the
GenAiFunction (`scripts/mcp_action.py`, `fetch_mcp_tool`). The stored
complex type of an action is not readable headless (verified on a dev org,
2026-11-04).

The helper writes no `outputs:` section for a tool without an outputSchema
(`scripts/mcp_action.py`, `render_action_block`). HYPOTHESIS: the Builder UI
does the same. No UI sample in hand has a tool without an outputSchema.

HYPOTHESIS: publish accepts an MCP action with no `outputs:` section. This is
not verified (compare [Known Issues](known-issues.md) Issue 15, which is about
`flow://` and `apex://` targets).

## Wrong vs right

A block that an LLM writes by hand differs from the Builder UI block. This
table compares a hand-written Slack MCP agent with the UI block.

| Element | Hand-written (wrong) | Builder UI and `mcp_action.py` (right) | Effect of the wrong form |
|---|---|---|---|
| Action key | `search_slack` | `a<32 hex>` | HYPOTHESIS: the reasoner drops the tool as "inaccessible" |
| `source:` | missing | `"a<32 hex>"`, same as the key | HYPOTHESIS: publish cannot bind the action to the GenAiFunction |
| `target:` | `mcpTool://<Named Credential>/<ESO>` | same | none |
| `inputs:` / `outputs:` | missing, or rejected by publish when added by hand | from the tool schema | HYPOTHESIS: the tool gets no parameters |
| Reasoning `with <input> = ...` | missing | one line for each input | HYPOTHESIS: the LLM cannot fill the parameters |
| GenAiFunction DeveloperName | renamed to `slack_*` | `a<32 hex>`, not changed | breaks the hash identity |

## Example

Helper output for two tools on ESR `P0Esr` with Named Credential `P0Nc`
(verified on a dev org, 2026-11-04). `hello_world` has no `outputSchema`, so
its block has no `outputs:`. This example is abridged: each description is one
line and the whitespace-only lines are removed. Paste the real helper output,
not this example.

```agentscript
    actions:
        afa0b58c66203318397e7846b93be8bcf:
            description: |
                Echo the caller's message with a hello MCP prefix.
            label: "hello_world - P0Esr"
            require_user_confirmation: False
            include_in_progress_indicator: False
            source: "afa0b58c66203318397e7846b93be8bcf"
            target: "mcpTool://P0Nc/mcptoolx5fx5fhellox5fworld"
            inputs:
                "message": string
                    description: |
                    label: "Message"
                    is_required: True
                    is_user_input: False
        aa46908aea1be3324ad16b2dd1a375cd5:
            description: |
                Report basic statistics about a piece of text.
            label: "text_stats - P0Esr"
            require_user_confirmation: False
            include_in_progress_indicator: False
            source: "aa46908aea1be3324ad16b2dd1a375cd5"
            target: "mcpTool://P0Nc/mcptoolx5fx5ftextx5fstats"
            inputs:
                "text": string
                    description: |
                    label: "Text"
                    is_required: True
                    is_user_input: False
            outputs:
                "result": string
                    description: |
                    label: "Result"
                    is_displayable: False
                    filter_from_agent: False
```

Reasoning reference:

```agentscript
        actions:
            afa0b58c66203318397e7846b93be8bcf: @actions.afa0b58c66203318397e7846b93be8bcf
                with message = ...
            aa46908aea1be3324ad16b2dd1a375cd5: @actions.aa46908aea1be3324ad16b2dd1a375cd5
                with text = ...
```

## Shapes the helper refuses

`mcp_action.py` renders only shapes that a Builder UI sample proves. It stops
with an error for these (`scripts/mcp_action.py`, `_param` and `fetch_mcp_tool`):

| Shape | Example |
|---|---|
| Nested object property | `{"type": "object", "properties": {...}}` |
| `$ref`, `anyOf`, `oneOf`, `allOf` | `{"$ref": "#/$defs/Address"}` |
| Array of objects, or of a type other than `string` / `integer` | `{"type": "array", "items": {"type": "object"}}` |
| `number` or `boolean` property | `{"type": "number"}` |
| `string` with a `format` other than `email`, `uri`, `date-time` | `{"type": "string", "format": "uuid"}` |
| Tool name with characters outside `[A-Za-z0-9_]` | `get-forecast` |

For a namespaced ESR, the helper reads the ESR `NamespacePrefix` and adds it
to the hash input (`scripts/mcp_action.py`, `action_key` and
`fetch_mcp_tool`). HYPOTHESIS: the `<namespace>:` prefix rule is correct. No
namespaced ESR was tested. If the org does not return `NamespacePrefix`, the
helper stops, because it cannot tell if the ESR is namespaced.

For a refused tool, add the tool with the Builder UI: open Agentforce Studio,
open the agent, and add the action from Agentforce Assets. Then retrieve the
bundle.

## discover.py messages

`discover.py` checks each `mcpTool://` action against the org GenAiFunctions,
and the target Named Credential against the ESR (`scripts/discover.py`,
`_check_mcp_tools`).

| Message | Meaning | Fix |
|---|---|---|
| `action key must be <hash>` | The action key is not the GenAiFunction DeveloperName. | Run `mcp_action.py` again and paste its block. |
| `source must be <hash>` | `source:` is not the GenAiFunction DeveloperName. | Set `source:` to the key, or paste the helper block. |
| `no GenAiFunction for this MCP tool; allowlist it with sf agent mcp asset replace` | The tool is not allowlisted. | Allowlist the tool. See [Prerequisites](#prerequisites). |
| `target Named Credential must be <NC>` | The target names a Named Credential that the tool's ESR does not use. A common cause is the ESR name in the target. | Run `mcp_action.py` again and paste its block. |
| `ambiguous: <tool> matches GenAiFunctions ...` | Two or more servers have a tool with this name, and the target Named Credential does not select exactly one of them. | Run `mcp_action.py` with the correct `--server`, and use its key. |
| `warning: action_key(<ESR>, <tool>) does not equal <hash>` | The GenAiFunction name is not the hash rule. HYPOTHESIS: someone renamed it, or the ESR is namespaced. | Do not rename GenAiFunctions. Allowlist the tool again. |
| `GenAiFunction query failed: <error>` | `discover.py` could not read the GenAiFunctions. It did not check the action. | Fix the query error (org alias, login, permissions), then run `discover.py` again. |
| `ExternalServiceRegistration query failed: <error>` | `discover.py` could not read the ESR Named Credential. | Fix the query error, then run `discover.py` again. |
| `no ExternalServiceRegistration <ESR>; target Named Credential not checked` | The GenAiFunction label names an ESR that the Tooling query did not return. | Run `sf agent mcp list -o <org> --json` and check the server. |
