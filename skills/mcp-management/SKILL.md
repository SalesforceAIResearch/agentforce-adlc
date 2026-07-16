---
name: mcp-management
description: "Register, configure, and manage MCP (Model Context Protocol) servers using the Salesforce CLI. TRIGGER when: user wants to register/create/add an MCP server, whitelist/approve/activate MCP tools, list/view MCP servers, update MCP server configuration, delete/remove MCP servers, fetch MCP server assets, or manage MCP authentication. DO NOT TRIGGER when: general MCP development, MCP server implementation, or MCP protocol design."
license: Apache-2.0
compatibility: "Requires sf CLI with agent mcp plugin installed"
metadata:
  version: "0.1.0"
  last_updated: "2026-07-07"
---

# MCP Management Skill

## What This Skill Is For

This skill helps you register and manage Model Context Protocol (MCP) servers in the Salesforce API Catalog using the `sf agent mcp` CLI commands. It handles:

- **Server registration** — Create new MCP server connections
- **Server management** — List, view, update, and delete servers
- **Asset whitelisting** — Interactive tool approval with detailed metadata review
- **Authentication** — Configure OAuth or no-auth connections

## Core Principles

1. **Always `--json`** — Include `--json` on every `sf agent mcp` command to get structured output
2. **Verify target org** — Before any operation, confirm a target org is set with `sf config get target-org --json`
3. **Interactive approval** — When whitelisting tools, display metadata for each tool individually and wait for user approval
4. **Security first** — For OAuth servers, handle client secrets securely (stdin piping) and warn about credential exposure

## Task Workflows

### 1. Register a New MCP Server

When the user wants to register/create/add an MCP server:

#### Required Information

Gather from the user (ask if not provided):
- **Server name** (`-n, --name`) — Unique identifier
- **Server URL** (`--server-url`) — Endpoint URL
- **Target org** (`-o, --target-org`) — Org alias or username
- **Label** (optional, `--label`) — Human-readable display name
- **Description** (optional, `--description`) — Server purpose
- **Authentication type** (`--auth-type`) — `NO_AUTH` (default) or `OAUTH`

If `--auth-type OAUTH`, also gather:
- **Identity provider** (`--identity-provider`)
- **Client ID** (`--client-id`)
- **Client secret** (`--client-secret`) — Handle securely via stdin
- **Scope** (`--scope`)

#### Execution Steps

1. **Verify target org is set**
   ```bash
   sf config get target-org --json
   ```
   If no target org, ask user to set one with `sf config set target-org <alias>`

2. **Gather required information** — Ask for any missing required fields

3. **Create the server**
   
   **NO_AUTH example:**
   ```bash
   sf agent mcp create -n MyServer --server-url https://mcp.example.com/mcp -o myOrg --json
   ```

   **OAUTH example (secure client secret handling):**
   ```bash
   echo "secret-value" | sf agent mcp create -n MyServer --server-url https://mcp.example.com/mcp --auth-type OAUTH --identity-provider MyIdp --client-id abc123 --client-secret - --scope "read write" -o myOrg --json
   ```

4. **Extract server ID** — Parse the JSON response and extract the `id` field (format: `0XSxx0000000001`). This ID is required for all subsequent operations.

5. **Display confirmation** — Show the user:
   - Server name
   - Server ID
   - Server URL
   - Connection status

6. **Offer next steps**
   - "Would you like to fetch and whitelist tools from this server now?"
   - If yes, proceed to **Fetch and Whitelist Assets** workflow

### 2. List MCP Servers

When the user wants to see all registered MCP servers:

#### Execution Steps

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **List servers**
   ```bash
   sf agent mcp list -o myOrg --json
   ```

   **Optional filters:**
   - By status: `--status ACTIVE` or `--status DISCONNECTED`
   - By type: `--type EXTERNAL`
   - By label: `--label "My Server"`

