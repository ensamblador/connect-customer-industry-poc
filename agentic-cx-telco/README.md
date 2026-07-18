> 🌎 **English:** [if you want to see the English version, click here (`README-en.md`)](README-en.md)

# agentic-cx-telco

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

```mermaid
graph TD
    Caller["Web / phone / chat caller"]
    CF["CloudFront (OAC)"]
    SITE_S3["S3: website build (private)"]
    DV["Lambda: data_viewer"]
    Connect["Amazon Connect instance"]

    Caller -->|HTTPS| CF
    CF -->|"/*"| SITE_S3
    CF -->|"/datos"| DV
    Caller -->|voice / chat| Connect

    subgraph PHASE1["Phase 1 — MCP backend"]
        API["API Gateway: telco-api"]
        ACC["Lambda: accounts"]
        PLN["Lambda: plans"]
        LIN["Lambda: lines"]
        AIS["Lambda: ai_session"]
        SEC["Secrets Manager: API key"]
        DDB_A[("DynamoDB: accounts")]
        DDB_P[("DynamoDB: plans")]
        DDB_L[("DynamoDB: lines")]
        GW["AgentCore MCP gateway"]
        CREDP["API-key credential provider"]
    end

    subgraph PHASE2["Phase 2 — Knowledge base"]
        KB_S3["S3: KB articles (KMS)"]
        DI["AppIntegrations DataIntegration"]
        KB["Q in Connect EXTERNAL KB"]
    end

    subgraph AI["Q in Connect AI layer"]
        ASSIST["Assistant / AI agents domain"]
        VOICE["AI agent: voice"]
        CHAT["AI agent: chat"]
        AGASSIST["AI agent: agent-assist"]
    end

    API --> ACC
    API --> PLN
    API --> LIN
    ACC --> DDB_A
    PLN --> DDB_P
    LIN --> DDB_L
    API -->|API key check| SEC

    GW -->|API key| CREDP
    CREDP --> SEC
    GW -->|"invokes REST (MCP tools)"| API
    Connect -->|MCP server integration| GW

    Connect -->|LAMBDA_FUNCTION| PLN
    Connect -->|LAMBDA_FUNCTION| AIS
    AIS --> DDB_A
    AIS -->|UpdateSessionData| ASSIST

    KB_S3 --> DI --> KB --> ASSIST
    ASSIST --> VOICE
    ASSIST --> CHAT
    ASSIST --> AGASSIST
    VOICE -->|MCP tools| GW
    CHAT -->|MCP tools| GW
    AGASSIST -->|MCP tools| GW
    VOICE -->|Retrieve| KB

    DV --> DDB_A
    DV --> DDB_P
    DV --> DDB_L
```

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

## Flujos de código de los Lambda

Cada Lambda desplegado es Python 3.12 en ARM64. Las cuatro funciones del backend de
telco (`accounts`, `plans`, `lines`, `ai_session`) comparten un helper `_response()` /
`_json_default` que serializa los valores `Decimal` de DynamoDB a números JSON nativos.
**Ningún handler escribe en `/tmp` ni en S3** — la persistencia es solo DynamoDB, datos
de sesión de Q in Connect, o el estado de perfiles de seguridad de Connect.

### accounts

**Disparador:** API Gateway REST (proxy). Rutas: `GET /accounts?phoneNumber=`,
`GET /accounts/by-email?email=`, `GET /accounts/{accountId}`,
`GET /accounts/{accountId}/balance`. Lee la tabla `accounts` (+ GSIs de phone/email).

