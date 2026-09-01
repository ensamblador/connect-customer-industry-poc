# agentic-cx-telco

> 📚 **Dónde está cada cosa**
>
> | Necesitas | Ve a |
> |---|---|
> | Visión general del PoC, arquitectura de referencia, desafíos que resuelve | [`../README.md`](../README.md) · [English](../README-en.md) |
> | Cómo desplegar: prerrequisitos, orden de fases, scripts y pasos manuales de consola | [`../instructions.md`](../instructions.md) · [English](../instructions-en.md) |
> | Cómo demostrarlo: preguntas exactas, qué esperar, checklist | [`DEMO-WALKTHROUGH.md`](./DEMO-WALKTHROUGH.md) · [English](./DEMO-WALKTHROUGH-en.md) |
> | **Detalle interno de esta app**: recursos por fase, Lambdas, contrato SSM, configuración | este archivo |
>
> Este README documenta **solo lo específico de telco**. Lo común a las tres industrias vive en los documentos maestros de arriba y no se repite aquí.

Un ejemplo por fases en AWS CDK (Python) que levanta un **backend de autoservicio
de telco** y lo expone a los **agentes de IA de Amazon Connect** como un servidor MCP
a través de un gateway de Bedrock AgentCore, más una **base de conocimiento de Q in
Connect** para recuperación (retrieval), los **recursos de soporte de Connect**
(perfiles de seguridad, vistas, guías, bot de Lex, flujos de contacto) que usan los
agentes, y un **sitio web estático "Latam Telco"** que aloja el widget de chat de
Connect. La app se divide en seis stacks pequeños y desacoplados que se despliegan de
forma independiente y se pasan valores entre sí solo a través de **SSM Parameter
Store** — sin exports de CloudFormation, sin nested stacks.

| Comando de despliegue | Stack | Qué despliega |
|---|---|---|
| `cdk deploy CX-TELCO-MCP` | `McpStack` (Fase 1) | Tablas DynamoDB + datos de ejemplo, el backend Lambda, la REST API de Telco, el gateway MCP de AgentCore, y las integraciones MCP/Lambda de Amazon Connect |
| `cdk deploy CX-TELCO-KB` | `KnowledgeBaseStack` (Fase 2) | La base de conocimiento EXTERNAL de Q in Connect respaldada en S3 (contenido es/pt/en) y su asociación con el asistente |
| `cdk deploy CX-TELCO-CONNECT-SUPPORT` | `ConnectSupportStack` (Fase 3) | Los perfiles de seguridad de los agentes de IA, las vistas administradas por el cliente, el flujo de la guía paso a paso de eSIM, y el bot Lex V2 de paso a Q-in-Connect |
| `cdk deploy CX-TELCO-AGENTS` | `AiAgentsStack` (Fase 4) | Los prompts de IA de orquestación y los tres agentes de IA (self-service voz + chat, agent-assist) |
| `cdk deploy CX-TELCO-FLOWS` | `ContactFlowsStack` (Fase 5) | La vista de traspaso de escalamiento, el flujo de screen-pop, los módulos de flujo escalate + set-customer-session, y el flujo inbound de self-service en español |
| `cdk deploy CX-TELCO-WEBSITE` | `WebsiteStack` (Fase 6) | El sitio estático "Latam Telco" (S3 privado + CloudFront OAC), el host del widget de chat de Connect, y el Lambda visor de datos de demo de DynamoDB |

---

## Qué se despliega

**Cómputo (Lambda)** — `accounts`, `plans`, `lines`, `ai_session` (backend de telco),
un custom resource de borrado `ProfileDetacher`, un custom resource de despliegue
`BasicQueueLookup`, y el `data_viewer` del sitio.

**Datos** — tres tablas DynamoDB on-demand (`accounts`, `plans`, `lines`) sembradas en
tiempo de despliegue, una API key en Secrets Manager, un bucket S3 cifrado con KMS con
los artículos de conocimiento, y un bucket S3 privado para el build del sitio.