3. **Display results** — Show a table or list with:
   - Server name
   - Server ID
   - Status (ACTIVE/DISCONNECTED)
   - Server URL
   - Label

4. **Offer actions** — Ask if the user wants to:
   - Get details on a specific server
   - Fetch assets from a server
   - Update or delete a server

### 3. Get Server Details

When the user wants details on a specific server:

#### Required Information

- **Server ID** (`-i, --mcp-server-id`)
- **Target org** (`-o, --target-org`)

#### Execution Steps

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Get server details**
   ```bash
   sf agent mcp get -i 0XSxx0000000001 -o myOrg --json
   ```

3. **Display details** — Show:
   - Name, label, description
   - Server URL
   - Status
   - Authentication type
   - Created/modified timestamps

### 4. Fetch and Whitelist Assets (Interactive Tool Approval)

This is the **core whitelisting workflow** with interactive tool-by-tool approval.

#### Required Information

- **Server ID** (`-i, --mcp-server-id`)
- **Target org** (`-o, --target-org`)

#### Execution Steps

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Fetch live assets from the server**
   ```bash
   sf agent mcp fetch -i 0XSxx0000000001 -o myOrg --json
   ```

3. **Parse the response** — Extract the list of assets (tools, prompts, resources). Each asset includes:
   - `id` — Asset identifier
   - `name` — Asset name (e.g., `McpTool__add`)
   - `kind` — Asset type (`MCP_TOOL`, `MCP_PROMPT`, `MCP_RESOURCE`)
   - `active` — Current activation status (boolean)
   - `description` — Tool description
   - `inputSchema` — JSON schema for tool inputs
   - `outputSchema` — JSON schema for tool outputs (if present)
   - `annotations` — Additional metadata (if present)

4. **Interactive tool review** — For EACH tool in the list:
   
   a. **Display tool metadata clearly:**
   ```
   Tool: <name>
   Kind: <kind>
   Description: <description>
   
   Input Schema:
   <formatted JSON inputSchema>
   
   Output Schema:
   <formatted JSON outputSchema> (or "Not specified")
   
   Annotations:
   <formatted JSON annotations> (or "None")
   
   Current Status: <active ? "ACTIVE" : "INACTIVE">
   ```

   b. **Ask for approval:**
   ```
   Do you want to ACTIVATE this tool? (yes/no/skip)
   - yes: Add to allowlist
   - no: Exclude from allowlist (deactivate if currently active)
   - skip: Keep current status unchanged
   ```

   c. **Record the user's choice** — Build an array of approved assets

5. **Build the asset allowlist** — Create a JSON payload with the approved assets:
   ```json
   {
     "assets": [
       {
         "name": "McpTool__add",
         "active": true
       },
       {
         "name": "McpTool__subtract",
         "active": false
       }
     ]
   }
   ```

6. **Write the allowlist to a temp file**
   ```bash
   echo '<json payload>' > /tmp/mcp-assets.json
   ```

7. **Replace the server's asset allowlist**
   ```bash
   sf agent mcp asset replace -i 0XSxx0000000001 --assets-file /tmp/mcp-assets.json -o myOrg --json
   ```

8. **Confirm results** — Display summary:
   ```
   Asset Allowlist Updated:
   - Activated: <count> tools
   - Deactivated: <count> tools
   - Unchanged: <count> tools
   ```

9. **Clean up temp file**
   ```bash
   rm /tmp/mcp-assets.json
   ```

#### Notes on Asset Replacement

- **Full replacement semantics** — `sf agent mcp asset replace` is a FULL replacement, not a merge. Assets not in the payload are removed/deactivated.
- **Always include the full desired state** — If a tool should remain active, include it in the payload with `"active": true`
- **Read current state first** — Use `sf agent mcp fetch` or `sf agent mcp asset list` to see current assets before replacement

### 5. List Assets for a Server

When the user wants to see the current asset allowlist:

