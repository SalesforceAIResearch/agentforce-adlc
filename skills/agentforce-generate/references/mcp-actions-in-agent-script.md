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

**Evidence:** "Verified on a dev org, 2026-11-04" means the W-24729191 Phase 0
Run 4 on a Salesforce internal dev org. The log numbers (for example "log 53")
point to that run.

## Terms

| Term | Meaning |
|---|---|
| ESR | `ExternalServiceRegistration`. One per MCP server. `sf agent mcp list` returns its `name` (the ESR DeveloperName) and `id` (the ESR Id, `0Le` prefix) (verified on a dev org, 2026-11-04, logs 28, 34). |
| Named Credential | The credential that the ESR uses. Read it from the ESR Tooling field `NamedCredential` (log 34). It can have a different name from the ESR (logs 41, 42). |
| ESO | `ExternalServiceOperation`. One per tool. DeveloperName is `mcptoolx5fx5f<tool>` in lowercase, with each `_` written as `x5f`. |
| GenAiFunction | The agent action record for one allowlisted tool (`GenAiFunctionDefinition`). Its DeveloperName is the action key. |
| Action key | `"a"` + UUIDv3(MD5(`"<ESR DeveloperName>:McpTool__<tool>"`)), 32 hex digits after the `a`. |

## Prerequisites

1. The MCP server is registered. `sf agent mcp list -o <org> --json` shows it.
2. Each tool you want is allowlisted with `sf agent mcp asset replace`. This
   creates the GenAiFunction for the tool. A deploy of only the ESR metadata
   creates the ESOs but no GenAiFunctions (verified on a dev org, 2026-11-04:
   0 GenAiFunctions after the ESR deploy, logs 43, 45; 2 GenAiFunctions after
   `asset replace`, logs 53, 54).
3. The `sf` CLI is `@salesforce/cli >= 2.142.1` (plugin-agent `>= 1.43.0`) for
   `sf agent mcp`. `mcp_action.py` stops with `need @salesforce/cli >= 2.142.1`
   on an older CLI (`scripts/mcp_action.py:28`, `_check_sf`).

Two `asset replace` traps (verified on a dev org, 2026-11-04):

- The running user needs a permission set that grants principal access to the
  server's External Credential. Without it, `asset replace` fails with
  `Error fetching server definition <Named Credential>` (log 46).
