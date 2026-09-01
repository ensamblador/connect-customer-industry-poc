# Script de Demo — Banco PoC

> 🌐 **Idiomas:** **Español** (este archivo) · [English](./DEMO-WALKTHROUGH-en.md)

Guía paso a paso para demostrar las capacidades de la PoC bancaria. Indica las preguntas a usar y qué esperar en cada paso, sin guionizar las respuestas del agente (son generadas en vivo y varían).

---

## Datos de Prueba

Antes de comenzar, familiarízate con los datos sintéticos disponibles:

| Cliente | Email | Teléfono | Producto | Saldo | Vencimiento | Estado |
|---------|-------|----------|----------|-------|-------------|--------|
| María González | maria.gonzalez@example.com | +12065550101 | Cuenta Nómina | $1,540.75 | 20 jun 2026 | activa |
| James Carter | james.carter@example.com | +12065550102 | Tarjeta Clásica | $320.00 | 28 jun 2026 | activa |
| Aisha Khan | aisha.khan@example.com | +12065550103 | Tarjeta Oro | $5,820.40 | 10 jun 2026 | suspendida |
| Diego Fernández | diego.fernandez@example.com | +12065550104 | Cuenta Nómina | $980.15 | 1 jul 2026 | activa |

**Productos disponibles:**
- Cuenta Nómina: sin comisión de mantenimiento, tarjeta de débito gratuita, $0/año
- Tarjeta Clásica: pagos sin contacto y protección de compras, $30/año
- Tarjeta Oro: 2% de cashback, seguro de viaje, salas VIP, $120/año
- Tarjeta Platino: 3% de cashback, seguro premium, salas VIP y concierge, $180/año

**Tarjetas existentes:** `card-9001` (María González, Clásica, **active**, terminación 4821) y `card-9002` (Aisha Khan, Oro, **requested**, pendiente de emisión). **James Carter y Diego Fernández no tienen tarjetas** — útiles para una solicitud desde cero.

> Los datos se pueden ver en el sitio web en la ruta `/datos` (link "Datos demo" en la navegación), con las tablas *Cuentas (accounts)*, *Productos (products)* y *Tarjetas (cards)*.

---

## 1. Self-Service por Chat

### 1.1 Acceder al sitio web

1. Abre el output de CloudFormation del stack **CX-BANCO-WEBSITE** → toma el valor de `WebsiteDistributionDomainName` (dominio CloudFront, p. ej. `https://d1234abcdef.cloudfront.net`). El output `WebsiteDataViewerPath` te da directamente la URL de `/datos`.
2. Navega al sitio web. Verás la página de "Latam Banco" con secciones de cuentas, tarjetas y banca digital.

### 1.2 Simular un usuario logueado

1. Haz clic en **"Iniciar sesión"** en el header.
2. Ingresa un email de los datos de prueba, por ejemplo: `diego.fernandez@example.com`
3. Haz clic en "Entrar". El sitio guarda el email en sessionStorage y lo envía como atributo del contacto al widget de chat.

> Esto permite que el agente de IA identifique automáticamente al cliente sin preguntar.

### 1.3 Abrir el chat y conversar

Haz clic en el **widget de chat** (burbuja en la esquina inferior derecha). Se abre la ventana de conversación.

---

### Demo 1: Preguntas de Knowledge Base

El agente responde estas preguntas **con los artículos de la base de conocimiento**, no con conocimiento propio del modelo. Los artículos viven en `knowledge_bases/bank/entries/<idioma>/`, con una carpeta por idioma (`es`, `en`, `pt`): el agente recupera la entrada correspondiente al idioma en que está conversando el cliente.

Preguntas para probar:

> **Tú:** ¿Cómo activo mi tarjeta nueva?

> **Tú:** ¿Qué comisiones cobran por mantener la cuenta?

> **Tú:** ¿Cuál es el horario de las sucursales?

> **Tú:** ¿Cómo hago una transferencia a otro banco?