```mermaid
graph TD
    START["handler(event)"] --> PARSE["Parse pathParameters / query / resource"]
    PARSE --> BYEMAIL{"resource ends with /by-email ?"}
    BYEMAIL -->|yes| EMAILQ{"email param present ?"}
    EMAILQ -->|no| E400A["400 email required"]
    EMAILQ -->|yes| QEMAIL["DynamoDB query email-index"]
    QEMAIL --> EMAILHIT{"items found ?"}
    EMAILHIT -->|no| E404A["404 no account"]
    EMAILHIT -->|yes| OK200A["200 items[0]"]

    BYEMAIL -->|no| HASID{"accountId present ?"}
    HASID -->|no| PHONEQ{"phoneNumber param present ?"}
    PHONEQ -->|no| E400B["400 phoneNumber required"]
    PHONEQ -->|yes| QPHONE["DynamoDB query phoneNumber-index"]
    QPHONE --> PHONEHIT{"items found ?"}
    PHONEHIT -->|no| E404B["404 no account"]
    PHONEHIT -->|yes| OK200B["200 items[0]"]

    HASID -->|yes| GET["DynamoDB get_item accountId"]
    GET --> FOUND{"item found ?"}
    FOUND -->|no| E404C["404 not found"]
    FOUND -->|yes| BAL{"resource ends with /balance ?"}
    BAL -->|yes| OK200C["200 balance / currency / dueDate"]
    BAL -->|no| OK200D["200 full item"]
```

### plans

**Disparador:** DUAL. (a) Proxy REST de API Gateway: `GET /plans?minGb=`, `GET /plans/{planId}`.
(b) **Invoke AWS Lambda function** de Amazon Connect (detectado cuando el evento tiene
una clave `Details` de nivel superior y no tiene `httpMethod`). Lee la tabla `plans`.

```mermaid
graph TD
    START["handler(event)"] --> CONNECT{"has Details and no httpMethod ?"}
    CONNECT -->|yes| SCANC["DynamoDB scan plans"]
    SCANC --> SORTC["Sort by dataGb, normalize Decimals"]
    SORTC --> OPTS["Build planOptions (Label / Value)"]
    OPTS --> RETC["Return plans / planOptions / count"]

    CONNECT -->|no| PLANID{"planId in path ?"}
    PLANID -->|yes| GET["DynamoDB get_item planId"]
    GET --> FOUND{"item found ?"}
    FOUND -->|no| E404["404 not found"]
    FOUND -->|yes| OK200["200 item"]

    PLANID -->|no| SCAN["DynamoDB scan plans"]
    SCAN --> MINGB{"minGb query present ?"}
    MINGB -->|yes| NUM{"minGb is a number ?"}
    NUM -->|no| E400["400 minGb must be a number"]
    NUM -->|yes| FILTER["Filter dataGb >= minGb"]
    MINGB -->|no| SORT["Sort by dataGb ascending"]
    FILTER --> SORT
    SORT --> OKLIST["200 plans / count"]
```

### lines

**Disparador:** Proxy REST de API Gateway. Rutas: `POST /lines`, `GET /lines?customerId=`,
`GET /lines/{lineId}`. Lee/escribe la tabla `lines` (+ GSI de customerId); genera
`lineId` del lado del servidor con `uuid4`.

```mermaid
graph TD
    START["handler(event)"] --> METHOD{"httpMethod == POST ?"}
    METHOD -->|yes| BODY["json.loads(body)"]
    BODY --> VALIDJSON{"valid JSON ?"}
    VALIDJSON -->|no| E400A["400 body must be valid JSON"]
    VALIDJSON -->|yes| REQ{"customerId and planId present ?"}
    REQ -->|no| E400B["400 customerId / planId required"]
    REQ -->|yes| AREA{"areaCode valid 3-digit ?"}
    AREA -->|no| E400C["400 areaCode must be 3-digit"]
    AREA -->|yes| PUT["DynamoDB put_item (status=requested)"]
    PUT --> OK201["201 line"]

    METHOD -->|no| HASID{"lineId in path ?"}
    HASID -->|yes| GET["DynamoDB get_item lineId"]
    GET --> FOUND{"item found ?"}
    FOUND -->|no| E404["404 not found"]
    FOUND -->|yes| OK200["200 item"]

    HASID -->|no| CUST{"customerId query present ?"}
    CUST -->|no| E400D["400 customerId required"]
    CUST -->|yes| QUERY["DynamoDB query customerId-index"]
    QUERY --> OKLIST["200 customerId / lines / count"]
```