#### Execution Steps

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **List assets**
   ```bash
   sf agent mcp asset list -i 0XSxx0000000001 -o myOrg --json
   ```

3. **Display results** — Show each asset with:
   - Name
   - Kind (MCP_TOOL, MCP_PROMPT, MCP_RESOURCE)
   - Active status
   - Available as agent action

### 6. Update MCP Server

When the user wants to modify server configuration:

#### Required Information

- **Server ID** (`-i, --mcp-server-id`)
- **Target org** (`-o, --target-org`)
- At least one field to update

#### Updatable Fields

- `--label` — New display label
- `--description` — New description
- `--server-url` — New endpoint URL
- `--auth-type` — Change authentication (requires full OAuth params if switching to OAUTH)

#### Execution Steps

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Gather update fields** — Ask which fields to change

3. **Update the server**
   ```bash
   sf agent mcp update -i 0XSxx0000000001 --label "New Label" --description "Updated description" -o myOrg --json
   ```

   **Switching to OAuth:**
   ```bash
   echo "secret" | sf agent mcp update -i 0XSxx0000000001 --auth-type OAUTH --identity-provider MyIdp --client-id abc --client-secret - --scope "read write" -o myOrg --json
   ```

4. **Confirm results** — Display updated server details

### 7. Delete MCP Server

When the user wants to remove a server registration:

#### Required Information

- **Server ID** (`-i, --mcp-server-id`)
- **Target org** (`-o, --target-org`)

#### Execution Steps

1. **Verify target org**
   ```bash
   sf config get target-org --json
   ```

2. **Get server details first** — Show what will be deleted
   ```bash
   sf agent mcp get -i 0XSxx0000000001 -o myOrg --json
   ```

3. **Confirm deletion** — Ask user:
   ```
   Are you sure you want to delete this MCP server?
   - Name: <name>
   - URL: <url>
   - This action is PERMANENT and cannot be undone.
   
   Confirm deletion? (yes/no)
   ```

4. **Delete the server**
   ```bash
   sf agent mcp delete -i 0XSxx0000000001 -o myOrg --no-prompt --json
   ```

5. **Confirm deletion** — Display success message

## Error Handling

### Common Errors

1. **No target org set**
   - Error: `No default org found`
   - Solution: Ask user to run `sf config set target-org <alias>`

2. **Server not found**
   - Error: `MCP server not found`
   - Solution: Verify server ID with `sf agent mcp list`

3. **Connection failure**
   - Error: `Failed to connect to MCP server`
   - Solution: Check server URL, network connectivity, and authentication

4. **Invalid authentication**
   - Error: `OAuth authentication failed`
   - Solution: Verify identity provider, client ID, client secret, and scope

5. **Asset not found**
   - Error: `Asset not found on server`
   - Solution: Fetch fresh assets with `sf agent mcp fetch`

## Security Best Practices

1. **Client secret handling**
   - NEVER pass `--client-secret` directly on the command line (visible in shell history)
   - ALWAYS use stdin piping: `echo "secret" | sf agent mcp create ... --client-secret -`
   - Or use a secure file: `cat secret.txt | sf agent mcp create ... --client-secret -`

2. **Credential storage**
   - Warn users that credentials are stored in the Salesforce org
   - Recommend using org-specific service accounts, not personal credentials

3. **Server URL validation**
   - Verify HTTPS for production servers
   - Warn if using HTTP for non-local development

4. **Asset review**
   - Always review tool descriptions and schemas before activation
   - Watch for overly broad permissions (e.g., database access, file system access)
   - Flag tools with destructive capabilities (delete, update, execute)

## Windows Compatibility

- **Python command:** Use `python` instead of `python3` on Windows
- **Temp files:** Use `%TEMP%\mcp-assets.json` (cmd) or `$env:TEMP\mcp-assets.json` (PowerShell) instead of `/tmp/`
- **Stdin piping:** PowerShell example: `"secret" | sf agent mcp create ... --client-secret -`