> **Tú:** ¿Cuál es la diferencia entre la tarjeta de débito y la de crédito?

**Qué esperar:** una respuesta redactada a partir del artículo correspondiente, en el idioma del cliente y citando la fuente recuperada. Si la pregunta no está cubierta por ningún artículo, el agente no debe inventar la respuesta.

**Otras preguntas para seguir explorando** (mismas fuentes, sin salir de la KB): qué tipos de cuenta existen y qué incluyen, pagos sin contacto, gestión de tarjetas desde la app móvil, problemas para entrar a la banca en línea, límites y tiempos de las transferencias.

---

### Demo 2: Consulta de cuenta (MCP Tools)

Estas preguntas disparan herramientas MCP que consultan la API en tiempo real.

> **Tú:** ¿Cuál es el saldo de mi cuenta?

> **Tú:** ¿Qué productos tienen disponibles?

> **Tú:** ¿Qué tarjetas tengo?

**Qué esperar:** el agente primero resuelve la cuenta a partir del email de la sesión y luego invoca la herramienta MCP. La respuesta puede ser algo como el **saldo y su fecha de vencimiento**, tomados en vivo de la API vía MCP. Verifica contra `/datos` que los valores coincidan con el registro del cliente.

**Preguntas de follow-up para probar:**

> **Tú:** ¿Cuándo vence mi próximo pago?

> **Tú:** ¿Qué tarjeta tiene la anualidad más baja?

> **Tú:** ¿Cuánto cashback da la Tarjeta Platino?

> **Tú:** ¿Tengo alguna solicitud de tarjeta en curso?

> Nota: `listProducts` acepta un filtro de anualidad máxima, así que preguntas del tipo "¿qué tarjetas cuestan menos de 50 al año?" muestran el filtrado del lado de la herramienta y no del modelo.

---

### Demo 3: Solicitar una tarjeta (Formulario guiado)

Esta demo muestra una acción determinística con **human-in-the-loop, donde el humano en el loop es el cliente**: en lugar de dejar que el modelo interprete la elección conversacionalmente, el cliente la confirma en un formulario.

> **Tú:** Quiero solicitar una tarjeta de crédito

**Qué esperar:** el agente identifica tu cuenta, avisa brevemente que va a abrir un formulario y devuelve el control al flujo. En el chat verás un **formulario con botones** para elegir una opción (o cancelar).

> **Tú:** *(Haz clic en una de las opciones del formulario)*

**Qué esperar:** el agente retoma la conversación, confirma la solicitud y te da el identificador de la nueva tarjeta con su estado inicial.

**Verificación:** navega a `/datos` en el sitio web → verás el nuevo producto o servicio con status **`requested`**.

**Follow-up opcional**, para cerrar el ciclo en la misma conversación:

> **Tú:** ¿Puedo ver mis tarjetas solicitadas?

---

## 2. Self-Service por Voz

### 2.1 Simular el login e iniciar la llamada web

1. Igual que en el chat: entra al sitio, haz clic en **"Iniciar sesión"** e ingresa `diego.fernandez@example.com`. Así la llamada llega ya identificada y el agente no tiene que preguntar quién eres.
2. En el widget de chat, haz clic en el ícono de **teléfono/llamada web** (WebRTC call).
3. El navegador pedirá acceso al **micrófono** → concédelo.
4. Se establece la llamada y escucharás una **voz agéntica** saludándote.

> **Nota:** No se requiere un número telefónico para probar. La llamada web usa el mismo flujo de self-service y ofrece las mismas capacidades que una llamada real.

### 2.2 Diálogos de voz

#### Pregunta de knowledge base

> **Tú (hablando):** "Hola, quiero saber cómo activar mi tarjeta nueva"

**Qué esperar:** una respuesta hablada basada en los artículos de la KB, en el mismo idioma en que preguntaste.

**Otras preguntas para probar por voz:** comisiones de la cuenta, horarios de sucursales, cómo hacer una transferencia, diferencias entre débito y crédito.

