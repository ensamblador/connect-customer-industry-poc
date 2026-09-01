# Instrucciones de despliegue — Connect Customer Industry PoC

> 🌐 **Idiomas:** **Español** (este archivo) · [English](./instructions-en.md)

Configuración de extremo a extremo para las apps CDK de este repositorio:

- **`general-localization/`** → stack **`CX-LANG-UTILS`** (flujo de cola localizado + prompts/agentes utilitarios de Q in Connect por locale, más el logging centralizado de los agentes de IA en CloudWatch).
- **`agentic-cx-{industria}/`** → seis stacks **`CX-{INDUSTRIA}-*`** (backend MCP de la industria, base de conocimiento, recursos de soporte de Connect, agentes de IA, flujos de contacto, sitio web).

> **Industrias disponibles:** `telco`, `banco`, `airline`. Esta guía es **genérica**: sustituye `{industria}` por una de ellas (y `{INDUSTRIA}` por `TELCO`, `BANCO` o `AIRLINE` en los nombres de stack) según la app que despliegues. Todas las apps de industria son estructuralmente idénticas (re-tematizan la misma arquitectura de referencia); solo cambian los datos de dominio (KB, tablas, guía, sitio). Despliega `CX-LANG-UTILS` **una sola vez** (paso 2) y luego repite los pasos 3–7 para cada industria que quieras.

Los pasos marcados **[MANUAL]** se hacen a mano en una consola; los pasos **[SCRIPT]** ejecutan un script auxiliar; todo lo demás es `cdk deploy`. Usa una sola cuenta AWS + región para todo el recorrido — los scripts auxiliares y el contrato SSM entre stacks resuelven contra el perfil/región activos en tu shell.

> **Script de asociación de la guía — unificado.** En cada app, la guía paso a paso (que Q in Connect ofrece cuando el cliente menciona un tema específico) se vincula a su artículo de la KB con un **único script compartido, `knowledge_bases/associate_guide.py`**, idéntico en todos los proyectos. El script resuelve el nombre del flujo de la guía y el texto de coincidencia del contenido desde los constantes **estándar** `GUIDE_FLOW_NAME` y `GUIDE_CONTENT_MATCH` del `config.py` de cada app, así que **hace automáticamente las asociaciones que corresponden a esa industria** — asociando todas las copias por idioma (es/pt/en) del artículo, de forma idempotente.

---

## 0. Prerrequisitos

- Node.js + npm (para el CLI de CDK y el build del sitio con Vite).
- Python 3 con un virtualenv **por app CDK** (`agentic-cx-{industria}/.venv`, `general-localization/.venv`). Créalo con `python3 -m venv .venv` dentro de cada app antes del primer despliegue.
- Credenciales de AWS disponibles en tu entorno (p. ej. `AWS_PROFILE` / SSO). Los scripts auxiliares usan `boto3.client(...)` directamente y heredan la región/perfil de tu shell — **no** aceptan `--profile`/`--region`.
- Las tres **variables de entorno de identidad de Connect** exportadas en tu shell — `INSTANCE_ALIAS`, `INSTANCE_ID`, `ASSISTANT_ID` (ver el paso 0a).
- CLI de AWS CDK (`npm i -g aws-cdk` o usa `npx cdk`).

```bash
# una vez por cuenta/región de AWS — usa la forma explícita aws://<account-id>/<region>
cdk bootstrap #opcional account id y region: cdk bootstrap aws://123456789012/us-east-1
```

Crea el virtualenv de cada app CDK que vayas a desplegar (una sola vez por app):

```bash
# general-localization
cd general-localization 
python3 -m venv .venv 
source .venv/bin/activate 
pip install -r requirements.txt
cd ..
deactivate

# una por industria: telco / banco / airline
cd agentic-cx-{industria} 
python3 -m venv .venv 
source .venv/bin/activate
pip install -r requirements.txt
cd ..
deactivate
```

