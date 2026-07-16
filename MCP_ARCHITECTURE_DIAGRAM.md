# MCP Server Management Architecture

## System Overview

```mermaid
graph TB
    subgraph "Claude Code Plugin - ADLC"
        Skill["/managing-mcp-servers<br/>Skill"]
        CLI["SfAgentCli<br/>(Extended)"]
        Whitelist["Tool Whitelist<br/>Script"]
        
        Skill -->|calls| CLI
        Skill -->|invokes| Whitelist
    end
    
    subgraph "Salesforce Org"
        ConnectAPI["API Catalog<br/>Connect API<br/>/api-catalog/mcp-servers"]
        MetadataAPI["Metadata API<br/>(Named Credentials)"]
        
        ConnectAPI -->|manages| External["External MCP<br/>Servers"]
    end
    
    subgraph "External Services"
        GitHub["GitHub MCP<br/>Server"]
        Notion["Notion MCP<br/>Server"]
        Custom["Custom MCP<br/>Server"]
    end
    
    CLI -->|REST API| ConnectAPI
    External -->|fetches from| GitHub
    External -->|fetches from| Notion
    External -->|fetches from| Custom
    
    User[User] -->|invokes| Skill
    Whitelist -->|displays| ToolMeta["Tool Metadata<br/>(inputs, outputs,<br/>permissions)"]
    ToolMeta -->|approval| User

    style Skill fill:#e1f5ff
    style CLI fill:#fff4e1
    style Whitelist fill:#fff4e1
    style ConnectAPI fill:#e8f5e9
    style External fill:#fce4ec
```

## Data Flow - External Server Registration

```mermaid
sequenceDiagram
    participant User
    participant Skill as /managing-mcp-servers
    participant CLI as SfAgentCli
    participant API as Connect API
    participant MCP as External MCP Server
    
    User->>Skill: Register GitHub MCP server
    Skill->>CLI: create_mcp_server(config)
    CLI->>API: POST /api-catalog/mcp-servers<br/>{type: EXTERNAL, serverUrl, auth}
    API->>MCP: Fetch tools/prompts/resources
    MCP-->>API: Tool metadata array
    API-->>CLI: {server, assets[]}
    CLI-->>Skill: Registration response
    
    Skill->>User: Display 15 discovered tools
    User->>Skill: Approve 8 tools, reject 7
    
    Skill->>CLI: update_server_assets(approved_list)
    CLI->>API: PUT /api-catalog/mcp-servers/{id}/assets
    API-->>CLI: Updated asset list
    CLI-->>Skill: Whitelist confirmed
    
    Skill->>CLI: list_connections(server_id)
    CLI->>API: GET /api-catalog/mcp-servers/{id}/connections
    API-->>CLI: Connection status
    CLI-->>Skill: Connection healthy
    
    Skill->>User: ✓ Server registered, 8 tools whitelisted
```

## Component Architecture

```mermaid
graph LR
    subgraph "Skill Layer"
        SKILL[SKILL.md<br/>Task Router]
        REF1[connect-api-reference.md]
        REF2[external-server-workflow.md]
        REF3[tool-metadata-schema.md]
        REF4[mcp-security-considerations.md]
        
        SKILL -.reads.-> REF1
        SKILL -.reads.-> REF2
        SKILL -.reads.-> REF3
        SKILL -.reads.-> REF4
    end
    
    subgraph "Shared Library"
        SF_CLI[sf_cli.py]
        Methods["• list_mcp_servers()<br/>• create_mcp_server()<br/>• get_mcp_server()<br/>• update_mcp_server()<br/>• delete_mcp_server()<br/>• fetch_external_server()<br/>• list_server_assets()<br/>• update_server_assets()<br/>• list_connections()<br/>• update_connection()"]
        
        SF_CLI -->|10 new methods| Methods
    end
    
    subgraph "Scripts"
        WHITELIST[mcp_tool_whitelist.py]
        Display["• Display tool metadata<br/>• Collect approvals<br/>• Filter asset list<br/>• Return JSON for PUT"]
        
        WHITELIST -->|interactive| Display
    end
    
    subgraph "Assets"
        T1[external-server-config.json]
        T2[tool-approval-checklist.md]
    end
    
    SKILL -->|calls| SF_CLI
    SKILL -->|invokes| WHITELIST
    SKILL -.examples.-> T1
    SKILL -.guides.-> T2
    
    style SKILL fill:#e1f5ff
    style SF_CLI fill:#fff4e1
    style WHITELIST fill:#fff4e1
```

## Tool Whitelisting State Machine