#### Consulta de cuenta por voz

> **Tú:** "Quiero saber cuánto tengo en mi cuenta"

**Qué esperar:** responde con el saldo y su fecha de vencimiento, en voz natural.

**Otras preguntas para probar:** qué producto tienes contratado, qué productos hay disponibles, cuándo vence el próximo pago, el estado de una tarjeta.

### 2.3 Solicitud de tarjeta por voz (prueba separada)

Vale la pena probar esta acción por separado, porque por voz **no** se usa el formulario: la confirmación es conversacional y explícita.

> **Tú:** "Quiero solicitar una tarjeta de crédito"

**Qué esperar:** el agente presenta las opciones de producto, y antes de ejecutar la acción pide una **confirmación explícita** (la confirmación de usuario está activada en voz). Solo al confirmar crea la solicitud y te devuelve el identificador de la nueva tarjeta.

**Verificación:** navega a `/datos` en el sitio web → verás la nueva tarjeta con status **`requested`**.

### 2.4 Probar con número telefónico (opcional)

Para una demo con una llamada telefónica con reconocimiento automático del cliente:

1. En la consola de **DynamoDB** → tabla `banco-accounts` → edita uno de los registros de prueba (p. ej. Diego Fernández) y reemplaza el `phoneNumber` con **tu número de teléfono real** en formato E.164 (p. ej. `+573001234567`). Esto permite que el flujo te identifique automáticamente al llamar, sin preguntarte quién eres.
2. En la consola de **Amazon Connect** → **Phone numbers** → reclama un número telefónico (DID).
3. Asócialo al flujo de contacto de self-service (el flujo inbound desplegado, `banco-selfservice-es-inbound`).
4. Llama al número desde tu celular — el agente de IA te reconocerá automáticamente por tu número y personalizará la atención.

---

## 3. Escalación a Agente Humano

### 3.1 Preparar el entorno del agente humano

1. Inicia sesión en el **workspace de agente** de Amazon Connect (CCP/Agent Workspace).
2. Verifica que tu usuario esté asignado a **BasicQueue** en el perfil de enrutamiento.
3. Verifica que el usuario cuenta con permisos en security profile para interactuar con las Tools, Views y Wisdom (mismas que el Agente IA de Assist).
4. Coloca tu estado en **Available** (disponible) para recibir contactos.

### 3.2 Provocar la escalación (chat)

Desde el widget de chat del sitio web (logueado como `diego.fernandez@example.com`):

> **Tú:** Hola, tengo un cargo de $980.15 que no reconozco en mi cuenta. Necesito disputarlo y que me devuelvan el dinero.

**Qué esperar:** el agente reconoce que las disputas de cargos están fuera de su alcance, lo explica y anuncia la transferencia a un representante.

**Lo que sucede por detrás:** el agente de IA ejecuta la herramienta `Escalate` con la razón (`billing_question`), el sentimiento detectado y un resumen de lo intentado en el autoservicio.

### 3.3 Recibir la escalación en el Agent Workspace

En tu pantalla de agente verás (algo por el estilo):

1. **Screen-pop inmediato** con la vista de "Contacto escalado" que muestra:
   - **Motivo de escalación:** billing_question
   - **Sentimiento del cliente:** neutral / frustrado
   - **Intención del cliente:** disputa de un cargo no reconocido y solicitud de devolución
   - **Resumen de escalación:** (generado por la IA) — qué pidió el cliente, qué intentó el autoservicio, por qué necesita un humano
   - **Acción recomendada:** revisar el cargo en disputa e iniciar la gestión si corresponde
   - **Ya intentado en autoservicio:** se verificó la cuenta y el saldo pendiente

2. Haz clic en **aceptar el contacto** para comenzar la atención.

> Esto demuestra que el agente humano tiene **contexto completo** sin que el cliente repita nada.

---

## 4. Agent Assist (Asistencia al Agente Humano)