**APIs y gateways** — la REST API `telco-api` (API Gateway), un **gateway de Bedrock
AgentCore** que la re-expone como servidor MCP, y una distribución de CloudFront (OAC)
frente al sitio + visor de datos.

**Amazon Connect / Q in Connect** — una base de conocimiento EXTERNAL + asociación con
el asistente, dos perfiles de seguridad de agentes de IA, tres vistas administradas por
el cliente, un bot de paso QInConnect de Lex V2, tres agentes de IA (voz / chat /
agent-assist) con sus prompts de orquestación, y cinco flujos de contacto / módulos de
flujo.

En este proyecto **no hay tareas/servicios de ECS** ni **máquinas de estado de Step
Functions** — todo el cómputo es Lambda.

### Detalle por fase

**Fase 1 — `CX-TELCO-MCP`**
- **Tablas DynamoDB** para `accounts`, `plans` y `lines` (on-demand, sembradas con datos de ejemplo en tiempo de despliegue).
- **Funciones Lambda**: `accounts`, `plans`, `lines` y `ai_session`.
- **REST API** (API Gateway) para las operaciones de telco, protegida por una API key almacenada en **Secrets Manager**.
- **Gateway de AgentCore** (Bedrock) que re-expone la REST API como un **servidor MCP**, con un **proveedor de credenciales por API key** y un target OpenAPI inline.
- **Integraciones de Amazon Connect**: registra el gateway como una **aplicación de servidor MCP** en la instancia de Connect (más un custom resource de borrado `ProfileDetacher`), y asocia los Lambdas `plans` + `ai_session` (`LAMBDA_FUNCTION`).

**Fase 2 — `CX-TELCO-KB`**
- **Clave KMS + bucket S3** con los artículos de conocimiento (subidos por CDK bajo `telco/<lang>/`).
- **DataIntegration de AppIntegrations** + **base de conocimiento EXTERNAL de Q in Connect** que rastrea el bucket.
- **Asociación con el asistente** que vincula la KB al dominio de agentes de IA de Q in Connect para que la herramienta Retrieve de un agente pueda consultarla.

**Fase 3 — `CX-TELCO-CONNECT-SUPPORT`**
- **Perfiles de seguridad de los agentes de IA** (self-service + agent-assist): `Wisdom.View` + `CustomViews.Access` de mínimo privilegio, más la concesión de herramientas MCP construida en tiempo de despliegue a partir del id del gateway.
- **Vistas administradas por el cliente** (`AWS::Connect::View`): el formulario guiado de nueva línea y la guía de activación eSIM.
- **Flujo de contacto de la guía eSIM**. La asociación de contenido `AMAZON_CONNECT_GUIDE` que vincula el flujo con el contenido `esim-activacion` de la KB se crea post-despliegue con `knowledge_bases/associate_guide.py` (los ids de contenido son valores posteriores a la ingesta), no por el stack.
- **Bot Lex V2 de paso a Q-in-Connect** (`AWS::Lex::Bot`): un único `AMAZON.QInConnectIntent` cableado al asistente de agentes de IA, 3 locales (en_US/es_US/pt_BR) sobre Nova Sonic v2 unified speech. El stack publica el ARN del **TestBotAlias** integrado del bot en SSM; compila los tres locales una vez en la consola después del despliegue.

**Fase 4 — `CX-TELCO-AGENTS`**
- **Prompts de IA de orquestación** (`AWS::Wisdom::AIPrompt`), uno por superficie de agente.
- **Tres agentes de IA** (`AWS::Wisdom::AIAgent`, orquestación): self-service **voz** y **chat** (KB Retrieve + las 9 herramientas MCP de AgentCore + Escalate/Complete; chat añade la guía de nueva línea), y **agent-assist** (Retrieve + solo superficie MCP). La asignación de perfiles de seguridad a los agentes es un paso **manual** post-despliegue.

