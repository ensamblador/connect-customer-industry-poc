# agentic-cx-bank

> 📚 **Dónde está cada cosa**
>
> | Necesitas | Ve a |
> |---|---|
> | Visión general del PoC, arquitectura de referencia, desafíos que resuelve | [`../README.md`](../README.md) · [English](../README-en.md) |
> | Cómo desplegar: prerrequisitos, orden de fases, scripts y pasos manuales de consola | [`../instructions.md`](../instructions.md) · [English](../instructions-en.md) |
> | Cómo demostrarlo: preguntas exactas, qué esperar, checklist | [`DEMO-WALKTHROUGH.md`](./DEMO-WALKTHROUGH.md) · [English](./DEMO-WALKTHROUGH-en.md) |
> | **Detalle interno de esta app**: recursos por fase, Lambdas, contrato SSM, configuración | este archivo |
>
> Este README documenta **solo lo específico de banco**. Lo común a las tres industrias vive en los documentos maestros de arriba y no se repite aquí.

Un ejemplo por fases en AWS CDK (Python) que levanta un **backend de autoservicio de
banca retail** y lo expone a los **agentes de IA de Amazon Connect** como un servidor
MCP a través de un gateway de Bedrock AgentCore, más una **base de conocimiento de Q in
Connect** para recuperación (retrieval), los **recursos de soporte de Connect**
(perfiles de seguridad, vistas, guías, bot de Lex, flujos de contacto) que usan los
agentes, y un **sitio web estático "Latam Banco"** que aloja el widget de chat de
Connect. La app se divide en seis stacks pequeños y desacoplados que se despliegan de
forma independiente y se pasan valores entre sí solo a través de **SSM Parameter
Store** — sin exports de CloudFormation, sin nested stacks.

| Comando de despliegue | Stack | Fase | Qué despliega |
|---|---|---|---|
| `cdk deploy CX-BANCO-MCP` | `McpStack` | Fase 1 | Tablas DynamoDB + datos de ejemplo, el backend Lambda, la REST API `banco-api`, el gateway MCP de AgentCore, y las integraciones MCP/Lambda de Amazon Connect |
| `cdk deploy CX-BANCO-KB` | `KnowledgeBaseStack` | Fase 2 | La base de conocimiento EXTERNAL de Q in Connect respaldada en S3 (contenido es/pt/en) y su asociación con el asistente |
| `cdk deploy CX-BANCO-CONNECT-SUPPORT` | `ConnectSupportStack` | Fase 3 | Los perfiles de seguridad de los agentes de IA, las vistas administradas por el cliente, el flujo de la guía paso a paso de activar tarjeta, y el bot Lex V2 de paso a Q-in-Connect |
| `cdk deploy CX-BANCO-AGENTS` | `AiAgentsStack` | Fase 4 | Los prompts de IA de orquestación y los tres agentes de IA (self-service voz + chat, agent-assist) |
| `cdk deploy CX-BANCO-FLOWS` | `ContactFlowsStack` | Fase 5 | La vista de traspaso de escalamiento, el flujo de screen-pop, los módulos de flujo escalate + set-customer-session, y el flujo inbound de self-service en español |
| `cdk deploy CX-BANCO-WEBSITE` | `WebsiteStack` | Fase 6 | El sitio estático "Latam Banco" (S3 privado + CloudFront OAC), el host del widget de chat de Connect, y el Lambda visor de datos de demo de DynamoDB |