## Examples

### Complete Registration + Whitelisting Flow

```bash
# 1. Verify target org
sf config get target-org --json

# 2. Create MCP server (no auth)
sf agent mcp create -n TestServer --server-url https://mcp.example.com/mcp -o myOrg --json
# Extract server ID from response: 0XSxx0000000001

# 3. Fetch available tools
sf agent mcp fetch -i 0XSxx0000000001 -o myOrg --json

# 4. Review each tool interactively (handled by Claude)

# 5. Build allowlist and write to file
echo '{"assets":[{"name":"McpTool__add","active":true}]}' > /tmp/mcp-assets.json

# 6. Replace asset allowlist
sf agent mcp asset replace -i 0XSxx0000000001 --assets-file /tmp/mcp-assets.json -o myOrg --json

# 7. Verify
sf agent mcp asset list -i 0XSxx0000000001 -o myOrg --json
```

### OAuth Server Registration

```bash
# Store client secret securely
echo "my-oauth-secret" > /tmp/client-secret.txt

# Create server with OAuth
cat /tmp/client-secret.txt | sf agent mcp create \
  -n OAuthServer \
  --server-url https://secure.mcp.example.com/mcp \
  --auth-type OAUTH \
  --identity-provider MyIdentityProvider \
  --client-id abc123xyz \
  --client-secret - \
  --scope "read write execute" \
  -o myOrg \
  --json

# Clean up
rm /tmp/client-secret.txt
```

## Quick Reference

| Command | Purpose |
|---------|---------|
| `sf agent mcp create` | Register a new MCP server |
| `sf agent mcp list` | List all registered servers |
| `sf agent mcp get` | Get details on a specific server |
| `sf agent mcp update` | Update server configuration |
| `sf agent mcp delete` | Remove server registration |
| `sf agent mcp fetch` | Fetch live assets from server |
| `sf agent mcp asset list` | List current asset allowlist |
| `sf agent mcp asset replace` | Update asset allowlist |

## Troubleshooting

### Server shows DISCONNECTED status

1. Check server URL is accessible: `curl -v <server-url>`
2. Verify authentication credentials (if OAuth)
3. Check server logs for connection errors
4. Try updating the server URL: `sf agent mcp update -i <id> --server-url <new-url>`

### Tools not appearing after whitelisting

1. Verify asset activation: `sf agent mcp asset list -i <id>`
2. Check if tools are marked as `active: true`
3. Fetch fresh assets: `sf agent mcp fetch -i <id>`
4. Verify server is ACTIVE: `sf agent mcp get -i <id>`

### "Command not found: agent mcp"

- The `sf agent mcp` plugin may not be installed
- Check SF CLI version: `sf version`
- Update SF CLI: `sf update`
- Verify plugin availability: `sf plugins`

## Maintaining This Skill

### Updating Command Reference

If the SF CLI `sf agent mcp` commands change:

1. **Check for new commands:**
   ```bash
   sf help agent mcp
   ```

2. **Update command help:**
   ```bash
   sf help agent mcp <command> > /tmp/mcp-command-help.txt
   ```

3. **Update `references.md`** with new parameters, response structures, or examples

4. **Update `SKILL.md` workflows** if command behavior changes

5. **Test the skill** with the new commands to ensure workflows still work

### Adding New Workflows

To add a new workflow to this skill:

1. **Add workflow section to `SKILL.md`** under "Task Workflows"
2. **Add detailed command reference to `references.md`**
3. **Add working example to `examples.md`**
4. **Update trigger keywords** in the frontmatter `description` field

## Future Enhancements

Planned features (not yet implemented):

- Bulk asset activation/deactivation
- Asset filtering by kind (tools only, prompts only, etc.)
- Asset search by name or description
- Server health check and monitoring
- Batch server operations
- Import/export server configurations
- Dry-run mode for asset changes
- Asset change history and rollback