**Fase 5 — `CX-TELCO-FLOWS`**
- **Vista de traspaso de escalamiento** (`AWS::Connect::View`) renderizada al aceptar el agente.
- **Flujo de contacto de screen-pop** que registra la vista de traspaso como el `DefaultAgentUI`.
- **Módulos de flujo**: `escalate-to-agent` (define el hook de screen-pop + la cola destino, transfiere) y `set-customer-session-telco` (clasifica el endpoint, busca al cliente vía el Lambda `ai_session`, escribe la sesión de Q in Connect).
- **Flujo inbound de self-service**: el flujo de entrada de voz/chat en español que crea la sesión de Wisdom, vincula el bot Lex + los agentes de voz/chat/assist, conduce el formulario guiado de nueva línea, y escala a un humano.
- **BasicQueueLookup** (custom resource `connect:ListQueues`) resuelve el ARN de la cola de la instancia por nombre en tiempo de despliegue.

**Fase 6 — `CX-TELCO-WEBSITE`**
- **Bucket S3 privado + CloudFront (OAC)** sirviendo el build de Vite del sitio "Latam Telco", que aloja el widget de chat de Amazon Connect y pasa el email logueado como atributo de contacto.
- **Lambda `data_viewer`** detrás de un comportamiento `/datos` de CloudFront que renderiza las tres tablas DynamoDB como una página HTML de solo lectura.

---

## Pruebas