> ### ⚠️ Requisito previo: el agente HUMANO también necesita los permisos
>
> En agent-assistance las llamadas a herramientas se autorizan contra la
> **intersección** del perfil de seguridad del agente de IA **y** el del agente
> humano. No basta con que el agente de IA (`banco-agent-assist-iac`) tenga los
> permisos: el usuario humano que abre el panel debe llevar **los mismos**, o las
> herramientas fallan solo en su sesión.
>
> El agente humano necesita las tres cosas:
>
> | Necesita | Permiso / concesión | Sin esto no funciona |
> |---|---|---|
> | **Wisdom** | `Wisdom.View` | las sugerencias de la KB y las consultas al asistente (4.1, 4.3) |
> | **Views** | `CustomViews.Access` | la guía paso a paso de activación de tarjeta (4.2) |
> | **MCP tools** | aplicación `Type: MCP` en el perfil, con namespace = id del gateway y los nueve ids `banco-rest-api-oas-target___<operación>` | las consultas de datos en vivo (4.4) |
>
> Lo más simple es asignar al usuario humano el mismo perfil **`banco-agent-assist-iac`** que despliega la Fase 3 (su id se publica en SSM como `SP_ASSIST_ID`), o añadir esos permisos y la concesión MCP a su perfil actual.
>
> **Publica una nueva versión del perfil después de editarlo.** El agente en ejecución usa la versión publicada; si adjuntaste el perfil pero no publicaste, las llamadas MCP fallan con `Target entity not found` aunque el gateway y la REST API estén sanos.

Una vez que aceptaste el contacto escalado, el panel de **Agent Assist** se activa:

### 4.1 Sugerencias automáticas de la KB

Mientras hablas con el cliente, Q in Connect escucha la conversación y sugiere respuestas. Por ejemplo, si el cliente menciona temas cubiertos por la KB:

> **Cliente:** "Además, me llegó una tarjeta nueva y no sé cómo activarla"

**En el panel de Agent Assist verás:**
- Una respuesta con la información de activación de tarjeta y el link a la entrada de la KB (del artículo `activar-tarjeta.txt`)
- Un **botón de guía "Activar tarjeta"** sugerido automáticamente

### 4.2 La guía paso a paso (activar tarjeta)

Haz clic en el botón **"Activar tarjeta"** en el panel de sugerencias.

Lo que aporta la guía no es información nueva: es el **paso a paso asociado a la entrada de la KB**, presentado un paso a la vez con botones "Anterior" y "Siguiente". El valor está en que el agente **resuelve más rápido** — no tiene que leer y resumir el artículo completo en vivo — y en que todos los agentes dan las mismas instrucciones, en el mismo orden, en cada contacto. Human in the Loop de nuevo, pero ahora el Agente.

### 4.3 Consultas directas al asistente

El agente humano puede escribir preguntas directamente en el panel de Agent Assist:

> **Agente escribe:** "¿Cuál es el horario de las sucursales los sábados?"

**Qué esperar:** la respuesta con los datos tomados del artículo de sucursales de la KB.

### 4.4 Herramientas MCP desde Agent Assist

El asistente también puede invocar las mismas herramientas MCP que el self-service, sobre el cliente del contacto activo:

> **Agente escribe:** "¿Cuál es el saldo de este cliente?"

> **Agente escribe:** "¿Qué tarjetas tiene?"

**Qué esperar:** datos en vivo de la cuenta (saldo y vencimiento, tarjetas y su estado), sin que el agente tenga que salir del workspace ni consultar otra herramienta.

---

## 5. Escenarios Adicionales para Explorar

### 5.1 Escalación por solicitud del cliente

> **Tú (chat):** Prefiero hablar con una persona, por favor.

**Qué esperar:** el agente escala de inmediato con razón `customer_request`, sin insistir en resolverlo.

### 5.2 Tema fuera de alcance

> **Tú:** Quiero hacer una transferencia de $500 a otra cuenta