- Each active asset in the payload must include `description`, and the value
  must equal the `sf agent mcp fetch` description after HTML unescape (`&#39;`
  becomes `'`, `&quot;` becomes `"`). `fetch --json` returns the escaped text.
  `asset replace` rejects the escaped text ("description in your request
  doesn't match current remote state", log 52) and rejects a missing
  description ("is missing the description field", log 53). The unescaped text
  succeeds (log 53).

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
   helper output exactly. Whitespace-only lines in the output are part of the
   Builder UI shape.
8. Run `discover.py` to check the MCP identity against the org:

   ```bash
   python3 scripts/discover.py --agent-file path/to/Agent.agent -o <org>
   ```

9. Fix every MCP problem that `discover.py` reports. See
   [discover.py messages](#discoverpy-messages).
10. Validate the bundle:

    ```bash
    sf agent validate authoring-bundle --json --api-name <Agent_API_Name> -o <org>
    ```

11. Publish the bundle:

    ```bash
    sf agent publish authoring-bundle --json --api-name <Agent_API_Name> -o <org>
    ```

12. Get explicit user approval to run live actions, and verify that the org is
    not a production org. Live actions call the real MCP server
    (`SKILL.md:94-95`).
13. Start a preview session with live actions, so that the MCP tool runs.
    Record the session ID that the command returns
    (`agent-validation-and-debugging.md:222-226`). Use `--simulate-actions`
    instead if the user does not approve live actions:

    ```bash
    sf agent preview start --json --authoring-bundle <Agent_API_Name> --use-live-actions -o <org>
    ```

14. Send a message that needs the tool (`deploy-reference.md:146`):

    ```bash
    sf agent preview send --json --authoring-bundle <Agent_API_Name> --session-id <SESSION_ID> -u "<MESSAGE>" -o <org>
    ```

15. End the session (`deploy-reference.md:147`):

    ```bash
    sf agent preview end --json --authoring-bundle <Agent_API_Name> --session-id <SESSION_ID> -o <org>
    ```

The flags in steps 10, 11, 13, and 14 match `@salesforce/cli` 2.146.3 `--help`
(W-24729191 log `sf-agent-flags-2.146.3.log`).

`sf agent validate|publish authoring-bundle` do not check MCP keys or targets.
Always run `discover.py` (step 8) before step 10. See also
[Known Issues](known-issues.md) Issue 22: validate and publish return 404 on
orgs that the public API platform does not know.

## Identity rules

| Field | Rule | Source |
|---|---|---|
| Action key | `"a"` + UUIDv3(MD5(`"<ESR DeveloperName>:McpTool__<tool>"`)). Use the ESR name, not the Named Credential name. | `scripts/mcp_action.py:33` (`action_key`); Core `McpElementDevName.java:64,72`. Verified on a dev org, 2026-11-04: ESR `P0Esr` with Named Credential `P0Nc` gave GenAiFunctions `afa0b58c...` and `aa46908a...`, which equal the ESR-name hash. The Named Credential hashes do not exist (log 54). |
| `source:` | Equal to the action key. | `scripts/mcp_action.py:172` (`render_action_block`); `discover.py:287-289` |
| `target:` | `mcpTool://<Named Credential DeveloperName>/<ESO DeveloperName>` | `scripts/mcp_action.py:41` (`target_uri`); Core `McpTargetParser.java:57-58` |
| GenAiFunction DeveloperName | Equal to the action key. Never rename a GenAiFunction. | The reasoner keeps an MCP tool only when the hash is in the action `developerName` (reasoner `mcp_tool_names.py:212,233-247`). |
| `inputs:` / `outputs:` | One entry for each top-level property of the tool `inputSchema` / `outputSchema`. No `outputs:` section when the tool has no `outputSchema`. | `scripts/mcp_action.py:183`; `tests/test_mcp_action.py` (`test_no_output_schema_omits_outputs`) |
| Reasoning reference | `<key>: @actions.<key>` plus one `with <input> = ...` line for each input. | `scripts/mcp_action.py:190` (`render_reasoning_ref`) |

The helper reads the tool schema from the Tooling field
`ExternalServiceRegistration.Schema` and the label and description from the
GenAiFunction (`scripts/mcp_action.py:125`, `fetch_mcp_tool`). The stored
complex type of an action is not readable headless (verified on a dev org,
2026-11-04, logs 25-27, 39).

CONFIRMED (Core code): the Builder UI also writes no `outputs:` section for a
tool with no `outputSchema`. `AFScriptActionDao.java:292-312` leaves the outputs
list empty, and `ActionConfiguration.ftl:52` (core-266-public) skips `outputs:`
when the list is empty.

HYPOTHESIS: publish accepts an MCP action with no `outputs:` section. This is
not verified (compare [Known Issues](known-issues.md) Issue 15, which is about
`flow://` and `apex://` targets).

## Wrong vs right

A block that an LLM writes by hand differs from the Builder UI block. This
table compares a hand-written Slack MCP agent with the UI block (W-24729191
spec, section 2).

| Element | Hand-written (wrong) | Builder UI and `mcp_action.py` (right) | Effect of the wrong form |
|---|---|---|---|
| Action key | `search_slack` | `a<32 hex>` | HYPOTHESIS: the reasoner drops the tool as "inaccessible" |
| `source:` | missing | `"a<32 hex>"`, same as the key | HYPOTHESIS: publish cannot bind the action to the GenAiFunction |
| `target:` | `mcpTool://<Named Credential>/<ESO>` | same | none |
| `inputs:` / `outputs:` | missing, or rejected by publish when added by hand | from the tool schema | the tool gets no parameters |
| Reasoning `with <input> = ...` | missing | one line for each input | the LLM cannot fill the parameters |
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
with an error for these (`scripts/mcp_action.py:83-102,129`):

| Shape | Example |
|---|---|
| Nested object property | `{"type": "object", "properties": {...}}` |
| `$ref`, `anyOf`, `oneOf`, `allOf` | `{"$ref": "#/$defs/Address"}` |
| Array of objects, or of a type other than `string` / `integer` | `{"type": "array", "items": {"type": "object"}}` |
| `number` or `boolean` property | `{"type": "number"}` |
| `string` with a `format` other than `email`, `uri`, `date-time` | `{"type": "string", "format": "uuid"}` |
| Tool name with characters outside `[A-Za-z0-9_]` | `get-forecast` |

The helper also does not handle namespaced ESRs (`scripts/mcp_action.py`,
`fetch_mcp_tool`: `action_key` is called with no namespace).

For a refused tool, add the action in the Builder UI: open Agentforce Studio,
open the agent, and add the action from Agentforce Assets. Then retrieve the
bundle. A Core Connect API, `POST /connect/genai-mcp/agent-script/actions`, is
in development for this case. It is not released.

## discover.py messages

`discover.py` checks each `mcpTool://` action against the org GenAiFunctions
(`scripts/discover.py:255-290`).

| Message | Meaning | Fix |
|---|---|---|
| `action key must be <hash>` | The action key is not the GenAiFunction DeveloperName. | Run `mcp_action.py` again and paste its block. |
| `source must be <hash>` | `source:` is not the GenAiFunction DeveloperName. | Set `source:` to the key, or paste the helper block. |
| `no GenAiFunction for this MCP tool; allowlist it with sf agent mcp asset replace` | The tool is not allowlisted. | Allowlist the tool. See [Prerequisites](#prerequisites). |
| `ambiguous: <tool> matches GenAiFunctions ...` | Two or more servers have a tool with this name. | Run `mcp_action.py` with the correct `--server`, and use its key. |
| `warning: action_key(<ESR>, <tool>) does not equal <hash>` | The GenAiFunction name is not the hash rule. HYPOTHESIS: someone renamed it, or the ESR is namespaced. | Do not rename GenAiFunctions. Allowlist the tool again. |
