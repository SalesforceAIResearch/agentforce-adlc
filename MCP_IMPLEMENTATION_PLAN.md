# MCP Server Registration & Tool Whitelisting - Implementation Plan

## Overview

This document outlines the implementation plan for adding external MCP (Model Context Protocol) server registration and tool whitelisting capabilities to the Agentforce ADLC Claude Code plugin.

## Objective

Enable Claude Code users to:
1. Register external MCP servers by URL with authentication configuration
2. Discover tools/prompts/resources from external MCP servers
3. Review and whitelist tools with full metadata visibility before approval
4. Manage server lifecycle (update, delete, re-sync)
5. Monitor connection status and update credentials

## API Foundation

The implementation leverages the **API Catalog - MCP Servers Connect API** documented at:
https://docs.google.com/document/d/1jupWmQp6LzU9_325t-7RKdYxX71xlkpzmPv4JFX5MxE/edit?tab=t.0

### Key API Endpoints

#### Server Operations
- `POST /api-catalog/mcp-servers` - Create external server
- `GET /api-catalog/mcp-servers` - List servers
- `GET /api-catalog/mcp-servers/{id}` - Get server details
- `PUT /api-catalog/mcp-servers/{id}` - Update server
- `DELETE /api-catalog/mcp-servers/{id}` - Delete server

#### Asset Management
- `GET /api-catalog/mcp-servers/{id}/assets` - List whitelisted assets
- `PUT /api-catalog/mcp-servers/{id}/assets` - Replace asset whitelist (atomic)
- `PUT /api-catalog/mcp-servers/{id}/assets/{assetId}` - Update single asset
- `DELETE /api-catalog/mcp-servers/{id}/assets/{assetId}` - Remove asset

#### External Server Operations
- `POST /api-catalog/mcp-servers/{id}/fetch` - Fetch tools from remote server (stateless)
- `GET /api-catalog/mcp-servers/{id}/connections` - List connections
- `PUT /api-catalog/mcp-servers/{id}/connections/{connectionId}` - Update connection

### External MCP Server Characteristics

**EXTERNAL** - Externally hosted MCP servers registered by URL
- Requires: `serverUrl`, `auth` (OAuth/JWT/NO_AUTH)
- Auto-fetches tools on creation
- No `active` flag (live when connection valid)
- Stateless re-sync via `/fetch`
- Connection status monitoring

## Implementation Structure

### New Skill: `/managing-mcp-servers`

```
skills/managing-mcp-servers/
├── SKILL.md                              # Skill definition and task router
├── assets/
│   ├── external-server-config.json       # External server registration template
│   └── tool-approval-checklist.md        # Guide for evaluating tools
└── references/
    ├── connect-api-reference.md          # Complete API endpoint documentation
    ├── external-server-workflow.md       # External server registration flow
    ├── tool-metadata-schema.md           # Tool metadata structure for approval
    └── mcp-security-considerations.md    # Security best practices
```

### Extended Shared Library

```python
# shared/sf-cli/sf_cli.py - New methods for SfAgentCli class

def list_mcp_servers(self, label: str | None = None) -> CliResult
def create_mcp_server(self, server_config: dict[str, Any]) -> CliResult
def get_mcp_server(self, server_id: str) -> CliResult
def update_mcp_server(self, server_id: str, updates: dict[str, Any]) -> CliResult
def delete_mcp_server(self, server_id: str) -> CliResult
def fetch_external_server(self, server_id: str) -> CliResult
def list_server_assets(self, server_id: str, kind: str | None = None) -> CliResult
def update_server_assets(self, server_id: str, assets: list[dict[str, Any]]) -> CliResult
def list_connections(self, server_id: str) -> CliResult
def update_connection(self, server_id: str, connection_id: str, updates: dict[str, Any]) -> CliResult
```

### New Helper Script

```python
# scripts/mcp_tool_whitelist.py
# Interactive tool approval workflow with rich metadata display
```

## Workflows

