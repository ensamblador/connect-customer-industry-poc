> 🌎 **English:** [if you want to see the English version, click here (`instructions-en.md`)](instructions-en.md)

# Instrucciones de despliegue — Connect Customer Industry PoC

Configuración de extremo a extremo para las apps CDK de este repositorio:

- **`general-localization/`** → stack **`CX-LANG-UTILS`** (flujo de cola localizado + prompts/agentes utilitarios de Q in Connect por locale, más el logging centralizado de los agentes de IA en CloudWatch).
- **`agentic-cx-telco/`** → seis stacks **`CX-TELCO-*`** (backend MCP de telco, base de conocimiento, recursos de soporte de Connect, agentes de IA, flujos de contacto, sitio web).
- **`agentic-cx-bank/`** → seis stacks **`CX-BANCO-*`** (backend MCP de banca retail, base de conocimiento, recursos de soporte de Connect, agentes de IA, flujos de contacto, sitio web).

Los pasos marcados **[MANUAL]** se hacen a mano en una consola; los pasos **[SCRIPT]** ejecutan un script auxiliar; todo lo demás es `cdk deploy`. Usa una sola cuenta AWS + región para todo el recorrido — los scripts auxiliares y el contrato SSM entre stacks resuelven contra el perfil/región activos en tu shell.