La dependencia de dev es `pytest` (`requirements-dev.txt`). Ejecuta la suite desde la
raíz del proyecto dentro del virtualenv:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/unit/
```

El `tests/unit/test_agentic_cx_telco_stack.py` actual es el andamiaje generado por CDK
(un ejemplo de aserción `Template.from_stack`) y aún no está cableado a los stacks
reales por fases. El enfoque previsto son **pruebas de aserción** de CDK — sintetizar
un stack a una plantilla de CloudFormation y hacer aserciones sobre las propiedades de
los recursos — que combina bien con el flujo de trabajo "synth es la puerta de
verificación" (`cdk synth` debe pasar antes de desplegar).

## Configuración

Toda la configuración son constantes planas a nivel de módulo en `config.py` (sin
secretos; las credenciales de AWS se resuelven desde tu perfil/SSO local en tiempo de
despliegue), ordenadas por la fase de despliegue que primero consume cada valor. Grupos
clave: identidad de Connect (`INSTANCE_ID`, `INSTANCE_ALIAS`, `ASSISTANT_ID`,
`HAS_REAL_INSTANCE`), nombres, ajustes de KB, perfiles de seguridad, vistas/guía, bot de
Lex, agentes de IA/prompts/modelos, flujos de contacto, y ajustes de build del sitio.
Ver `config.py` para la lista completa anotada.

La **identidad de Connect es la excepción**: `INSTANCE_ALIAS`, `INSTANCE_ID` y
`ASSISTANT_ID` no están escritos en `config.py`, se leen del entorno como variables
obligatorias (`_require_env`), así que importar `config.py` lanza `ConfigError` si falta
alguna. Guárdalas en el `.env` de la raíz del repo (gitignored; `.env.example` es la
plantilla) y haz `source ../.env` una vez por terminal antes de `cdk` o de los scripts
post-despliegue. `HAS_REAL_INSTANCE` es por tanto siempre `True`; sigue existiendo como
constante para los guards `if config.HAS_REAL_INSTANCE:` de los stacks.

### Parámetros SSM (el contrato entre stacks)

Definidos una sola vez en `shared/ssm_names.py`. Solo se publican los valores que
genuinamente cruzan un límite de stack; todo lo demás queda como un `CfnOutput`. Los
secretos nunca van en el bus (la API key se queda en Secrets Manager).

| Parámetro | Productor | Consumido por | Propósito |
|---|---|---|---|
| `/agentic-cx-telco/agentcore/gateway-id` | `CX-TELCO-MCP` | Fase 3 | id del gateway sin adornos (namespace MCP del perfil de seguridad + audiencia JWT de Connect) |
| `/agentic-cx-telco/agentcore/mcp-tool-prefix` | `CX-TELCO-MCP` | Fase 4 | prefijo `gateway_<id>__<target>___` para los ids de herramientas MCP del agente |
| `/agentic-cx-telco/agentcore/lambda/plans-arn` | `CX-TELCO-MCP` | Fase 5 | ARN del Lambda plans (para los flujos de contacto) |
| `/agentic-cx-telco/agentcore/lambda/ai-session-arn` | `CX-TELCO-MCP` | Fase 5 | ARN del Lambda ai_session (para los flujos de contacto) |
| `/agentic-cx-telco/kb/knowledge-base-id` | `CX-TELCO-KB` | script | id de la KB (leído por `associate_guide.py`) |
| `/agentic-cx-telco/kb/assistant-association-id` | `CX-TELCO-KB` | Fase 4 | id de la asociación KB↔asistente (binding Retrieve del agente) |
| `/agentic-cx-telco/connect/security-profile-selfservice-id` | `CX-TELCO-CONNECT-SUPPORT` | manual | id del perfil de seguridad del agente de IA self-service |
| `/agentic-cx-telco/connect/security-profile-assist-id` | `CX-TELCO-CONNECT-SUPPORT` | manual | id del perfil de seguridad de agent-assist |
| `/agentic-cx-telco/connect/view-newline-qualified-arn` | `CX-TELCO-CONNECT-SUPPORT` | Fase 5 | ARN de la vista del formulario de nueva línea (ShowView del flujo inbound) |
| `/agentic-cx-telco/connect/lex-bot-alias-arn` | `CX-TELCO-CONNECT-SUPPORT` | Fase 5 | ARN del TestBotAlias del bot Lex para los bloques Lex del flujo inbound |
| `/agentic-cx-telco/agents/voice-arn` | `CX-TELCO-AGENTS` | Fase 5 | ARN del agente de IA de voz self-service |
| `/agentic-cx-telco/agents/chat-arn` | `CX-TELCO-AGENTS` | Fase 5 | ARN del agente de IA de chat self-service |
| `/agentic-cx-telco/agents/assist-arn` | `CX-TELCO-AGENTS` | Fase 5 | ARN del agente de IA agent-assist |
---

## Despliegue

El procedimiento de despliegue es **idéntico para las tres industrias**, así que vive una
sola vez en la guía maestra en lugar de en tres copias que se desincronizan:

> ### → [`../instructions.md`](../instructions.md) · [English](../instructions-en.md)

Cubre los prerrequisitos, el despliegue de `CX-LANG-UTILS` (una sola vez), el orden de las
seis fases, los scripts post-despliegue (`tag_kb_content.py`, `associate_guide.py`) y los
pasos manuales de consola: adjuntar los perfiles de seguridad **y publicar una nueva
versión**, la alternancia de Lex Bot Management, la compilación de locales y el widget de
chat.

### Los valores de esta app

Sustituye `{industria}` / `{INDUSTRIA}` en la guía maestra por estos:

| | |
|---|---|
| Stacks, en orden de fase | `CX-TELCO-MCP` · `CX-TELCO-KB` · `CX-TELCO-CONNECT-SUPPORT` · `CX-TELCO-AGENTS` · `CX-TELCO-FLOWS` · `CX-TELCO-WEBSITE` |
| Perfiles de seguridad a adjuntar | voz + chat → `telco-selfservice-ai-agent` · agent-assist → `telco-agent-assist-iac` |
| Flujo de la guía a asociar | `Activar eSIM` → contenido `esim` de la KB |
| Bot Lex a compilar | `telco-qconnect-bot-v2` (`en_US`, `es_US`, `pt_BR`) |

> Qué despliega cada stack y por qué depende del anterior está arriba, en
> [Detalle por fase](#detalle-por-fase). El contrato SSM que los conecta está en
> [Parámetros SSM](#parámetros-ssm-el-contrato-entre-stacks).

Para demostrar la app una vez desplegada, ver
[`DEMO-WALKTHROUGH.md`](./DEMO-WALKTHROUGH.md) ([English](./DEMO-WALKTHROUGH-en.md)).