### External MCP Server Registration

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Idempotency Check                                       │
│ GET /api-catalog/mcp-servers?label={label}&type=EXTERNAL        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Register Server                                         │
│ POST /api-catalog/mcp-servers                                   │
│ {                                                               │
│   "type": "EXTERNAL",                                          │
│   "name": "developer_name",                                    │
│   "label": "Display Name",                                     │
│   "serverUrl": "https://mcp.example.com/sse",                 │
│   "auth": {                                                    │
│     "authType": "OAUTH",                                       │
│     "identityProvider": "GitHub_IDP",                          │
│     "clientId": "...",                                         │
│     "clientSecret": "...",                                     │
│     "scope": "read:org"                                        │
│   }                                                            │
│ }                                                              │
│                                                                │
│ → Response includes server object + discovered assets array    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Present Tools to User                                   │
│ Display each asset with:                                        │
│ - Tool name, description                                        │
│ - Input/output parameters                                       │
│ - Annotations (permissions, risks)                              │
│ - storedInCore flag (previously whitelisted?)                   │
│                                                                 │
│ USER APPROVAL REQUIRED FOR EACH TOOL                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Whitelist Approved Tools                                │
│ PUT /api-catalog/mcp-servers/{id}/assets                        │
│ {                                                               │
│   "assets": [                                                   │
│     {                                                           │
│       "operationId": "tool_1_id",                              │
│       "name": "Custom Name",                                   │
│       "active": true,                                          │
│       "annotations": {...}                                     │
│     }                                                          │
│   ]                                                            │
│ }                                                              │
│                                                                │
│ → Replace semantics: this becomes the complete asset set        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Verify Connection                                       │
│ GET /api-catalog/mcp-servers/{id}/connections                   │
│ → Check connection status and configuration                     │
└─────────────────────────────────────────────────────────────────┘
```

### Re-Sync External Server

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Fetch Current Remote State                              │
│ POST /api-catalog/mcp-servers/{id}/fetch                        │
│ → Stateless call, returns merged view                           │
│ → storedInCore: true = previously whitelisted                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Review Changes                                          │
│ Compare fetched tools with current whitelist:                   │
│ - NEW: storedInCore = false                                     │
│ - EXISTING: storedInCore = true                                 │
│ - REMOVED: in current whitelist but not in fetch response       │
│                                                                 │
│ Present delta to user for approval                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Update Whitelist                                        │
│ PUT /api-catalog/mcp-servers/{id}/assets                        │
│ → Persist approved changes                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Tool Approval UX

### Display Format

For each tool discovered, present:

```
─────────────────────────────────────────────────────────────────
Tool: create_github_issue
Kind: MCP_TOOL
Status: NEW (not yet whitelisted) | WHITELISTED | MODIFIED
─────────────────────────────────────────────────────────────────
Description:
  Creates a new GitHub issue in the specified repository with
  title, body, labels, and assignees.

Input Parameters:
  • repository (required, string) - Owner/repo format
  • title (required, string) - Issue title
  • body (optional, string) - Issue description (Markdown)
  • labels (optional, array[string]) - Label names
  • assignees (optional, array[string]) - GitHub usernames

Output:
  • issueNumber (integer) - Created issue number
  • issueUrl (string) - Direct URL to the issue

Annotations:
  • permission_required: write:issues
  • rate_limit: 5000/hour
  • scope: Creates public-facing content

Approve this tool? [y/n]:
─────────────────────────────────────────────────────────────────
```

### Approval Checklist

Guide users through evaluation:

1. **Purpose clarity** - Is the tool's function clearly described?
2. **Input validation** - Are required vs. optional params clear?
3. **Output expectations** - Do you understand what data returns?
4. **Permission scope** - What access does this tool require?
5. **Risk assessment** - Can this tool cause destructive actions?
6. **Necessity** - Do you actually need this tool for your use case?

## Security Considerations

### Authentication Secrets

- **NEVER log `clientSecret` or credential fields**
- Use write-only semantics (secrets not returned in GET responses)
- Store credentials in Salesforce Named Credentials when possible
- Use `managed: true` for API Catalog-managed credentials

### Production Org Warnings

Add guardrail hook to warn before:
- Creating external servers in production orgs
- Whitelisting tools with destructive capabilities
- Updating connection credentials

### Permission Requirements

**External Servers:**
- TBD (per API documentation)

### Audit Trail

Document all MCP server operations:
- Server registration (who, when, URL)
- Tool whitelisting decisions (which tools, by whom)
- Connection updates (credential rotation)

## Integration Points

### Skill Triggers

```
/managing-mcp-servers
```

**Trigger keywords:**
- "mcp server", "register mcp", "mcp registration"
- "external server", "external mcp"
- "whitelist tools", "approve tools", "tool approval"
- "api catalog", "connect api"
- "list mcp servers", "update mcp", "delete mcp"

### Reference from Other Skills

`/developing-agentforce` may reference `/managing-mcp-servers` when:
- Agent requires tools from external MCP servers
- Connection configuration needed for agent-MCP integration

### CLI Integration

All operations use `sf api request rest` pattern:

```bash
# List servers
sf api request rest /api-catalog/mcp-servers --json -o OrgAlias

# Create external server
sf api request rest /api-catalog/mcp-servers \
  --method POST \
  --body @server-config.json \
  --json \
  -o OrgAlias

# Fetch tools
sf api request rest /api-catalog/mcp-servers/{id}/fetch \
  --method POST \
  --json \
  -o OrgAlias