> Las apps de telco y banco son estructuralmente idénticas (ambas re-tematizan la misma arquitectura de referencia). Esta guía recorre telco de extremo a extremo; la sección **[App de banco](#8-app-de-banco-cx-banco)** al final lista solo lo que cambia.

---

## 0. Prerrequisitos

- Node.js + npm (para el CLI de CDK y el build del sitio con Vite).
- Python 3 con un virtualenv por app CDK (`agentic-cx-telco/.venv`, `agentic-cx-bank/.venv`, `general-localization/.venv`).
- Credenciales de AWS disponibles en tu entorno (p. ej. `AWS_PROFILE` / SSO). Los scripts auxiliares usan `boto3.client(...)` directamente y heredan la región/perfil de tu shell — **no** aceptan `--profile`/`--region`.
- CLI de AWS CDK (`npm i -g aws-cdk` o usa `npx cdk`).

```bash
# una vez por cuenta/región de AWS
cdk bootstrap
```

---

## 1. [MANUAL] Crear la instancia de Amazon Connect + el asistente de IA de Q in Connect

1. En la consola de **Amazon Connect**, crea (o elige) una **instancia** de Connect. Anota su **instance id** y su **instance alias**.
2. Crea un dominio de **Q in Connect** / **asistente de IA** (el "dominio de agentes de IA"). Anota su **assistant id**.

Luego actualiza la configuración en cada app para que apunten a la instancia real:

- `agentic-cx-telco/config.py` y `agentic-cx-bank/config.py` → define `INSTANCE_ALIAS`, `INSTANCE_ID`, `ASSISTANT_ID`.
  - `HAS_REAL_INSTANCE` pasa a `True` automáticamente en cuanto `INSTANCE_ALIAS` deja de ser el placeholder; controla cada recurso ligado a la instancia.
- `general-localization/config.py` → define `INSTANCE_ID`, `ASSISTANT_ID` (la misma instancia/asistente).

---

## 2. Desplegar `general-localization` (`CX-LANG-UTILS`)

```bash
cd general-localization
source .venv/bin/activate
pip install -r requirements.txt
cdk deploy
```

**Despliega:**
- **Flujo de contacto de cola de cliente localizado** (`CUSTOMER_QUEUE`) que bifurca según el `LanguageCode` del contacto y reproduce un mensaje de espera + voz TTS por idioma (en/es/pt, inglés por defecto). El prompt de música de espera se resuelve por nombre en tiempo de despliegue (`connect:ListPrompts`).
- **Módulo de flujo de contacto `init-flow-es-v2`** — habilita el logging del flujo, define el flujo de cola localizado como el hook de evento `CustomerQueue`, y configura la grabación/analítica por canal.
- **Prompts de IA + agentes utilitarios de Q in Connect por locale** para cada locale no inglés habilitado en `config.LOCALES` (actualmente `es_US`): cuatro prompts (reformulación de consulta, generación de respuesta, etiquetado de intención, toma de notas) que alimentan tres agentes (Answer Recommendation, Manual Search, Note Taking).
- **Logging centralizado de los agentes de IA en CloudWatch** (controlado por `config.ENABLE_AGENT_LOGS`) — la única entrega `EVENT_LOGS` del asistente compartido hacia CloudWatch Logs vive **solo** aquí. Como el `ASSISTANT_ID` es compartido entre las apps de telco y banco, y CloudWatch Logs permite una sola fuente de entrega por recurso, este logging es propiedad exclusiva de `CX-LANG-UTILS`; los stacks de industria no llevan recursos de logging.
- Publica el flujo de cola + el módulo init + los ARNs de agentes en **SSM** y los emite como **CfnOutputs**.

### 2a. [MANUAL] Definir los agentes utilitarios localizados como los predeterminados del dominio

Los tres agentes utilitarios localizados se crean en el asistente pero no quedan cableados como **agentes de IA predeterminados** automáticamente. En la consola de **Amazon Connect** → **AI agents** (tu dominio de Q in Connect) → **Default AI agents**, asígnalos por caso de uso (luego **Save**):

| Caso de uso | Agente predeterminado |
|---|---|
| Answer Recommendation | `localized-answer-recommendation-es_US` |
| Manual Search | `localized-manual-search-es_US` |
| Note Taking | `localized-note-taking-es_US` |

Deja los demás casos de uso (Self Service, Email *, Case Summarization, Agent Assistance) en sus valores existentes/predeterminados. Repite para cada locale adicional que habilites en `config.LOCALES`.

---

## 3. Compilar los assets del sitio web (antes de desplegar la app de telco)

```bash
cd agentic-cx-telco/website
npm install
npm run build      # produce website/dist, consumido por CX-TELCO-WEBSITE
```

`config.BUILD_WEBSITE` controla el stack del sitio — debe encontrar `website/dist` en tiempo de synth. (Volverás a compilar + redesplegar el sitio en el paso 7, después de cablear el widget de chat.)

---

## 4. Desplegar los stacks de `agentic-cx-telco`

```bash
cd agentic-cx-telco
source .venv/bin/activate
pip install -r requirements.txt
cdk synth                 # puerta de verificación
cdk deploy --all          # o desplegar fase por fase (orden abajo)
```

Orden de fases (impuesto por `add_dependency`, solo ordenamiento — los valores cruzan stacks vía SSM, nunca `Fn::ImportValue`):

| Orden | Stack | Qué despliega |
|---|---|---|
| 1 | **`CX-TELCO-MCP`** | Tablas DynamoDB (`accounts`/`plans`/`lines`) + datos semilla, el backend Lambda (`accounts`/`plans`/`lines`/`ai_session`), la REST API de Telco (API key en Secrets Manager), el **gateway MCP de AgentCore** (re-expone la REST API como herramientas MCP, con proveedor de credenciales por API key + target OpenAPI inline), y las integraciones de Connect (registra el gateway como app de servidor MCP + asocia los Lambdas `plans`/`ai_session`). |
| 1 | **`CX-TELCO-KB`** | Clave KMS + bucket S3 con los artículos HTML de la KB (es/pt/en), una DataIntegration de AppIntegrations, la **base de conocimiento EXTERNAL de Q in Connect** que rastrea el bucket, y la asociación con el asistente que vincula la KB al dominio de agentes de IA. *Independiente de MCP — puede desplegarse en paralelo.* |
| 2 | **`CX-TELCO-CONNECT-SUPPORT`** | **Perfiles de seguridad** de los agentes de IA (self-service + agent-assist, `Wisdom.View` + `CustomViews.Access` + la concesión de herramientas MCP en tiempo de despliegue), **vistas administradas por el cliente** (formulario guiado de nueva línea, guía de activación eSIM), el **flujo de contacto de la guía eSIM**, y el **bot Lex V2 de paso a Q-in-Connect** (`telco-qconnect-bot-v2`, 3 locales, Nova Sonic v2, ARN de TestBotAlias publicado en SSM). |
| 3 | **`CX-TELCO-AGENTS`** | Los **prompts de IA de orquestación** y los **tres agentes de IA** — self-service **voz** + **chat** (KB Retrieve + 9 herramientas MCP de AgentCore + Escalate/Complete; chat añade la guía de nueva línea) y **agent-assist** (Retrieve + superficie MCP). Consume el prefijo de herramientas MCP (Fase 1) y el id de asociación de la KB (Fase 2). |
| 4 | **`CX-TELCO-FLOWS`** | La **vista de traspaso** de escalamiento, el **flujo de screen-pop** (registra la vista como `DefaultAgentUI`), los **módulos de flujo** (`escalate-to-agent`, `set-customer-session-telco`), y el **flujo inbound de self-service en español** (crea la sesión de Wisdom, vincula el bot Lex + los tres agentes, conduce el formulario guiado de nueva línea, escala a un humano). Resuelve el ARN de BasicQueue por nombre en tiempo de despliegue. |
| 5 | **`CX-TELCO-WEBSITE`** | El sitio estático "Latam Telco" → **S3 privado + CloudFront (OAC)**, que aloja el **widget de chat** de Amazon Connect y un visor de datos de demo en **`/datos`** (un Lambda que renderiza las tablas DynamoDB de la Fase 1). Ordenado después de MCP (solo ordenamiento). |

---

## 5. [SCRIPT] Post-despliegue: etiquetar el contenido de la KB + cablear la guía eSIM

Ejecuta después de que `CX-TELCO-KB` termine su primer sync **asíncrono** (esto no puede ser un recurso de CloudFormation porque el crawler crea ids de contenido nuevos y sin etiquetar en cada sync). Desde `agentic-cx-telco/`, con el venv activo y tu perfil/región de AWS definidos en el entorno:

```bash
# 1) Etiqueta cada ítem de contenido para que el filtro Retrieve de los agentes lo encuentre.
#    el kb-id se resuelve desde SSM automáticamente; --wait sondea hasta que la ingesta esté ACTIVE.
python knowledge_bases/tag_kb_content.py --wait --expect 21

# 2) Vincula el flujo de la guía paso a paso de eSIM con su artículo de la KB (idempotente).
python knowledge_bases/associate_esim_guide.py        # añade --dry-run para previsualizar
```

> Si `--expect 21` no coincide con tu conteo real de ingesta, ajústalo (o quita `--expect`) o `--wait` agotará el tiempo.

---

## 6. [MANUAL] Pasos de consola post-despliegue

Estos no tienen recurso nativo de CloudFormation y deben hacerse a mano:

1. **Adjunta el perfil de seguridad a cada agente de IA y publica una nueva versión.** En el sitio de administración de **Amazon Connect** → **AI agents** (tu dominio de Q in Connect), abre cada agente, **adjunta su perfil de seguridad**, luego **Save and Publish a new version**:
   - `telco-selfservice-voice-es` y `telco-selfservice-chat-es` → `telco-selfservice-ai-agent-iac`
   - `telco-agent-assist-es` → `telco-agent-assist-iac`
   - Para **agent-assist**, los agentes humanos que usan el panel del asistente también deben llevar los mismos permisos (`Wisdom.View`, `CustomViews.Access`, la concesión de herramientas MCP) — las llamadas a herramientas se autorizan contra la intersección de los perfiles del agente de IA y del agente humano. (Los ids de perfil también se publican en SSM para scripting.)

   > **Obligatorio — esto es lo que autoriza las llamadas a herramientas MCP.** Las herramientas MCP de AgentCore se conceden a través del perfil de seguridad, y el agente en ejecución usa la **versión publicada**. Si el perfil no está adjunto (o lo editaste pero no publicaste una nueva versión), las llamadas a herramientas MCP fallan en la invocación con `Target entity not found` aunque el gateway/target y la REST API de backend estén sanos. Después de adjuntar el perfil, siempre **publica una nueva versión** y confirma que el flujo/binding apunte a esa versión.

2. **Toma control del bot desde Amazon Connect (alterna Lex Bot Management) — hazlo _antes_ de compilar los locales.** Como el bot se crea del lado de **Amazon Lex** (vía CDK), la instancia de Connect no refresca su enlace de Lex Bot Management automáticamente, así que el bot no será seleccionable/editable dentro de los flujos de Connect hasta que alternes la función. En la consola de **Amazon Connect** → tu instancia → **Flows** → sección **Amazon Lex Bots**:

   1. Desmarca **Enable Lex Bot Management in Amazon Connect** → **Save** (deshabilitar → guardar).
   2. Vuelve a marcar **Enable Lex Bot Management in Amazon Connect** → **Save** (habilitar → guardar).

   Connect crea el **service role** y el **service-linked role** por ti como parte de esta alternancia, y `telco-qconnect-bot-v2` se vuelve visible para la instancia. (**No** necesitas crear el service-linked role de Lex a mano.)

3. **Compila los locales del bot Lex** (consola de Amazon Lex V2): abre `telco-qconnect-bot-v2` y compila `en_US`, `es_US`, `pt_BR`. Intencionalmente no se auto-compilan para mantener los despliegues rápidos; una vez compilados, el TestBotAlias (`TSTALIASID`) sirve DRAFT y el flujo inbound (ya vinculado vía SSM) funciona.

   > **Habilita los locales también en el TestBotAlias.** Después de compilar, asegúrate de que cada locale (`en_US`/`es_US`/`pt_BR`) esté habilitado en el **TestBotAlias**. Si un locale no está habilitado en el alias que usa el flujo, el chat falla en el paso `ConnectParticipantWithLexBot` con `The BotAliasId TSTALIASID does not have Language <locale> enabled`. La app de banco cablea esto automáticamente con un pequeño custom resource; para telco confírmalo en la consola (Aliases → TestBotAlias → Languages) o vía `aws lexv2-models update-bot-alias`.

---

## 7. [MANUAL] Cablear el widget de chat en el sitio web

1. En la consola de **Amazon Connect**, crea un **widget de comunicaciones de chat**. Al crearlo, añade tus **orígenes aprobados** para que el widget pueda cargar:
   - `http://localhost` (y/o `http://localhost:<puerto>`) para desarrollo local.
   - El dominio de CloudFront del output del stack del sitio, p. ej. `https://{id}.cloudfront.net` (el output `WebsiteDistributionDomainName` / `WebsiteDataViewerPath` de `CX-TELCO-WEBSITE` / `CX-BANCO-WEBSITE`).

   > El widget fallará silenciosamente al cargar en cualquier origen que no esté en esta lista. Como el dominio de CloudFront no se conoce hasta que el stack del sitio se despliega, normalmente creas el widget, despliegas el sitio, y luego regresas a añadir el origen real `*.cloudfront.net` (un dominio personalizado también funciona una vez configurado).
2. Abre `agentic-cx-telco/website/index.html` y **actualiza el widget de Connect**: reemplaza el contenido **entre** estos dos marcadores con tu snippet de widget generado, tal cual — deja los marcadores en su lugar:

   ```html
   <!--REPLACE WITH CONNECT WIDGET AS IS (BELOW THIS LINE)-->
   [AQUÍ VA EL CONTENIDO DE TU WIDGET]
   <!--END OF CONNECT WIDGET (ABOVE THIS LINE)-->
   ```

   > **Pasar el email del usuario logueado como atributo de contacto.** El sitio registra `window._connectContactAttrs` como el objeto `contactAttributes` del widget **una sola vez**, y luego muta esa misma referencia de objeto al iniciar/cerrar sesión. Mantén ese patrón: si construyes un objeto nuevo en cada llamada a `contactAttributes`, el widget nunca ve el email posterior al login, y la búsqueda de cliente no puede personalizar el contacto.

3. Recompila y redespliega el sitio:

```bash
cd agentic-cx-telco/website
npm run build
cd ..
cdk deploy CX-TELCO-WEBSITE
```

---

## 8. App de banco (`CX-BANCO-*`)

La app de banco (`agentic-cx-bank/`) refleja telco paso a paso. Despliégala de la misma forma, sustituyendo los nombres de abajo. **Tiene un prerrequisito extra: `CX-LANG-UTILS` debe estar ya desplegado**, porque el flujo inbound de banco consume el parámetro SSM externo `/flows/init/es` (el módulo `init-flow-es-v2`) publicado por `general-localization` como su módulo de inicio.

Orden de despliegue: **`CX-BANCO-MCP` → `CX-BANCO-KB` → `CX-BANCO-CONNECT-SUPPORT` → `CX-BANCO-AGENTS` → `CX-BANCO-FLOWS` → `CX-BANCO-WEBSITE`** (las Fases 1 y 2 son mutuamente independientes).

Lo que difiere de telco:

| Concepto | Telco | Banco |
|---|---|---|
| Dominio del backend | accounts / plans / lines | accounts / products / cards |
| Tablas DynamoDB | `accounts` / `plans` / `lines` | `banco-accounts` / `banco-products` / `banco-cards` |
| REST API / gateway | `telco-api` | `banco-api` / `banco-mcp-server` |
| Formulario guiado + guía | formulario de nueva línea + guía de activación eSIM | formulario de solicitud de tarjeta + guía de activar tarjeta |
| Bot Lex | `telco-qconnect-bot-v2` | `banco-qconnect-bot-v2` |
| Perfiles de seguridad | `telco-selfservice-ai-agent-iac` / `telco-agent-assist-iac` | `banco-selfservice-ai-agent` / `banco-agent-assist-iac` |
| Agentes de IA | `telco-selfservice-voice-es` / `-chat-es` / `telco-agent-assist-es` | `banco-selfservice-voice-es` / `-chat-es` / `banco-agent-assist-es` |
| Sitio web | "Latam Telco" | "Latam Banco" |
| Script de la guía | `associate_esim_guide.py` | `associate_activate_card_guide.py` |
| Segmentación de Retrieve | `industry=telco` | `industry=bank` Y `language=es` |

Scripts post-despliegue de banco (después del sync de `CX-BANCO-KB`):

```bash
cd agentic-cx-bank
source .venv/bin/activate
python knowledge_bases/tag_kb_content.py --wait --expect 21
python knowledge_bases/associate_activate_card_guide.py        # añade --dry-run para previsualizar
```

Luego repite los mismos pasos de consola **[MANUAL]** de las secciones 6 y 7 (adjuntar + publicar los perfiles de seguridad, alternar Lex Bot Management, compilar + habilitar los tres locales de Lex en el TestBotAlias, y cablear el widget de chat en `agentic-cx-bank/website/index.html`).

> La habilitación de locales en el TestBotAlias del bot Lex de banco la maneja automáticamente un custom resource en `CX-BANCO-CONNECT-SUPPORT`, así que el chat funciona sin la alternancia manual de locales del alias. Aun así necesitas **compilar** los tres locales en la consola de Lex.

---

## Pasos manuales / de script de un vistazo

| # | Tipo | Paso |
|---|---|---|
| 0 | manual | `cdk bootstrap` (por cuenta/región) |
| 1 | manual | Crear la instancia de Connect + el asistente de Q in Connect; actualizar `config.py` en cada app |
| 2 | manual | Definir los agentes utilitarios localizados como predeterminados del dominio (Answer Recommendation / Manual Search / Note Taking) |
| 3 | manual | `npm install && npm run build` del sitio antes del despliegue de cada app |
| 5 | script | `tag_kb_content.py --wait` (el KB id se auto-resuelve desde SSM) |
| 5 | script | `associate_esim_guide.py` (telco) / `associate_activate_card_guide.py` (banco) |
| 6 | manual | Adjuntar los perfiles de seguridad de la Fase 3 a los tres agentes de IA (autoriza las herramientas MCP), luego **publicar una nueva versión** — sin esto, las llamadas a herramientas fallan con `Target entity not found` |
| 6 | manual | Tomar control del bot en Connect: Flows → alternar Lex Bot Management off+save, on+save (crea los roles) — hazlo **antes** de compilar los locales |
| 6 | manual | Compilar los locales `en_US` / `es_US` / `pt_BR` del bot Lex y confirmar que estén habilitados en el TestBotAlias |
| 7 | manual | Crear el widget de chat (añadir `http://localhost` + el output `https://{id}.cloudfront.net` como **orígenes aprobados**), pegarlo entre los marcadores del widget en `website/index.html`, recompilar + redesplegar el sitio |

> El detalle completo por stack, el contrato SSM entre stacks, y la referencia de configuración viven en el `README.md` de cada app (`README-en.md` para la versión en inglés).
