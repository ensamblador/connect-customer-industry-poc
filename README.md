# Amazon Connect — Agentic Customer Experience PoC

> **Autoservicio inteligente, omnicanal y multiindustria** con Amazon Connect AI Agents, Q in Connect, y Bedrock AgentCore MCP.

Este repositorio contiene una prueba de concepto completa que demuestra cómo resolver los desafíos más comunes de los contact centers usando capacidades agénticas de Amazon Connect. Cada industria (telco, banco, aerolínea) re-tematiza la misma arquitectura de referencia con datos y experiencias de dominio específicas, compartiendo una sola instancia de Connect.

---

## Desafíos y Soluciones

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

Las atenciones simples requieren esperar a un agente humano, con disponibilidad limitada en horario 9-5.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**Autoservicio agéntico omnicanal 24/7** — Amazon Connect AI Agents resuelven consultas de principio a fin por voz y chat, sin intervención humana. El agente consulta sistemas backend (MCP tools), busca en la base de conocimiento, y solo escala cuando realmente no puede resolver.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

IVRs estáticos sin flexibilidad: árboles de menú rígidos que frustran al cliente y no se adaptan al contexto de la conversación.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**Atención agéntica conversacional** — En lugar de "Presione 1 para...", el cliente habla naturalmente. Un bot Lex V2 con Nova Sonic v2 delega al AI Agent de Q in Connect, que entiende la intención, accede a herramientas y resuelve en lenguaje natural. Sin menús, sin frustración.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

Voces robóticas y monótonas que no generan confianza ni cercanía con el cliente.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**Voces agénticas de nueva generación (Katie)** — Las nuevas voces de Amazon Connect son políglota y expresivas. Katie habla español, inglés y portugués con naturalidad, adaptando tono y ritmo al contexto de la conversación. Configuración en el bot Lex V2 con Nova Sonic v2 unified speech.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

El autoservicio no puede acceder a sistemas internos: el bot responde preguntas genéricas pero no puede consultar saldos, hacer reservas, ni ejecutar acciones reales.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**MCP Tools + Knowledge Base por industria** — Bedrock AgentCore expone una REST API (DynamoDB + Lambda) como herramientas MCP que el AI Agent invoca en tiempo real: consultar cuentas, listar vuelos/productos, crear reservas. La KB multilingüe (es/pt/en) cubre FAQs, políticas y procedimientos del dominio.

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

Cuando el autoservicio no puede resolver, el cliente es transferido a un agente humano sin contexto — y tiene que repetir todo desde cero.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**Escalación con contexto completo** — Al escalar, el AI Agent registra un `escalationSummary` con lo que se intentó y por qué se escala. El agente humano recibe un screen-pop con los datos del cliente, el resumen de la conversación y las herramientas del AI Agent a su disposición (Agent Assist).

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

Los agentes humanos pierden tiempo buscando información en múltiples sistemas mientras el cliente espera en la línea.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**Agent Assist con sugerencias en tiempo real** — Q in Connect escucha la conversación y sugiere respuestas de la KB, ejecuta herramientas MCP, y ofrece **guías paso a paso** cuando detecta un tema específico (p. ej. "maleta perdida" dispara automáticamente la guía de reporte de equipaje).

</td>
</tr>
</table>

---

<table>
<tr>
<td width="50%" style="background-color:#fce4e4; vertical-align:top; padding:16px;">

### Desafío

El soporte solo funciona en un idioma, excluyendo a una base de clientes diversa en Latinoamérica.

</td>
<td width="50%" style="background-color:#e4fce4; vertical-align:top; padding:16px;">

### Solución

**Localización nativa multilingüe** — Los prompts de IA, el bot Lex (3 locales: en_US, es_US, pt_BR), la base de conocimiento (artículos en es/pt/en) y los mensajes de espera se localizan por idioma. Los agentes utilitarios (Answer Recommendation, Note Taking) tienen prompts localizados para responder en el idioma del contacto.

