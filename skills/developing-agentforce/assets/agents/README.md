# Complete Agent Templates

Templates for building complete, deployable agents.

## Learning Path

| Template | Complexity | Description |
|----------|------------|-------------|
| `hello-world.agent` | Beginner | Minimal viable agent - start here |
| `simple-qa.agent` | Beginner | Single-subagent Q&A agent |
| `template-single-subagent.agent` | Beginner | Copy-and-modify starter with one subagent |
| `multi-subagent.agent` | Intermediate | Multi-subagent routing agent |
| `template-multi-subagent.agent` | Intermediate | Copy-and-modify starter with multiple subagents |
| `hub-and-spoke.agent` | Intermediate | Central-router architecture pattern |
| `verification-gate.agent` | Advanced | Security gate before protected subagents |
| `knowledge-grounded.agent` | Advanced | Agent wired to a Data Library (ADL) |
| `order-service.agent` | Advanced | Complex real-world example |
| `production-faq.agent` | Advanced | Production-ready FAQ with escalation |
| `local-info-agent-annotated.agent` | Reference | Fully annotated example covering all major constructs |

## Quick Start

1. Copy a template to your SFDX project:
   ```bash
   mkdir -p force-app/main/default/aiAuthoringBundles/My_Agent
   cp hello-world.agent force-app/main/default/aiAuthoringBundles/My_Agent/My_Agent.agent
   cp ../bundle-meta.xml force-app/main/default/aiAuthoringBundles/My_Agent/My_Agent.bundle-meta.xml
   ```

2. Validate and deploy:
   ```bash
   sf agent validate authoring-bundle --json --api-name My_Agent --target-org your-org
   sf agent publish authoring-bundle --json --api-name My_Agent --target-org your-org
   ```

## Required Blocks

Every agent must have these blocks **in this order**:

| Block | Purpose |
|-------|---------|
| `system:` | Agent personality and default messages |
| `config:` | Deployment metadata (agent_name, label, etc.) |
| `variables:` | Data connections and state storage |
| `language:` | Locale configuration |
| `start_agent` | Entry point subagent (exactly one required) |

## Next Steps

- [patterns/](../patterns/) - Advanced patterns for complex behaviors