### ai_session

**Disparador:** `InvokeLambdaFunction` de Amazon Connect desde el módulo de flujo
`set-customer-session-telco`. Devuelve un **STRING_MAP** plano. Lee la tabla `accounts`
(GSIs de phone/email), llama a `connect:DescribeContact` para encontrar el ARN de la
sesión de Wisdom del contacto, y a `qconnect:UpdateSessionData` para escribir atributos
en la sesión de Q in Connect. Todas las fallas de Connect/sesión se silencian para que
una escritura de personalización nunca bloquee el contacto.

```mermaid
graph TD
    START["handler(event)"] --> READ["Read Parameters + ContactId; phone / email"]
    READ --> MODE{"phone or email present ?"}

    MODE -->|no| WRITABLE{"any writable params ?"}
    WRITABLE -->|no| RETFALSE["Return session_updated=false"]
    WRITABLE -->|yes| WRITE["_write_session_values"]
    WRITE --> ARN1["connect:DescribeContact -> session ARN"]
    ARN1 --> HASARN1{"session ARN found ?"}
    HASARN1 -->|no| WSKIP["skip; session_updated=false"]
    HASARN1 -->|yes| UPD1["qconnect:UpdateSessionData"]
    UPD1 --> WRESP["Return session_updated + echoed keys"]
    WSKIP --> WRESP

    MODE -->|yes| LOOKUP["_lookup_customer: DynamoDB query phone/email GSI"]
    LOOKUP --> ITEM{"customer found ?"}
    ITEM -->|no| NOTCUST["Return is_customer=FALSE"]
    ITEM -->|yes| ARN2["connect:DescribeContact -> session ARN"]
    ARN2 --> HASARN2{"ARN + data present ?"}
    HASARN2 -->|no| LSKIP["session_updated stays false"]
    HASARN2 -->|yes| UPD2["qconnect:UpdateSessionData"]
    UPD2 --> LRESP["Return is_customer=TRUE + fields"]
    LSKIP --> LRESP
```

### ProfileDetacher (custom resource, en borrado)

**Disparador:** custom resource de CloudFormation (`cr.Provider`) en el stack de MCP. En
**Create/Update es un no-op**; en **Delete** quita el namespace de esta aplicación MCP
(el id del gateway) de cada perfil de seguridad de Connect que aún lo conceda, para que
`DeleteIntegrationAssociation` pueda proceder automáticamente. Llama a
`connect:ListSecurityProfiles`, `ListSecurityProfileApplications`, y
`UpdateSecurityProfile`.

```mermaid
graph TD
    START["on_event(event)"] --> RT{"RequestType == Delete ?"}
    RT -->|no| NOOP["Return PhysicalResourceId (no-op)"]
    RT -->|yes| LIST["connect:ListSecurityProfiles (paginated)"]
    LIST --> LOOP["For each security profile"]
    LOOP --> APPS["ListSecurityProfileApplications"]
    APPS --> HAS{"namespace present on profile ?"}
    HAS -->|no| LOOP
    HAS -->|yes| REBUILD["Drop matching namespace"]
    REBUILD --> UPDATE["connect:UpdateSecurityProfile"]
    UPDATE --> LOOP
    LOOP --> DONE["Return PhysicalResourceId"]
```

### BasicQueueLookup (custom resource, en despliegue)

**Disparador:** custom resource de CloudFormation en el stack de FLOWS. Resuelve el ARN
de la cola estándar por nombre (`connect:ListQueues`, paginado) para que los flujos
transfieran a una cola válida sin id hardcodeado. Lanza un error ruidoso si la cola
nombrada no se encuentra.

