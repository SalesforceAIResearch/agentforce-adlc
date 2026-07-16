# MCP Management Skill

Register and manage Model Context Protocol (MCP) servers using the Salesforce CLI.

## Quick Start

```bash
# Invoke the skill
/mcp-management
```

Or trigger naturally:
- "Register an MCP server"
- "Whitelist MCP tools"
- "List my MCP servers"
- "Update MCP server configuration"

## What It Does

- **Server Registration** — Create new MCP server connections with NO_AUTH or OAUTH
- **Interactive Whitelisting** — Review and approve tools one-by-one with full metadata
- **Server Management** — List, view, update, and delete MCP servers
- **Asset Management** — Fetch live assets and manage allowlists

## Key Features

### Interactive Tool Approval

For each tool discovered on an MCP server, the skill displays:
- Tool name and description
- Input schema (parameters, types, required fields)
- Output schema (return value structure)
- Annotations (rate limits, categories, flags)
- Current activation status

You review and approve each tool individually before whitelisting.

### Secure Authentication

- OAuth credentials handled via stdin (never exposed in shell history)
- Automatic org validation before operations
- Production deployment warnings

### Full Lifecycle Support

```
Create → Fetch → Whitelist → Update → Delete
```

## Prerequisites

- Salesforce CLI with `sf agent mcp` plugin installed
- Target org configured: `sf config set target-org <alias>`

## Common Workflows

### Register a New Server

```
User: Register an MCP server
Claude: I'll help you register an MCP server. I need:
        - Server name
        - Server URL
        - Target org
        - Authentication type (NO_AUTH or OAUTH)
```

### Whitelist Tools

```
User: Whitelist tools from MyServer
Claude: [Fetches tools and displays each with full metadata]
        Tool: McpTool__add
        Description: Add two numbers
        Input Schema: {...}
        
        Do you want to ACTIVATE this tool? (yes/no/skip)
```

### List Servers

```
User: Show me all MCP servers
Claude: [Displays table of servers with status]
```

## Files

- `SKILL.md` — Skill definition and workflow documentation
- `references.md` — Complete command reference and examples
- `README.md` — This file

## Learn More

See [`SKILL.md`](SKILL.md) for detailed workflows and [`references.md`](references.md) for command syntax and examples.