**Orden de despliegue: `CX-BANCO-MCP` → `CX-BANCO-KB` → `CX-BANCO-CONNECT-SUPPORT` →
`CX-BANCO-AGENTS` → `CX-BANCO-FLOWS` → `CX-BANCO-WEBSITE`.** Las Fases 1 y 2 son
mutuamente independientes y pueden desplegarse en cualquier orden; cada fase posterior
consume valores de SSM publicados por las fases anteriores (ver [Despliegue](#despliegue)).

---

## Qué se despliega

**Cómputo (Lambda)** — `accounts`, `products`, `cards`, `ai_session` (backend de
banca), un custom resource de borrado `ProfileDetacher`, un custom resource de
despliegue `BasicQueueLookup`, y el `data_viewer` del sitio.

**Datos** — tres tablas DynamoDB on-demand (`banco-accounts`, `banco-products`,
`banco-cards`) sembradas en tiempo de despliegue, una API key en Secrets Manager, un
bucket S3 cifrado con KMS con los artículos de conocimiento, y un bucket S3 privado para
el build del sitio.

**APIs y gateways** — la REST API `banco-api` (API Gateway), un **gateway de Bedrock
AgentCore** (`banco-mcp-server`) que la re-expone como servidor MCP, y una distribución
de CloudFront (OAC) frente al sitio + visor de datos.

**Amazon Connect / Q in Connect** — una base de conocimiento EXTERNAL + asociación con
el asistente, dos perfiles de seguridad de agentes de IA, tres vistas administradas por
el cliente, un bot de paso QInConnect de Lex V2, tres agentes de IA (voz / chat /
agent-assist) con sus prompts de orquestación, y cinco flujos de contacto / módulos de
flujo.

En este proyecto **no hay tareas/servicios de ECS** ni **máquinas de estado de Step
Functions** — todo el cómputo es Lambda.

### Detalle por fase

**Fase 1 — `CX-BANCO-MCP`**
- **Tablas DynamoDB** para `banco-accounts`, `banco-products` y `banco-cards`
  (on-demand, sembradas con datos de ejemplo en tiempo de despliegue), con GSIs
  `phoneNumber-index` + `email-index` en accounts y `customerId-index` en cards.
- **Funciones Lambda**: `accounts`, `products`, `cards` y `ai_session`.
- **REST API** (`banco-api`, API Gateway) para las operaciones de banca, protegida por
  una API key almacenada en **Secrets Manager** y forzada con un usage plan.
- **Gateway de AgentCore** (`banco-mcp-server`, Bedrock) que re-expone la REST API como
  un **servidor MCP**, con un **proveedor de credenciales por API key**
  (`banco-mcp-server-apikey`) y un target OpenAPI inline
  (`banco-rest-api-oas-target`).
- **Integraciones de Amazon Connect**: registra el gateway como una **aplicación de
  servidor MCP** en la instancia de Connect (más un custom resource de borrado
  `ProfileDetacher`), y asocia los Lambdas `products` + `ai_session`
  (`LAMBDA_FUNCTION`).
- **Publica en SSM:** `GATEWAY_ID`, `MCP_TOOL_PREFIX`, `LAMBDA_PLANS_ARN` (el ARN del
  Lambda products — se preserva el sufijo de la clave), `LAMBDA_AI_SESSION_ARN`.

**Fase 2 — `CX-BANCO-KB`**
- **Clave KMS + bucket S3** con los artículos de conocimiento (subidos por CDK bajo
  `bank/<lang>/`).
- **DataIntegration de AppIntegrations** + **base de conocimiento EXTERNAL de Q in
  Connect** (`banco-kb`) que rastrea el bucket.
- **Asociación con el asistente** que vincula la KB al dominio de agentes de IA de Q in
  Connect para que la herramienta Retrieve de un agente pueda consultarla.
- **Publica en SSM:** `KB_ID`, `KB_ASSOC_ID`.

**Fase 3 — `CX-BANCO-CONNECT-SUPPORT`**
- **Perfiles de seguridad de los agentes de IA** (`banco-selfservice-ai-agent`,
  `banco-agent-assist-iac`): `Wisdom.View` + `CustomViews.Access` de mínimo privilegio,
  más la concesión de herramientas MCP construida en tiempo de despliegue a partir del
  id del gateway (consumido de SSM `GATEWAY_ID`).
- **Vistas administradas por el cliente** (`AWS::Connect::View`): el formulario guiado de
  solicitud de tarjeta (`BancoCardRequestForm`) y la guía de activar tarjeta
  (`BancoCardActivationGuide`).
- **Flujo de contacto de la guía de activar tarjeta** (nombre visible **`Activar
  tarjeta`**). La asociación de contenido `AMAZON_CONNECT_GUIDE` que vincula el flujo con
  el contenido `activar-tarjeta` de la KB se crea post-despliegue con
  `knowledge_bases/associate_guide.py` (los ids de contenido son valores
  posteriores a la ingesta), no por el stack.
- **Bot Lex V2 de paso a Q-in-Connect** (`banco-qconnect-bot-v2`): un único
  `AMAZON.QInConnectIntent` cableado al asistente de agentes de IA, 3 locales
  (en_US/es_US/pt_BR) sobre Nova Sonic v2 unified speech. El stack publica el ARN del
  **TestBotAlias** integrado del bot en SSM; compila los tres locales una vez en la
  consola después del despliegue.
- **Publica en SSM:** `SP_SELFSERVICE_ID`, `SP_ASSIST_ID`, `VIEW_NEWLINE_ARN` (el ARN
  calificado del formulario de solicitud de tarjeta — se preserva el sufijo de la
  clave), `LEX_BOT_ALIAS_ARN`.

**Fase 4 — `CX-BANCO-AGENTS`**
- **Prompts de IA de orquestación** (`AWS::Wisdom::AIPrompt`), uno por superficie de
  agente (`banco-selfservice-voice-orchestration`,
  `banco-selfservice-chat-orchestration`, `banco-agent-assist-orchestration`).
- **Tres agentes de IA** (`AWS::Wisdom::AIAgent`, orquestación):
  `banco-selfservice-voice-es` y `banco-selfservice-chat-es` (KB Retrieve + las 9
  herramientas MCP de AgentCore + Escalate/Complete; chat añade la herramienta de la guía
  de solicitud de tarjeta), y `banco-agent-assist-es` (Retrieve + solo superficie MCP).
  La herramienta Retrieve filtra `industry=bank` Y `language=es`. La asignación de
  perfiles de seguridad a los agentes es un paso **manual** post-despliegue.
- **Publica en SSM:** `AGENT_VOICE_ARN`, `AGENT_CHAT_ARN`, `AGENT_ASSIST_ARN`.

**Fase 5 — `CX-BANCO-FLOWS`**
- **Vista de traspaso de escalamiento** (`BancoEscalationHandoff`, `AWS::Connect::View`)
  renderizada al aceptar el agente.
- **Flujo de contacto de screen-pop** (`banco-agent-screenpop-es`) que registra la vista
  de traspaso como el `DefaultAgentUI`.
- **Módulos de flujo**: `banco-escalate-to-agent` (define el hook de screen-pop + la cola
  destino, transfiere) y `set-customer-session-banco` (clasifica el endpoint, busca al
  cliente vía el Lambda `ai_session`, escribe la sesión de Q in Connect).
- **Flujo inbound de self-service** (`banco-selfservice-es-inbound`): el flujo de entrada
  de voz/chat en español que crea la sesión de Wisdom, vincula el bot Lex + los agentes
  de voz/chat/assist, conduce el formulario guiado de solicitud de tarjeta, y escala a un
  humano. También consume el `INIT_FLOW_MODULE_ARN` externo (`/flows/init/es`) como su
  módulo de inicio.
- **BasicQueueLookup** (custom resource `connect:ListQueues`) resuelve el ARN de la
  `BasicQueue` de la instancia por nombre en tiempo de despliegue.

**Fase 6 — `CX-BANCO-WEBSITE`**
- **Bucket S3 privado + CloudFront (OAC)** sirviendo el build de Vite del sitio "Latam
  Banco", que aloja el widget de chat de Amazon Connect y pasa el email logueado como
  atributo de contacto.
- **Lambda `data_viewer`** detrás de un comportamiento `/datos` de CloudFront que
  renderiza las tres tablas DynamoDB (`banco-accounts`, `banco-products`, `banco-cards`)
  como una página HTML de solo lectura.

---

## Subsistemas de banca

**Cuentas y búsqueda de cliente** — `banco-accounts` guarda las cuentas de cliente (con
GSIs `phoneNumber` y `email`). El Lambda `accounts` sirve la búsqueda de cuenta por
teléfono, por email, por id, y un resumen de saldo; el Lambda `ai_session` reutiliza las
mismas búsquedas para personalizar un contacto en vivo escribiendo el registro del
cliente en la sesión de Q in Connect.

**Catálogo de productos** — `banco-products` guarda el catálogo de productos bancarios
(cuentas de nómina, tarjetas clásica/oro, …). El Lambda `products` lista productos (con
un filtro opcional `maxAnnualFee`) y devuelve los detalles de un producto individual;
también responde llamadas de "Invoke Lambda" de Amazon Connect con una lista
`productOptions` lista para vista para el formulario guiado.

**Solicitudes de tarjeta** — `banco-cards` guarda las solicitudes de tarjeta / producto
indexadas por `cardId` (con un GSI `customerId-index`). El Lambda `cards` crea una nueva
solicitud (`status = requested`, `cardId` generado por el servidor), lista las
solicitudes de un cliente, y devuelve una solicitud individual por id. `requestCard` es
la única operación que cambia estado y está protegida por confirmación en los agentes.

**Base de conocimiento** — `banco-kb` sirve artículos de autoservicio (cuentas,
tarjetas, transferencias, comisiones, FAQ, info de sucursales, activar tarjeta) en tres
idiomas (es/pt/en). La herramienta Retrieve de los agentes la consulta, segmentada por
etiquetas `industry` + `language`.

**Agentes de IA** — tres agentes de orquestación (self-service voz, self-service chat,
agent-assist) atienden contactos usando la herramienta KB Retrieve más las 9
herramientas MCP de banca, escalando a un humano cuando es necesario.

**Flujos de contacto** — el flujo inbound personaliza y enruta contactos, vincula el bot
Lex y los agentes, conduce el formulario de solicitud de tarjeta, y escala vía los
módulos de screen-pop + escalate.

**Sitio web** — el sitio "Latam Banco" aloja el widget de chat de Connect y un visor de
datos de demo para las tres tablas DynamoDB.

---

## Pruebas

La dependencia de dev es `pytest` (`requirements-dev.txt`). Ejecuta la suite desde la
raíz del proyecto dentro del virtualenv:

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/unit/
```

El enfoque previsto son **pruebas de aserción** de CDK — sintetizar un stack a una
plantilla de CloudFormation y hacer aserciones sobre las propiedades de los recursos —
que combina bien con el flujo de trabajo "synth es la puerta de verificación"
(`cdk synth` debe pasar antes de desplegar).

## Configuración

Toda la configuración son constantes planas a nivel de módulo en `config.py` (sin
secretos; las credenciales de AWS se resuelven desde tu perfil/SSO local en tiempo de
despliegue), ordenadas por la fase de despliegue que primero consume cada valor. Grupos
clave: identidad de Connect (`INSTANCE_ID`, `INSTANCE_ALIAS`, `ASSISTANT_ID`,
`HAS_REAL_INSTANCE`), nombres, ajustes de KB, perfiles de seguridad, vistas/guía, bot de
Lex, agentes de IA/prompts/modelos, flujos de contacto, y ajustes de build del sitio.
La **identidad de Connect es la excepción**: `INSTANCE_ALIAS`, `INSTANCE_ID` y
`ASSISTANT_ID` no están escritos en `config.py`, se leen del entorno como variables
obligatorias (`_require_env`), así que importar `config.py` lanza `ConfigError` si falta
alguna. Guárdalas en el `.env` de la raíz del repo (gitignored; `.env.example` es la
plantilla) y haz `source ../.env` una vez por terminal antes de `cdk` o de los scripts
post-despliegue. `HAS_REAL_INSTANCE` es por tanto siempre `True`; sigue existiendo como
constante para los guards `if config.HAS_REAL_INSTANCE:` de los stacks.

Cada nombre de recurso lleva el prefijo de su industria, así que nunca colisiona con los
recursos de un proyecto hermano en la instancia de Connect compartida. Ver `config.py`
para la lista completa anotada.

### Parámetros SSM (el contrato entre stacks)

Definidos una sola vez en `shared/ssm_names.py` bajo el namespace `/agentic-cx-bank`.
Solo se publican los valores que genuinamente cruzan un límite de stack; todo lo demás
queda como un `CfnOutput`. Los secretos nunca van en el bus (la API key se queda en
Secrets Manager).

| Parámetro | Productor | Consumido por | Valor que lleva |
|---|---|---|---|
| `/agentic-cx-bank/agentcore/gateway-id` | `CX-BANCO-MCP` | Fase 3 | id del gateway sin adornos (namespace MCP del perfil de seguridad + audiencia JWT de Connect) |
| `/agentic-cx-bank/agentcore/mcp-tool-prefix` | `CX-BANCO-MCP` | Fase 4 | prefijo `gateway_<id>__banco-rest-api-oas-target___` para los ids de herramientas MCP del agente |
| `/agentic-cx-bank/agentcore/lambda/plans-arn` | `CX-BANCO-MCP` | Fase 5 | ARN del Lambda products (para los flujos de contacto) |
| `/agentic-cx-bank/agentcore/lambda/ai-session-arn` | `CX-BANCO-MCP` | Fase 5 | ARN del Lambda ai_session (para los flujos de contacto) |
| `/agentic-cx-bank/kb/knowledge-base-id` | `CX-BANCO-KB` | scripts | id de la KB (leído por ambos scripts post-despliegue) |
| `/agentic-cx-bank/kb/assistant-association-id` | `CX-BANCO-KB` | Fase 4 | id de la asociación KB↔asistente (binding Retrieve del agente) |
| `/agentic-cx-bank/connect/security-profile-selfservice-id` | `CX-BANCO-CONNECT-SUPPORT` | manual | id del perfil de seguridad del agente de IA self-service |
| `/agentic-cx-bank/connect/security-profile-assist-id` | `CX-BANCO-CONNECT-SUPPORT` | manual | id del perfil de seguridad de agent-assist |
| `/agentic-cx-bank/connect/view-newline-qualified-arn` | `CX-BANCO-CONNECT-SUPPORT` | Fase 5 | ARN de la vista del formulario de solicitud de tarjeta (ShowView del flujo inbound) |
| `/agentic-cx-bank/connect/lex-bot-alias-arn` | `CX-BANCO-CONNECT-SUPPORT` | Fase 5 | ARN del TestBotAlias del bot Lex para los bloques Lex del flujo inbound |
| `/agentic-cx-bank/agents/voice-arn` | `CX-BANCO-AGENTS` | Fase 5 | ARN del agente de IA de voz self-service |
| `/agentic-cx-bank/agents/chat-arn` | `CX-BANCO-AGENTS` | Fase 5 | ARN del agente de IA de chat self-service |
| `/agentic-cx-bank/agents/assist-arn` | `CX-BANCO-AGENTS` | Fase 5 | ARN del agente de IA agent-assist |

> **Dependencia externa (no es una clave del Bank_Project):** `INIT_FLOW_MODULE_ARN`
> resuelve a `/flows/init/es`, que vive **fuera** del namespace `/agentic-cx-bank`. Lo
> publica la app de localización separada `CX-LANG-UTILS` en la misma instancia de
> Connect y lo consume el flujo inbound de la Fase 5 como su módulo de inicio.
> `CX-LANG-UTILS` debe desplegarse primero para que el parámetro exista en tiempo de
> despliegue.
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
| Stacks, en orden de fase | `CX-BANCO-MCP` · `CX-BANCO-KB` · `CX-BANCO-CONNECT-SUPPORT` · `CX-BANCO-AGENTS` · `CX-BANCO-FLOWS` · `CX-BANCO-WEBSITE` |
| Perfiles de seguridad a adjuntar | voz + chat → `banco-selfservice-ai-agent` · agent-assist → `banco-agent-assist-iac` |
| Flujo de la guía a asociar | `Activar tarjeta` → contenido `activar-tarjeta` de la KB |
| Bot Lex a compilar | `banco-qconnect-bot-v2` (`en_US`, `es_US`, `pt_BR`) |

> Qué despliega cada stack y por qué depende del anterior está arriba, en
> [Detalle por fase](#detalle-por-fase). El contrato SSM que los conecta está en
> [Parámetros SSM](#parámetros-ssm-el-contrato-entre-stacks).

Para demostrar la app una vez desplegada, ver
[`DEMO-WALKTHROUGH.md`](./DEMO-WALKTHROUGH.md) ([English](./DEMO-WALKTHROUGH-en.md)).