```mermaid
graph TD
    START["handler(event)"] --> RT{"RequestType == Delete ?"}
    RT -->|yes| NOOP["Return PhysicalResourceId (no-op)"]
    RT -->|no| PAGE["connect:ListQueues (STANDARD, paginated)"]
    PAGE --> MATCH{"queue name matches ?"}
    MATCH -->|no| PAGE
    MATCH -->|yes| FOUND["Capture Arn + Id"]
    FOUND --> CHECK{"arn resolved ?"}
    CHECK -->|no| RAISE["raise Exception (fail deploy)"]
    CHECK -->|yes| RET["Return QueueArn / QueueId"]
```

### data_viewer (sitio web)

**Disparador:** Lambda detrás de un comportamiento `/datos` de CloudFront (proxy de API
Gateway con OAC). Escanea las tres tablas DynamoDB (`accounts`, `plans`, `lines`) con
paginación completa y renderiza una única página HTML de solo lectura en memoria (sin
`/tmp`, sin S3). Un único try/except devuelve una página HTML 500 ante cualquier error.

```mermaid
graph TD
    START["handler(event)"] --> TRY["try: for each table"]
    TRY --> SCAN["DynamoDB scan (paginated)"]
    SCAN --> SECTION["Build HTML table section"]
    SECTION --> MORE{"more tables ?"}
    MORE -->|yes| SCAN
    MORE -->|no| PAGE["Render _PAGE with content"]
    PAGE --> OK200["200 text/html (no-store)"]
    TRY -->|Exception| ERR["Render error section"]
    ERR --> E500["500 text/html"]
```

## Flujos de código de tareas y servicios de ECS

Ninguno. Este proyecto no despliega tareas ni servicios de ECS.

## Workflows de Step Functions

Ninguno. Este proyecto no despliega máquinas de estado de Step Functions.

---

## Estructura del proyecto

```
agentic-cx-telco/
├── app.py                     # Entrada de la app CDK — cablea los seis stacks por fases + dependencias
├── config.py                  # Config plana a nivel de módulo, agrupada por fase de despliegue (sin secretos)
├── cdk.json                   # Ejecuta `python3 app.py`
├── requirements.txt           # Deps de runtime (aws-cdk-lib, constructs, PyYAML, boto3)
├── requirements-dev.txt       # Deps de dev (pytest)
│
├── agentic_cx_telco/          # Los seis stacks CDK
│   ├── mcp_stack.py               # Fase 1  CX-TELCO-MCP
│   ├── knowledge_base_stack.py    # Fase 2  CX-TELCO-KB
│   ├── connect_support_stack.py   # Fase 3  CX-TELCO-CONNECT-SUPPORT
│   ├── ai_agents_stack.py         # Fase 4  CX-TELCO-AGENTS
│   ├── contact_flows_stack.py     # Fase 5  CX-TELCO-FLOWS
│   └── website_stack.py           # Fase 6  CX-TELCO-WEBSITE
│
├── lambdas/
│   ├── project_lambdas.py     # Construct `Lambdas` (accounts / plans / lines / ai_session)
│   └── code/                  # Código de los handlers, una carpeta por función
│       ├── accounts/handler.py
│       ├── plans/handler.py
│       ├── lines/handler.py
│       └── ai_session/handler.py
│
├── apis/                      # Construct de la REST API + spec OpenAPI (telco_api.py, openapi/)
├── agent_core/                # Constructs del gateway AgentCore + proveedor de credenciales por API key
├── databases/                # Construct de tablas DynamoDB + datos semilla (data/)
├── knowledge_bases/          # Construct de KB + artículos de telco + scripts post-despliegue
│   ├── knowledge_base.py
│   ├── tag_kb_content.py          # post-despliegue: etiqueta el contenido de la KB para segmentación de Retrieve
│   └── associate_guide.py    # post-despliegue: crea la asociación AMAZON_CONNECT_GUIDE
├── connect/                  # Bloques de construcción de Connect (constructs + lambdas inline/CR)
│   ├── mcp_integration.py         # Integración de aplicación MCP + ProfileDetacher (CR inline)
│   ├── basic_queue_lookup_cr.py   # Construct BasicQueueLookup
│   ├── basic_queue_lookup_cr_lambda/index.py   # su handler de CR
│   ├── ai_agents.py / ai_prompts.py / security_profile.py / lex_bot.py / views.py / flows.py
│   └── lambda_integration.py
├── connect_ai_agents/        # YAML de prompts de orquestación por superficie de agente
├── flows/                    # JSON de flujos de contacto + módulos (una carpeta por flujo)
├── views/                    # JSON de vistas administradas por el cliente (formulario nueva línea / guía eSIM / traspaso)
├── webhosting/               # Construct de hosting del sitio + data_viewer_lambda/index.py
├── website/                  # Front-end Vite "Latam Telco" (salida del build → website/dist)
├── shared/ssm_names.py       # El contrato de nombres de parámetros SSM entre stacks
└── tests/unit/               # Andamiaje de pytest
```

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