```mermaid
stateDiagram-v2
    [*] --> ServerRegistered: POST /mcp-servers<br/>(auto-fetch)
    
    ServerRegistered --> ToolsDiscovered: Parse assets[] response
    
    ToolsDiscovered --> UserReview: Display metadata<br/>(name, inputs, outputs,<br/>permissions, annotations)
    
    UserReview --> Approved: User approves tool
    UserReview --> Rejected: User rejects tool
    
    Approved --> Whitelisted: Add to approved_list
    Rejected --> ToolsDiscovered: Continue to next tool
    
    Whitelisted --> AllReviewed: More tools?
    ToolsDiscovered --> AllReviewed: No more tools
    
    AllReviewed --> PersistWhitelist: PUT /assets<br/>(atomic replace)
    
    PersistWhitelist --> [*]: Server ready
    
    note right of UserReview
        For each tool, show:
        • Description
        • Input parameters
        • Output schema
        • Annotations
        • Risk assessment
    end note
    
    note right of PersistWhitelist
        Replace semantics:
        Only tools in the PUT
        body remain whitelisted
    end note
```

## Re-Sync Workflow

```mermaid
flowchart TD
    Start([User triggers re-sync]) --> Fetch[POST /{id}/fetch<br/>Stateless read-through]
    
    Fetch --> Parse[Parse response:<br/>storedInCore flag]
    
    Parse --> Categorize{Categorize tools}
    
    Categorize -->|storedInCore: false| New[NEW TOOLS<br/>Not yet whitelisted]
    Categorize -->|storedInCore: true| Existing[EXISTING TOOLS<br/>Previously whitelisted]
    Categorize -->|In whitelist,<br/>not in fetch| Removed[REMOVED TOOLS<br/>No longer on server]
    
    New --> Display[Display delta to user]
    Existing --> Display
    Removed --> Display
    
    Display --> Review{User reviews changes}
    
    Review -->|Approve new tools| AddNew[Add to approved_list]
    Review -->|Keep existing| Keep[Retain in list]
    Review -->|Remove obsolete| Drop[Remove from list]
    
    AddNew --> Update[PUT /{id}/assets<br/>Atomic replace]
    Keep --> Update
    Drop --> Update
    
    Update --> Done([Re-sync complete])
    
    style New fill:#e8f5e9
    style Existing fill:#fff4e1
    style Removed fill:#fce4ec
    style Update fill:#e1f5ff
```

## Security Architecture

```mermaid
graph TB
    subgraph "Security Layers"
        Input[User Input] --> Validation
        
        subgraph "Pre-Execution Guards"
            Validation[Input Validation]
            OrgCheck[Org Type Check<br/>sandbox vs prod]
            PermCheck[Permission Check<br/>per API documentation]
            
            Validation --> OrgCheck
            OrgCheck --> PermCheck
        end
        
        subgraph "Credential Handling"
            Secret[Secrets<br/>clientSecret, tokens]
            WriteOnly[Write-Only Semantics<br/>Never returned in GET]
            Named[Named Credentials<br/>Salesforce-managed]
            Managed[managed: true flag]
            
            Secret --> WriteOnly
            WriteOnly --> Named
            Named --> Managed
        end
        
        subgraph "Approval Gates"
            ToolReview[Tool Metadata Review]
            RiskAssess[Risk Assessment<br/>destructive ops?]
            UserApproval[Explicit User Approval]
            
            ToolReview --> RiskAssess
            RiskAssess --> UserApproval
        end
        
        subgraph "Audit Trail"
            Log[Operation Logging]
            Who[Who: User ID]
            When[When: Timestamp]
            What[What: Server/Tool changes]
            
            Log --> Who
            Log --> When
            Log --> What
        end
    end
    
    PermCheck --> Execution[Execute API Call]
    Managed --> Execution
    UserApproval --> Execution
    Execution --> Log
    
    style Validation fill:#e8f5e9
    style OrgCheck fill:#fff4e1
    style UserApproval fill:#fce4ec
    style Log fill:#e1f5ff
```

## Integration with Existing Skills

```mermaid
graph LR
    subgraph "Existing Skills"
        Dev[/developing-agentforce]
        Test[/testing-agentforce]
        Obs[/observing-agentforce]
    end
    
    subgraph "New Skill"
        MCP[/managing-mcp-servers]
    end
    
    subgraph "Use Cases"
        UC1[Agent needs external<br/>MCP tools]
        UC2[Configure agent-MCP<br/>connections]
    end
    
    Dev -.may reference.-> MCP
    MCP -.provides tools for.-> Dev
    
    UC1 --> Dev
    UC1 --> MCP
    
    UC2 --> Dev
    UC2 --> MCP
    
    style MCP fill:#e1f5ff
    style Dev fill:#e8f5e9
```

---

**Diagrams rendered**: 7 total
- System overview
- External server registration sequence
- Component architecture
- Tool whitelisting state machine
- Re-sync workflow
- Security architecture
- Integration with existing skills

**Note**: Platform server support removed per project requirements. This architecture focuses solely on external MCP server management.