**Qué esperar:** el agente explica que no ejecuta pagos ni transferencias y escala con razón `out_of_scope`. Nota el contraste con Demo 1: el agente **sí** explica cómo hacer una transferencia (contenido de la KB), pero **no** la ejecuta.

### 5.3 Cuenta suspendida

Inicia sesión como `aisha.khan@example.com` y pregunta:

> **Tú:** ¿Por qué no puedo usar mi tarjeta?

**Qué esperar:** el agente consulta la cuenta, detecta el status `suspended` y lo relaciona con el saldo pendiente, ofreciendo la transferencia a un representante para la reactivación.

> Aisha además ya tiene una solicitud de tarjeta en estado `requested` (`card-9002`), así que pedir otra tarjeta en esa sesión sirve para ver cómo maneja el agente una solicitud ya en curso.

### 5.4 Consulta de un producto específico

> **Tú:** ¿Qué beneficios incluye la Tarjeta Oro?

### 5.5 Comisiones

> **Tú:** ¿Me cobran algo por usar la banca en línea?

**Qué esperar:** respuesta basada en el artículo de comisiones de la KB.

---

## 6. Multi-Lenguaje (Cambio Dinámico de Idioma)

El agente soporta cambio dinámico de idioma sin necesidad de cambiar flujos ni configuración. Usa una voz multilingüe (polyglot) que soporta English, Spanish y Portuguese. El agente detecta el idioma del cliente desde la transcripción/texto y responde en ese mismo idioma, recuperando además los artículos de la KB en la carpeta de idioma correspondiente.

### 6.1 Cambio de idioma en Chat

Inicia sesión como cualquier cliente y abre el chat:

> **Tú:** Hi, I'd like to know my balance

Ahora cambia a español:

> **Tú:** Gracias. ¿Cómo activo mi tarjeta nueva?

Prueba con portugués:

> **Tú:** Quais produtos vocês oferecem?

**Qué esperar:** cada respuesta llega en el idioma del último mensaje del cliente, siguiendo el cambio de inmediato y sin perder el contexto de la conversación.

### 6.2 Cambio de idioma por Voz

Inicia una llamada web y habla en diferentes idiomas:

> **Tú (hablando en inglés):** "Hello, I want to check my account balance"

> **Tú (cambiando a español):** "Sí, ¿me puedes decir qué comisiones tiene mi cuenta?"

> **Tú (cambiando a portugués):** "Obrigado, é tudo por hoje"

**Qué esperar:** la voz cambia de idioma dinámicamente siguiendo al cliente, dentro de la misma llamada y sin transferencias ni reinicios.

---

## Checklist de la Demo

- [ ] Sitio web carga correctamente (CloudFront)
- [ ] Login con email funciona y se refleja en el header
- [ ] Widget de chat se abre y responde
- [ ] Preguntas de KB obtienen respuestas basadas en los artículos del idioma en uso
- [ ] Consulta de saldo devuelve datos reales de la cuenta (coinciden con `/datos`)
- [ ] El listado de productos coincide con la tabla *Productos (products)*
- [ ] Formulario de solicitud de tarjeta se muestra al pedir una tarjeta
- [ ] La tarjeta solicitada aparece en `/datos` con status `requested`
- [ ] Llamada web funciona y la voz suena natural
- [ ] La solicitud de tarjeta por voz pide confirmación explícita antes de ejecutar
- [ ] Escalación transfiere al agente con contexto completo
- [ ] Screen-pop muestra resumen, razón y acción recomendada
- [ ] **El usuario humano lleva `Wisdom.View` + `CustomViews.Access` + la concesión MCP, en una versión publicada del perfil**
- [ ] Agent Assist sugiere respuestas de la KB
- [ ] Guía paso a paso de activación de tarjeta se despliega correctamente
- [ ] El asistente responde consultas directas del agente
- [ ] Chat responde en el idioma del cliente (probar inglés, español, portugués)
- [ ] Cambio de idioma mid-conversation funciona en chat
- [ ] Voz cambia de idioma dinámicamente al seguir al caller