```bash
source .venv/bin/activate
pip install -r requirements.txt

# synth (puerta de verificación) — cdk.json ejecuta `python3 app.py`
cdk synth

# Fase 1 + Fase 2 — independientes, se despliegan en cualquier orden
cdk deploy CX-TELCO-MCP --profile connect-industry
cdk deploy CX-TELCO-KB  --profile connect-industry

# Fase 3 — depende de la Fase 1 (gateway id) y de la Fase 2 (kb id)
cdk deploy CX-TELCO-CONNECT-SUPPORT --profile connect-industry

# Fase 4 — depende de la Fase 1 (prefijo de herramientas MCP) y de la Fase 2 (asociación de KB)
cdk deploy CX-TELCO-AGENTS --profile connect-industry

# Fase 5 — depende de la Fase 1 (Lambda ai_session), la Fase 3 (vista + alias Lex),
# y la Fase 4 (ARNs de agentes)
cdk deploy CX-TELCO-FLOWS --profile connect-industry

# Fase 6 — compila el sitio primero, luego despliega (S3 + CloudFront)
cd website && npm install && npm run build && cd ..
cdk deploy CX-TELCO-WEBSITE --profile connect-industry
```

### Pasos post-despliegue

Después de la **Fase 4**, asigna los perfiles de seguridad de la Fase 3 a los agentes de
IA (manual — no hay recurso nativo de CFN para `connect:AssociateSecurityProfiles` con
`EntityType=AI_AGENT`):

1. En el **sitio de administración de Amazon Connect**, abre **AI agents** (Q in Connect).
2. Asigna perfiles: voz + chat → `telco-selfservice-ai-agent`, agent-assist →
   `telco-agent-assist-iac`.
3. Para **agent-assist**, los agentes humanos que usan el panel del asistente también
   deben llevar los mismos permisos — las llamadas a herramientas se autorizan contra la
   intersección de los perfiles del agente de IA y del agente humano.

Después de que la **Fase 2** termine su primer sync, etiqueta el contenido de la KB para
que la herramienta Retrieve lo encuentre, luego cablea la guía eSIM a su artículo:

```bash
python knowledge_bases/tag_kb_content.py --wait --expect 21 --kb-id <kb-id> --profile connect-industry
python knowledge_bases/associate_guide.py --profile connect-industry   # añade --dry-run para previsualizar
```

Después de la **Fase 3**, compila los tres locales del bot Lex (`en_US`, `es_US`,
`pt_BR`) en la consola de Amazon Lex V2 para que su **TestBotAlias** quede activo para el
flujo inbound (los locales intencionalmente no se auto-compilan para mantener el
despliegue rápido).