```

## Testing Strategy

### Unit Tests

- `tests/test_mcp_cli.py` - Test sf_cli.py MCP methods
- Mock subprocess calls
- Validate JSON serialization/deserialization
- Test error handling for all failure modes

### Integration Tests

- `tests/integration/test_mcp_external_flow.py` - End-to-end external server registration
- Requires sandbox org with API Catalog enabled

### Manual Validation

- Register test external server (mock MCP server)
- Verify tool metadata display correctness
- Test whitelist update atomic semantics
- Confirm connection status reporting

## Documentation Updates

### CLAUDE.md

Add to Skills table:

```markdown
| `/managing-mcp-servers` | "mcp server", "register mcp", "whitelist tools", "api catalog", "external server", "external mcp" | Register external MCP servers, discover tools, whitelist with approval, manage lifecycle |
```

### CHANGELOG.md

Under `[Unreleased]` → `Added`:

```markdown
- New skill `/managing-mcp-servers` for external MCP server registration and tool whitelisting via API Catalog Connect API
  - External MCP server registration with OAuth/JWT/No-Auth authentication
  - Interactive tool approval workflow with full metadata visibility
  - Server lifecycle management (list, update, delete, re-sync)
  - Connection status monitoring and credential updates
- `shared/sf-cli/sf_cli.py` extended with 10 new methods for Connect API operations
- `scripts/mcp_tool_whitelist.py` for interactive tool approval
- `skills/managing-mcp-servers/references/`:
  - `connect-api-reference.md` - Complete API endpoint documentation
  - `external-server-workflow.md` - External server registration flow
  - `tool-metadata-schema.md` - Tool metadata structure
  - `mcp-security-considerations.md` - Security best practices
```

### Version Bump

**Current**: 0.6.1  
**New**: 0.7.0 (MINOR bump - new user-visible capability)

Update:
- `.claude-plugin/plugin.json` → `version: "0.7.0"`
- `.claude-plugin/marketplace.json` → `plugins[0].version: "0.7.0"`

## File Structure

```
agentforce-adlc/
├── skills/
│   └── managing-mcp-servers/         # NEW
│       ├── SKILL.md
│       ├── assets/
│       │   ├── external-server-config.json
│       │   └── tool-approval-checklist.md
│       └── references/
│           ├── connect-api-reference.md
│           ├── external-server-workflow.md
│           ├── tool-metadata-schema.md
│           └── mcp-security-considerations.md
├── shared/sf-cli/
│   └── sf_cli.py                     # EXTENDED (10 new methods)
├── scripts/
│   └── mcp_tool_whitelist.py         # NEW
├── tests/
│   └── test_mcp_cli.py               # NEW
├── CLAUDE.md                         # UPDATED
├── CHANGELOG.md                      # UPDATED
├── .claude-plugin/
│   ├── plugin.json                   # UPDATED (version)
│   └── marketplace.json              # UPDATED (version)
├── MCP_IMPLEMENTATION_PLAN.md        # NEW (this document)
├── MCP_ARCHITECTURE_DIAGRAM.md       # NEW (mermaid diagrams)
├── MCP_API_QUICK_REFERENCE.md        # NEW (quick reference)
└── MCP_IMPLEMENTATION_SUMMARY.md     # NEW (summary)
```

## Implementation Checklist

- [ ] Create skill directory structure
- [ ] Write SKILL.md with task domains
- [ ] Write all reference documentation files
- [ ] Extend shared/sf-cli/sf_cli.py with MCP methods (10 methods)
- [ ] Create scripts/mcp_tool_whitelist.py
- [ ] Create example templates in assets/
- [ ] Write unit tests
- [ ] Update CLAUDE.md
- [ ] Update CHANGELOG.md
- [ ] Update plugin.json and marketplace.json versions
- [ ] Test external server registration flow
- [ ] Test tool whitelisting UX
- [ ] Test re-sync workflow
- [ ] Document security considerations
- [ ] Add guardrail hooks for production warnings

## Future Enhancements

### Phase 2 Considerations

1. **Batch Operations**
   - Bulk server registration from config files
   - Import/export server configurations
   - Template library for common MCP servers

2. **Advanced Filtering**
   - Search tools by capability tags
   - Filter by permission requirements
   - Group by operation kind

3. **Monitoring & Observability**
   - Connection health dashboards
   - Tool usage analytics
   - Error rate tracking per server

4. **CI/CD Integration**
   - Declarative server config (YAML/JSON)
   - Idempotent sync commands
   - GitOps workflow support

## References

- **API Documentation**: [API Catalog - MCP Servers Connect API Design Document](https://docs.google.com/document/d/1jupWmQp6LzU9_325t-7RKdYxX71xlkpzmPv4JFX5MxE/edit?tab=t.0)
- **ADLC Project**: `/Users/dbombinmoreno/Projects/agentforce-adlc`
- **Existing Skills**: `/developing-agentforce`, `/testing-agentforce`, `/observing-agentforce`
- **Shared Library**: `shared/sf-cli/sf_cli.py`
- **Plugin Manifest**: `.claude-plugin/plugin.json`

---

**Status**: Implementation plan complete, ready for execution.
**Created**: 2026-06-02
**Updated**: 2026-06-03 (removed platform server support)
**Author**: Claude Code (via Daniel Bombin)