### 0a. Identidad de Connect vía variables de entorno

Los ids de la instancia de Connect y del asistente **no viven en el repositorio**: los cuatro `config.py` los leen del entorno como variables **obligatorias** y lanzan `ConfigError` al importarse si falta alguna. Esto evita publicar valores específicos de tu cuenta (el alias contiene tu número de cuenta) y hace que un `source` olvidado detenga el despliegue con un error nombrando la variable, en vez de sintetizar un stack a medio configurar o desplegar contra la instancia equivocada.

Las tres variables son las mismas para las cuatro apps (misma instancia, mismo asistente), así que un único archivo `.env` en la raíz del repo configura todo. `.env` está en `.gitignore`; `.env.example` es la plantilla versionada:

```bash
cp .env.example .env
# edita .env con tu alias + los dos UUIDs (paso 1)
```

`.env` lleva `export` en cada línea, así que basta con hacer `source` una vez por terminal, antes de cualquier `cdk` o script auxiliar:

```bash
cd agentic-cx-{industria}
source ../.env          # equivalente: set -a; source ../.env; set +a

# comprobación rápida
echo $INSTANCE_ALIAS $INSTANCE_ID $ASSISTANT_ID
```

> Si prefieres no volver a hacer `source` en cada terminal nueva, expórtalas en tu perfil de shell o usa [direnv](https://direnv.net/), que carga `.env` automáticamente al entrar al directorio.

> **Los tests no necesitan estas variables.** Cada app trae un `conftest.py` en su raíz que rellena valores ficticios cuando no están definidas (los tests solo sintetizan plantillas, nunca llaman a AWS), así que `pytest` funciona en un shell limpio. Un valor exportado de verdad sigue teniendo prioridad.

---

## 1. [MANUAL] Crear la instancia de Amazon Connect + el asistente de IA de Q in Connect

1. En la consola de **Amazon Connect**, crea (o elige) una **instancia** de Connect. Anota su **instance id** y su **instance alias**.
2. Crea un dominio de **Q in Connect** / **asistente de IA** (el "dominio de agentes de IA"). Anota su **assistant id**.

Luego pon esos tres valores en el `.env` de la raíz del repo (**no** se editan en `config.py` — ver el paso 0a):

```bash
export INSTANCE_ALIAS=mi-alias-de-connect     # subdominio de https://<alias>.my.connect.aws
export INSTANCE_ID=00000000-0000-0000-0000-000000000000
export ASSISTANT_ID=00000000-0000-0000-0000-000000000000
```

Si necesitas recuperarlos desde la CLI:

```bash
aws connect list-instances      # -> Id (INSTANCE_ID) + Alias (INSTANCE_ALIAS)
aws qconnect list-assistants    # -> assistantId (ASSISTANT_ID)
```

Las cuatro apps (`general-localization` + las tres de industria) leen estas mismas tres variables, así que un solo `.env` en la raíz las configura todas. Cada **nombre de recurso** lleva el prefijo de su industria (`telco-*` / `banco-*` / `airline-*`), así que nunca choca con los de otra industria en la instancia compartida.

> `INSTANCE_ALIAS` construye además la `OIDC_DISCOVERY_URL` del authorizer JWT de entrada del gateway MCP de AgentCore, por eso se necesita el alias y no solo el id.

---

## 2. Desplegar `general-localization` (`CX-LANG-UTILS`)

```bash
cd general-localization
source ../.env                 # INSTANCE_ID + ASSISTANT_ID (paso 0a)
source .venv/bin/activate
pip install -r requirements.txt
cdk deploy
cd ..
```

**Despliega:**
- **Flujo de contacto de cola de cliente localizado** (`CUSTOMER_QUEUE`) que bifurca según el `LanguageCode` del contacto y reproduce un mensaje de espera + voz TTS por idioma (en/es/pt, inglés por defecto). El prompt de música de espera se resuelve por nombre en tiempo de despliegue (`connect:ListPrompts`).
- **Módulo de flujo de contacto `init-flow-es-v2`** — habilita el logging del flujo, define el flujo de cola localizado como el hook de evento `CustomerQueue`, y configura la grabación/analítica por canal.
- **Prompts de IA + agentes utilitarios de Q in Connect por locale** para cada locale no inglés habilitado en `config.LOCALES` (actualmente `es_US`): cuatro prompts (reformulación de consulta, generación de respuesta, etiquetado de intención, toma de notas) que alimentan tres agentes (Answer Recommendation, Manual Search, Note Taking).
- **Logging centralizado de los agentes de IA en CloudWatch** (controlado por `config.ENABLE_AGENT_LOGS`) — la única entrega `EVENT_LOGS` del asistente compartido hacia CloudWatch Logs vive **solo** aquí. Como el `ASSISTANT_ID` es compartido entre todas las apps de industria, y CloudWatch Logs permite una sola fuente de entrega por recurso, este logging es propiedad exclusiva de `CX-LANG-UTILS`; los stacks de industria no llevan recursos de logging.
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

> **A partir de aquí, los pasos 3–7 aplican a cualquier industria.** Sustituye `{industria}` por `telco`, `banco` o `airline`, y `{INDUSTRIA}` por `TELCO`, `BANCO` o `AIRLINE` (en los nombres de stack) según la app que estés desplegando. Repite estos pasos por cada industria.

## 3. Compilar los assets del sitio web (antes de desplegar la app)

```bash
cd agentic-cx-{industria}/website
npm install
npm run build      # produce website/dist, consumido por CX-{INDUSTRIA}-WEBSITE
cd ..
```

`config.BUILD_WEBSITE` controla el stack del sitio — debe encontrar `website/dist` en tiempo de synth. (Volverás a compilar + redesplegar el sitio en el paso 7, después de cablear el widget de chat.)

---

## 4. Desplegar los stacks de `agentic-cx-{industria}`

**Prerrequisito:** `CX-LANG-UTILS` (paso 2) ya debe estar desplegado — el flujo inbound de la industria consume el parámetro SSM externo `/flows/init/es` (el módulo `init-flow-es-v2`) como su módulo de inicio.

```bash
cd agentic-cx-{industria}
source ../.env            # INSTANCE_ALIAS + INSTANCE_ID + ASSISTANT_ID (paso 0a)
source .venv/bin/activate
cdk diff                 # puerta de verificación
cdk deploy --all          # o desplegar fase por fase (orden abajo)
```

Orden de fases (impuesto por `add_dependency`, solo ordenamiento — los valores cruzan stacks vía SSM, nunca `Fn::ImportValue`):

| Orden | Stack | Qué despliega |
|---|---|---|
| 1 | **`CX-{INDUSTRIA}-MCP`** | Tablas DynamoDB + datos semilla, el backend Lambda, la REST API de la industria (API key en Secrets Manager), el **gateway MCP de AgentCore** (re-expone la REST API como herramientas MCP, con proveedor de credenciales por API key + target OpenAPI inline), y las integraciones de Connect (registra el gateway como app de servidor MCP + asocia los Lambdas que consumen los flujos). |
| 1 | **`CX-{INDUSTRIA}-KB`** | Clave KMS + bucket S3 con los artículos de la KB (es/pt/en), una DataIntegration de AppIntegrations, la **base de conocimiento EXTERNAL de Q in Connect** que rastrea el bucket, y la asociación con el asistente que vincula la KB al dominio de agentes de IA. *Independiente de MCP — puede desplegarse en paralelo.* |
| 2 | **`CX-{INDUSTRIA}-CONNECT-SUPPORT`** | **Perfiles de seguridad** de los agentes de IA (self-service + agent-assist, `Wisdom.View` + `CustomViews.Access` + la concesión de herramientas MCP en tiempo de despliegue), **vistas administradas por el cliente** (formulario guiado + la vista de la guía paso a paso), el **flujo de contacto de la guía** (`GUIDE_FLOW_NAME`), y el **bot Lex V2 de paso a Q-in-Connect** (`{industria}-qconnect-bot-v2`, 3 locales, Nova Sonic v2, ARN de TestBotAlias publicado en SSM). |
| 3 | **`CX-{INDUSTRIA}-AGENTS`** | Los **prompts de IA de orquestación** y los **tres agentes de IA** — self-service **voz** + **chat** (KB Retrieve + herramientas MCP de AgentCore + Escalate/Complete; chat añade el formulario guiado) y **agent-assist** (Retrieve + superficie MCP). Consume el prefijo de herramientas MCP (Fase 1) y el id de asociación de la KB (Fase 2). |
| 4 | **`CX-{INDUSTRIA}-FLOWS`** | La **vista de traspaso** de escalamiento, el **flujo de screen-pop** (registra la vista como `DefaultAgentUI`), los **módulos de flujo** (`escalate-to-agent`, `set-customer-session-{industria}`), y el **flujo inbound de self-service en español** (crea la sesión de Wisdom, vincula el bot Lex + los tres agentes, conduce el formulario guiado, escala a un humano). Resuelve el ARN de BasicQueue por nombre en tiempo de despliegue. |
| 5 | **`CX-{INDUSTRIA}-WEBSITE`** | El sitio estático de la industria → **S3 privado + CloudFront (OAC)**, que aloja el **widget de chat** de Amazon Connect y un visor de datos de demo en **`/datos`** (un Lambda que renderiza las tablas DynamoDB de la Fase 1). Ordenado después de MCP (solo ordenamiento). |

---

## 5. [SCRIPT] Post-despliegue: etiquetar el contenido de la KB + asociar la guía

Ejecuta después de que `CX-{INDUSTRIA}-KB` termine su primer sync **asíncrono** (esto no puede ser un recurso de CloudFormation porque el crawler crea ids de contenido nuevos y sin etiquetar en cada sync). Desde `agentic-cx-{industria}/`, con el venv activo, `source ../.env` hecho (los scripts importan `config.py`, que exige las tres variables) y tu perfil/región de AWS definidos en el entorno:

```bash
# 1) Etiqueta cada ítem de contenido para que el filtro Retrieve de los agentes lo encuentre.
#    el kb-id se resuelve desde SSM automáticamente; --wait sondea hasta que la ingesta esté ACTIVE.
python knowledge_bases/tag_kb_content.py --wait --expect 21

# 2) Vincula el flujo de la guía paso a paso con su(s) artículo(s) de la KB (idempotente).
#    Script compartido: resuelve el flujo (GUIDE_FLOW_NAME) y el texto de coincidencia
#    (GUIDE_CONTENT_MATCH) desde config.py, y asocia todas las copias por idioma del artículo.
python knowledge_bases/associate_guide.py        # añade --dry-run para previsualizar
```

> Si `--expect 21` no coincide con tu conteo real de ingesta, ajústalo (o quita `--expect`) o `--wait` agotará el tiempo.

---

## 6. [MANUAL] Pasos de consola post-despliegue

Estos no tienen recurso nativo de CloudFormation y deben hacerse a mano:

1. **Adjunta el perfil de seguridad a cada agente de IA y publica una nueva versión.** En el sitio de administración de **Amazon Connect** → **AI agents** (tu dominio de Q in Connect), abre cada agente, **adjunta su perfil de seguridad**, luego **Save and Publish a new version**:
   - `{industria}-selfservice-voice-es` y `{industria}-selfservice-chat-es` → el perfil de seguridad **self-service** del proyecto (`config.AI_AGENT_SECURITY_PROFILE_NAME`)
   - `{industria}-agent-assist-es` → el perfil **agent-assist** (`config.AI_AGENT_ASSIST_SECURITY_PROFILE_NAME`)
   - Para **agent-assist**, los agentes humanos que usan el panel del asistente también deben llevar los mismos permisos (`Wisdom.View`, `CustomViews.Access`, la concesión de herramientas MCP) — las llamadas a herramientas se autorizan contra la intersección de los perfiles del agente de IA y del agente humano. (Los ids de perfil también se publican en SSM para scripting.)

   > **Obligatorio — esto es lo que autoriza las llamadas a herramientas MCP.** Las herramientas MCP de AgentCore se conceden a través del perfil de seguridad, y el agente en ejecución usa la **versión publicada**. Si el perfil no está adjunto (o lo editaste pero no publicaste una nueva versión), las llamadas a herramientas MCP fallan en la invocación con `Target entity not found` aunque el gateway/target y la REST API de backend estén sanos. Después de adjuntar el perfil, siempre **publica una nueva versión** y confirma que el flujo/binding apunte a esa versión.

2. **Toma control del bot desde Amazon Connect (alterna Lex Bot Management) — hazlo _antes_ de compilar los locales.** Como el bot se crea del lado de **Amazon Lex** (vía CDK), la instancia de Connect no refresca su enlace de Lex Bot Management automáticamente, así que el bot no será seleccionable/editable dentro de los flujos de Connect hasta que alternes la función. En la consola de **Amazon Connect** → tu instancia → **Flows** → sección **Amazon Lex Bots**:

   1. Desmarca **Enable Lex Bot Management in Amazon Connect** → **Save** (deshabilitar → guardar).
   2. Vuelve a marcar **Enable Lex Bot Management in Amazon Connect** → **Save** (habilitar → guardar).

   Connect crea el **service role** y el **service-linked role** por ti como parte de esta alternancia, y `{industria}-qconnect-bot-v2` se vuelve visible para la instancia. (**No** necesitas crear el service-linked role de Lex a mano.)

3. **Compila los locales del bot Lex** (consola de Amazon Lex V2): abre `{industria}-qconnect-bot-v2` y compila `en_US`, `es_US`, `pt_BR` **si no están ya en estado BUILD** (el estado se muestra junto a cada locale). Intencionalmente no se auto-compilan para mantener los despliegues rápidos; una vez compilados, el TestBotAlias (`TSTALIASID`) sirve DRAFT y el flujo inbound (ya vinculado vía SSM) funciona. Si los tres locales ya muestran **Built**, puedes omitir este paso.

   > **Habilita los locales también en el TestBotAlias.** Después de compilar, asegúrate de que cada locale (`en_US`/`es_US`/`pt_BR`) esté habilitado en el **TestBotAlias**. Si un locale no está habilitado en el alias que usa el flujo, el chat falla en el paso `ConnectParticipantWithLexBot` con `The BotAliasId TSTALIASID does not have Language <locale> enabled`. Algunas apps cablean esto automáticamente con un pequeño custom resource en `CX-{INDUSTRIA}-CONNECT-SUPPORT`; si la tuya no, confírmalo en la consola (Aliases → TestBotAlias → Languages) o vía `aws lexv2-models update-bot-alias`. En todos los casos aún debes **compilar** los tres locales en la consola de Lex si no están ya compilados.

---

## 7. [MANUAL] Cablear el widget de chat en el sitio web

1. En la consola de **Amazon Connect**, crea un **widget de comunicaciones de chat**. Al crearlo, añade tus **orígenes aprobados** para que el widget pueda cargar:
   - `http://localhost` (y/o `http://localhost:<puerto>`) para desarrollo local.
   - El dominio de CloudFront del output del stack del sitio, p. ej. `https://{id}.cloudfront.net` (el output `WebsiteDistributionDomainName` / `WebsiteDataViewerPath` de `CX-{INDUSTRIA}-WEBSITE`).

   > El widget fallará silenciosamente al cargar en cualquier origen que no esté en esta lista. Como el dominio de CloudFront no se conoce hasta que el stack del sitio se despliega, normalmente creas el widget, despliegas el sitio, y luego regresas a añadir el origen real `*.cloudfront.net` (un dominio personalizado también funciona una vez configurado).
2. Abre `agentic-cx-{industria}/website/index.html` y **actualiza el widget de Connect**: reemplaza el contenido **entre** estos dos marcadores con tu snippet de widget generado, tal cual — deja los marcadores en su lugar:

   ```html
   <!--REPLACE WITH CONNECT WIDGET AS IS (BELOW THIS LINE)-->
   [AQUÍ VA EL CONTENIDO DE TU WIDGET]
   <!--END OF CONNECT WIDGET (ABOVE THIS LINE)-->
   ```

   > **Pasar el email del usuario logueado como atributo de contacto.** El sitio registra `window._connectContactAttrs` como el objeto `contactAttributes` del widget **una sola vez**, y luego muta esa misma referencia de objeto al iniciar/cerrar sesión. Mantén ese patrón: si construyes un objeto nuevo en cada llamada a `contactAttributes`, el widget nunca ve el email posterior al login, y la búsqueda de cliente no puede personalizar el contacto.

3. Recompila y redespliega el sitio:

```bash
cd agentic-cx-{industria}/website
npm run build
cd ..
cdk deploy CX-{INDUSTRIA}-WEBSITE
```

---

## Pasos manuales / de script de un vistazo

| # | Tipo | Paso |
|---|---|---|
| 0 | manual | `cdk bootstrap aws://<account-id>/<region>` (por cuenta/región) |
| 0 | manual | `python3 -m venv .venv` en cada app CDK (`general-localization`, `agentic-cx-{industria}`) |
| 0a | manual | `cp .env.example .env` en la raíz del repo, rellenarlo, y `source ../.env` en cada shell antes de `cdk` o los scripts |
| 1 | manual | Crear la instancia de Connect + el asistente de Q in Connect; poner `INSTANCE_ALIAS` / `INSTANCE_ID` / `ASSISTANT_ID` en `.env` |
| 2 | manual | Definir los agentes utilitarios localizados como predeterminados del dominio (Answer Recommendation / Manual Search / Note Taking) |
| 3 | manual | `npm install && npm run build` del sitio antes del despliegue de cada app |
| 5 | script | `tag_kb_content.py --wait` (el KB id se auto-resuelve desde SSM) |
| 5 | script | `associate_guide.py` — script único compartido; asocia la guía que corresponde a cada industria (resuelto desde `GUIDE_FLOW_NAME` / `GUIDE_CONTENT_MATCH` en `config.py`) |
| 6 | manual | Adjuntar los perfiles de seguridad de la Fase 3 a los tres agentes de IA (autoriza las herramientas MCP), luego **publicar una nueva versión** — sin esto, las llamadas a herramientas fallan con `Target entity not found` |
| 6 | manual | Tomar control del bot en Connect: Flows → alternar Lex Bot Management off+save, on+save (crea los roles) — hazlo **antes** de compilar los locales |
| 6 | manual | Compilar los locales `en_US` / `es_US` / `pt_BR` del bot Lex (si no están ya en estado **Built**) y confirmar que estén habilitados en el TestBotAlias |
| 7 | manual | Crear el widget de chat (añadir `http://localhost` + el output `https://{id}.cloudfront.net` como **orígenes aprobados**), pegarlo entre los marcadores del widget en `website/index.html`, recompilar + redesplegar el sitio |

> Repite los pasos **3–7** por cada industria (`telco`, `banco`, `airline`) que quieras desplegar, sustituyendo `{industria}` / `{INDUSTRIA}`.

> El detalle completo por stack, el contrato SSM entre stacks, y la referencia de configuración viven en el `README.md` de cada app (`agentic-cx-{industria}/README.md`).

> Para demostrar cada app una vez desplegada: `agentic-cx-{industria}/DEMO-WALKTHROUGH.md` (inglés: `DEMO-WALKTHROUGH-en.md`).