</td>
</tr>
</table>

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Amazon Connect Instance                       │
│                                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────────────────┐  │
│  │ Lex Bot  │──▶│  AI Agents   │──▶│   Q in Connect (Wisdom)    │  │
│  │ Nova     │   │  Voice/Chat/ │   │   KB + Retrieve + Guides   │  │
│  │ Sonic v2 │   │  Agent Assist│   └────────────────────────────┘  │
│  └──────────┘   └──────┬───────┘                                    │
│                         │ MCP Tools                                  │
│                         ▼                                            │
│            ┌────────────────────────┐                                │
│            │  Bedrock AgentCore     │                                │
│            │  MCP Gateway + Target  │                                │
│            └───────────┬────────────┘                                │
└────────────────────────┼────────────────────────────────────────────┘
                         │ REST API (API Key)
                         ▼
              ┌─────────────────────┐
              │   API Gateway       │
              │   + Lambda + DDB    │
              │   (industry data)   │
              └─────────────────────┘
```

**Por industria:**
- **Telco** → cuentas, planes, líneas móviles
- **Banco** → cuentas, productos financieros, tarjetas
- **Airline** → cuentas de viajero, vuelos disponibles, reservas

---

## Estructura del Repositorio

```
connect-customer-industry-poc/
├── general-localization/       # CX-LANG-UTILS — cola localizada, prompts/agentes i18n, logging
├── agentic-cx-telco/           # CX-TELCO-* (6 stacks) — demo telecomunicaciones
├── agentic-cx-bank/            # CX-BANCO-* (6 stacks) — demo banca
├── agentic-cx-airline/         # CX-AIRLINE-* (6 stacks) — demo aerolínea
├── cdk_constructs/             # Constructs CDK compartidos (AgentCore, Connect, webhosting)
├── instructions.md             # Guía de despliegue paso a paso
└── README.md                   # Este archivo
```

Cada app de industria contiene:
```
agentic-cx-{industria}/
├── config.py                   # Configuración centralizada (IDs, nombres, feature flags)
├── apis/                       # API Gateway REST API + OpenAPI spec
├── databases/                  # DynamoDB tables + seed data
├── lambdas/                    # Lambda handlers (por dominio)
├── connect_ai_agents/          # Prompts YAML de orquestación (voz/chat/assist)
├── connect/                    # Agent toolset (MCP tools + Retrieve + Escalate)
├── knowledge_bases/            # Artículos KB (es/pt/en) + scripts de tagging/asociación
├── flows/                      # Contact flows (JSON, Flow Language)
├── views/                      # Customer-managed views (formularios, guías paso a paso)
├── website/                    # Sitio estático (Vite) con widget de chat
└── agentic_cx_{industria}/     # CDK stacks (6 fases)
```

---

## Despliegue

Consulta **[instructions.md](./instructions.md)** para la guía completa de despliegue paso a paso, incluyendo:

- Prerrequisitos (CDK bootstrap, virtualenvs, credenciales)
- Creación de la instancia de Connect y el asistente de Q in Connect
- Despliegue de `general-localization` (una sola vez)
- Despliegue de cada industria (6 stacks por app)
- Post-despliegue: tagging de KB, asociación de guías, perfiles de seguridad, bot Lex, widget de chat

---

## Personalización

### Modificar los Prompts de los AI Agents

Los prompts de orquestación son archivos YAML que definen la personalidad, las reglas y el comportamiento del agente:

```
connect_ai_agents/{industria}-selfservice-voice/prompts/   # Prompt de voz
connect_ai_agents/{industria}-selfservice-chat/prompts/    # Prompt de chat
connect_ai_agents/{industria}-agent-assist-es/prompts/     # Prompt de agent-assist
```

Cada prompt tiene secciones editables:
- **`<identity>`** — Personalidad y tono del agente
- **`<core_behavior>`** — Reglas de negocio numeradas (identificación, escalación, confirmación)
- **`<customer_info>`** — Variables de sesión inyectadas por el flujo
- **`<security>`** — Guardrails (no revelar sistema, no dar consejos legales/médicos)

Después de editar un prompt: `cdk deploy CX-{INDUSTRIA}-AGENTS` y luego **publicar una nueva versión** del agente en la consola.

### Cambiar la Voz

La voz se configura en el **bot Lex V2** (Nova Sonic v2 unified speech). Para cambiar de voz:

1. En la consola de Amazon Lex → tu bot → cada locale → **Voice settings**
2. Selecciona la voz deseada (p. ej. Katie para políglota, Lupe para español, etc.)
3. Recompila el locale

Las voces de nueva generación (Katie, Ruth, Stephen) son expresivas y políglota — una sola voz maneja múltiples idiomas sin cambiar de locale.

### Modificar las Herramientas MCP

Las herramientas que el agente puede invocar se definen en dos lugares:

1. **`apis/openapi/openapi.yaml`** — El spec OpenAPI define las operaciones (cada `operationId` se convierte en una herramienta MCP)
2. **`connect/agent_tools.py`** — Las instrucciones y ejemplos por herramienta que guían al agente sobre cuándo y cómo usar cada tool

Para agregar una nueva herramienta: añade el endpoint en la API + Lambda, agrega el `operationId` al OpenAPI, regístralo en `config.AI_AGENT_MCP_OPERATIONS`, y añade la guía en `agent_tools.py`.

### Modificar la Knowledge Base

Los artículos viven en `knowledge_bases/{industria}/entries/{idioma}/` como archivos `.txt`. Para agregar contenido:

1. Crea un `.txt` en la carpeta del idioma correspondiente (es/, pt/, en/)
2. Redespliega `CX-{INDUSTRIA}-KB` (sube los archivos al bucket S3)
3. Espera el sync y ejecuta `python knowledge_bases/tag_kb_content.py --wait`

---

## Observabilidad

### Logging de AI Agents (CloudWatch)

El stack `CX-LANG-UTILS` configura la entrega centralizada de **EVENT_LOGS** del asistente de Q in Connect a CloudWatch Logs. Controlado por `config.ENABLE_AGENT_LOGS`:

- **Log group:** `/aws/connect/wisdom/{assistant-id}/event-logs`
- **Contenido:** Cada invocación del agente, tool calls, resultados de Retrieve, escalaciones, y completions
- **Uso:** Depurar por qué un agente eligió cierta herramienta, verificar que las citaciones son correctas, auditar escalaciones

### Visor de Datos Demo

Cada sitio web expone un endpoint `/datos` (Lambda + CloudFront) que renderiza las tablas DynamoDB del backend como HTML — útil para verificar que los datos semilla están correctos sin abrir la consola de DynamoDB.

### Contact Lens / Analytics

El flujo inbound habilita grabación y analítica por canal. Contact Lens proporciona transcripción en tiempo real, análisis de sentimiento, y detección de temas — integrado con el flujo de escalación.

---

## Decomisionar el Proyecto

Para eliminar todos los recursos desplegados:

```bash
# 1. Destruir los stacks de cada industria (en orden inverso)
cd agentic-cx-{industria}
source .venv/bin/activate
cdk destroy --all

# 2. Destruir general-localization
cd ../general-localization
source .venv/bin/activate
cdk destroy

# 3. Limpieza manual (si aplica):
#    - Eliminar el widget de chat en la consola de Connect
#    - Eliminar las content associations de la guía (associate_guide.py --delete, o manual)
#    - Vaciar los buckets S3 antes de destroy si CDK no puede eliminarlos
#    - Revisar que no queden security profiles huérfanos en la instancia
```

> **Nota:** Las tablas DynamoDB y los buckets S3 de la KB están configurados con `RemovalPolicy.DESTROY` (demo). En producción, cámbialos a `RETAIN`.

> **Orden de destrucción:** Destruye las industrias primero (sus flujos referencian el módulo init de `CX-LANG-UTILS`). Si destruyes `CX-LANG-UTILS` primero, el `cdk destroy` de la industria puede fallar al no encontrar el parámetro SSM `/flows/init/es`.

---

## Licencia

Este proyecto es una prueba de concepto para demostraciones. Consulta el archivo LICENSE (si existe) para los términos de uso.
