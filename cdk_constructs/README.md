# cdk_constructs

Shared, **industry-agnostic** CDK constructs and helpers for the `agentic-cx-*`
apps (airline, bank, telco, and any industry added later). Every construct here
is parameterized — it takes explicit props and imports **no** ambient
`config`. Each per-industry app passes its own values in from its local
`config.py` (and small data modules like `connect/agent_tools.py`).

> Editing a module here changes behavior for **every** industry app that
> imports it. That is the point: one fix, all industries.

## Install (editable)

Each app depends on this package via an editable install. In every app's
`requirements.txt`:

```
-e ../cdk_constructs
```

So from an app directory:

```bash
pip install -e ../cdk_constructs      # or: pip install -r requirements.txt
```

Then import by package path:

```python
from cdk_constructs.webhosting import Webhosting
from cdk_constructs.connect import ContactFlow, OrchestrationAIAgent, AgentToolset
from cdk_constructs.knowledge_bases import S3KnowledgeBase
from cdk_constructs.agent_core import AgentCoreGateway
from cdk_constructs.apis import openapi_spec
```

Layout is a single flat folder (this directory **is** the `cdk_constructs`
package — `pyproject.toml` maps the import name to `.`), so there is no
`cdk_constructs/cdk_constructs` nesting. When you add a new subpackage, list it
under `[tool.setuptools] packages` in `pyproject.toml`.

## Catalog

| Import | Construct / helper | Purpose |
|---|---|---|
| `cdk_constructs.webhosting` | `Webhosting` (+ `Webhosting.from_config`) | Private S3 + CloudFront (OAC) site, optional `/datos` data-viewer. |
| `cdk_constructs.connect` | `ContactFlow`, `ContactFlowModule` | `CfnContactFlow` / `CfnContactFlowModule` from an authored JSON file. |
| | `CustomerManagedView` | `CfnView` from an authored view-content JSON. |
| | `BasicQueueLookup` | Custom resource resolving a queue ARN by name at deploy. |
| | `OrchestrationPrompt` | `CfnAIPrompt` (+ version) from a YAML body. |
| | `OrchestrationAIAgent`, `AgentSurface`, `AgentToolset`, `build_tools`, `rtc_tool_dict` | Self-service / assist AI agent (`CfnAIAgent`) + its per-surface tool surface, driven by an industry `AgentToolset`. |
| | `AiAgentSecurityProfile`, `DEFAULT_AI_AGENT_PERMISSIONS` | Least-privilege Connect security profile for an AI agent. |
| | `QInConnectLexBot` | Amazon Lex V2 Q-in-Connect passthrough bot (`CfnBot`). |
| | `LambdaConnectIntegration` | Associate a Lambda with a Connect instance. |
| | `McpServerIntegration` | Register an AgentCore MCP gateway as a Connect MCP_SERVER integration. |
| `cdk_constructs.knowledge_bases` | `S3KnowledgeBase` | KMS + S3 + AppIntegrations DataIntegration + EXTERNAL Wisdom KB + assistant association. |
| `cdk_constructs.agent_core` | `AgentCoreGateway`, `ApiKeyCredentialProvider` | Bedrock AgentCore MCP gateway (inline OpenAPI target + JWT) and its API-key credential provider. |
| `cdk_constructs.apis` | `openapi_spec` | Load an authored `openapi.yaml` and render the compact JSON inline payload for the gateway target. |

## What stays in each industry app (not here)

The constructs are the reusable *shape*; the **data and business logic** live in
each app:

- `config.py` — the industry's values (names, ARNs, locale, table names, flags).
- `connect/agent_tools.py` — the `AgentToolset` (MCP tool catalog, Retrieve /
  Escalate instructions, chat guide tools, content tag, escalate reasons).
- `databases/databases.py` (`Tables`), `lambdas/project_lambdas.py` (`Lambdas`),
  `apis/<industry>_api.py` — the industry's table schema, function set, and REST
  route map (they compose the shared constructs but encode domain shape).
- `lambdas/code/**` — Lambda handler business logic (incl. `data_viewer`).
- Authored artifacts: `flows/**`, `views/**`, `connect_ai_agents/**` (prompt
  YAMLs), `knowledge_bases/<industry>/**` (KB entries + manifest),
  `apis/openapi/openapi.yaml`, `website/**`.
- `knowledge_bases/tag_kb_content.py` / `associate_guide.py` — post-deploy
  operational scripts (bound to the app's `config` / `shared.ssm_names`).

## Convention for adding a construct

1. Write it here with explicit props (no `import config`); validate inputs and
   expose a small public API. Keep it free of any industry token.
2. If it needs a lot of config wiring, add a `from_config(...)` classmethod that
   reads a documented contract (see `Webhosting.from_config`) so the per-app
   stack stays a thin one-liner.
3. Register the subpackage in `pyproject.toml`, export it from the relevant
   `__init__.py`, and reinstall (`pip install -e ../cdk_constructs`).
