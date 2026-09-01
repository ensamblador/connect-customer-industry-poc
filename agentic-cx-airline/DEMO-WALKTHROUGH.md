# Script de Demo — Airline PoC

> 🌐 **Idiomas:** **Español** (este archivo) · [English](./DEMO-WALKTHROUGH-en.md)

Guía paso a paso para demostrar las capacidades de la PoC de aerolínea. Indica las preguntas a usar y qué esperar en cada paso, sin guionizar las respuestas del agente (son generadas en vivo y varían).

---

## Datos de Prueba

Antes de comenzar, familiarízate con los datos sintéticos disponibles:

| Cliente | Email | Teléfono | Categoría | Millas | Vuelos en la cuenta | Estado |
|---------|-------|----------|-----------|--------|---------------------|--------|
| María González | maria.gonzalez@example.com | +12065550101 | gold | 48,250 | AL100, AL305 | activa |
| James Carter | james.carter@example.com | +12065550102 | classic | 9,120 | AL200 | activa |
| Aisha Khan | aisha.khan@example.com | +12065550103 | platinum | 132,540 | AL410, AL520 | activa |
| Diego Fernández | diego.fernandez@example.com | +12065550104 | classic | 3,480 | AL150 | activa |

**Vuelos disponibles:**

| Vuelo | Ruta | Fecha | Horario | Precio | Asientos |
|-------|------|-------|---------|--------|----------|
| AL100 | Bogotá → Medellín (BOG→MDE) | 15 ago 2026 | 06:30 → 07:45 | $89 USD | 42 |
| AL150 | Bogotá → Medellín (BOG→MDE) | 15 ago 2026 | 18:00 → 19:15 | $95 USD | 12 |
| AL200 | Bogotá → Lima (BOG→LIM) | 15 ago 2026 | 09:00 → 11:30 | $199 USD | 18 |
| AL305 | Medellín → Ciudad de México (MDE→MEX) | 16 ago 2026 | 14:00 → 18:15 | $320 USD | 55 |
| AL410 | Lima → Santiago (LIM→SCL) | 17 ago 2026 | 07:45 → 12:00 | $275 USD | 90 |
| AL520 | Santiago → São Paulo (SCL→GRU) | 18 ago 2026 | 22:00 → 03:30 | $410 USD | 35 |

**Reservas existentes:** `res-8001` (María González, AL100, **confirmed**, asiento 12A) y `res-8002` (James Carter, AL200, **pending**, pendiente de confirmación de pago). **Aisha Khan y Diego Fernández no tienen reservas** — útil para demostrar la diferencia entre "vuelos en la cuenta" y "reservas".

> Los datos se pueden ver en el sitio web en la ruta `/datos` (link "Datos demo" en la navegación), con las tablas *Cuentas (accounts)*, *Vuelos (flights)* y *Reservas (reservations)*.

---

## 1. Self-Service por Chat

### 1.1 Acceder al sitio web

1. Abre el output de CloudFormation del stack **CX-AIRLINE-WEBSITE** → toma el valor de `WebsiteDistributionDomainName` (dominio CloudFront, p. ej. `https://d1234abcdef.cloudfront.net`). El output `WebsiteDataViewerPath` te da directamente la URL de `/datos`.
2. Navega al sitio web. Verás la página de "AeroLatam" con secciones de vuelos, millas y ayuda.

### 1.2 Simular un usuario logueado

1. Haz clic en **"Iniciar sesión"** en el header.
2. Ingresa un email de los datos de prueba, por ejemplo: `diego.fernandez@example.com`
3. Haz clic en "Entrar". El sitio guarda el email en sessionStorage y lo envía como atributo del contacto al widget de chat.

> Esto permite que el agente de IA identifique automáticamente al cliente sin preguntar.

### 1.3 Abrir el chat y conversar

Haz clic en el **widget de chat** (burbuja en la esquina inferior derecha). Se abre la ventana de conversación.

---

### Demo 1: Preguntas de Knowledge Base

El agente responde estas preguntas **con los artículos de la base de conocimiento**, no con conocimiento propio del modelo. Los artículos viven en `knowledge_bases/airline/entries/<idioma>/`, con una carpeta por idioma (`es`, `en`, `pt`): el agente recupera la entrada correspondiente al idioma en que está conversando el cliente.

Preguntas para probar:

> **Tú:** ¿Cuánto equipaje de mano puedo llevar?

> **Tú:** ¿Cómo hago el check-in?

> **Tú:** ¿Cómo funcionan las millas del programa de viajero frecuente?

> **Tú:** ¿Dónde están los mostradores de AeroLatam en el aeropuerto?

> **Tú:** ¿Qué hago si mi maleta no llegó?

**Qué esperar:** una respuesta redactada a partir del artículo correspondiente, en el idioma del cliente y citando la fuente recuperada. Si la pregunta no está cubierta por ningún artículo, el agente no debe inventar la respuesta.

**Otras preguntas para seguir explorando** (mismas fuentes, sin salir de la KB): cómo cambiar o cancelar una reserva, selección de asientos, artículos especiales y equipaje deportivo, cargos por exceso de peso, cómo inscribirse en AeroLatam Club.

---

### Demo 2: Consulta de cuenta (MCP Tools)

Estas preguntas disparan herramientas MCP que consultan la API en tiempo real.

> **Tú:** ¿Cuántas millas tengo acumuladas?

> **Tú:** ¿Qué vuelos tengo en mi cuenta?

> **Tú:** ¿Qué vuelos hay disponibles de Bogotá a Medellín?

**Qué esperar:** el agente primero resuelve la cuenta a partir del email de la sesión y luego invoca la herramienta MCP. La respuesta puede ser algo como el **saldo de millas y la categoría del viajero**, o el listado de vuelos con su horario y precio, tomados en vivo de la API vía MCP. Verifica contra `/datos` que los valores coincidan con el registro del cliente.

**Preguntas de follow-up para probar:**

> **Tú:** ¿Cuál es mi categoría de viajero frecuente?

> **Tú:** ¿Cuánto cuesta el vuelo AL305?

> **Tú:** ¿Tengo alguna reserva activa?

> **Tú:** ¿Hay vuelos a Lima?

> Nota: "¿qué vuelos tengo?" y "¿tengo reservas?" usan herramientas distintas (`getAccountFlights` vs `listCustomerReservations`). Con Diego o Aisha la primera devuelve datos y la segunda viene vacía — buen momento para mostrar que el agente elige la herramienta según la intención.

---

### Demo 3: Reservar un vuelo (Formulario guiado)

Esta demo muestra una acción determinística con **human-in-the-loop, donde el humano en el loop es el cliente**: en lugar de dejar que el modelo interprete la elección conversacionalmente, el cliente la confirma en un formulario.

> **Tú:** Quiero reservar un vuelo

**Qué esperar:** el agente identifica tu cuenta, avisa brevemente que va a abrir un formulario y devuelve el control al flujo. En el chat verás un **formulario con botones** para elegir una opción (o cancelar).

> **Tú:** *(Haz clic en una de las opciones del formulario)*

**Qué esperar:** el agente retoma la conversación, confirma la solicitud y te da el identificador de la nueva reserva con su estado inicial.

**Verificación:** navega a `/datos` en el sitio web → verás la nueva reserva con status **`pending`**.

**Follow-up opcional**, para cerrar el ciclo en la misma conversación:

> **Tú:** ¿Puedo ver mis reservas?

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

> **Tú (hablando):** "Hola, quiero saber cuánto equipaje de mano puedo llevar"

**Qué esperar:** una respuesta hablada basada en los artículos de la KB, en el mismo idioma en que preguntaste.

**Otras preguntas para probar por voz:** cómo hacer el check-in, cómo reportar una maleta perdida, horarios de los mostradores en el aeropuerto, cómo acumular y usar millas.

#### Consulta de cuenta por voz

> **Tú:** "Quiero saber cuántas millas tengo"

**Qué esperar:** responde con el saldo de millas y la categoría del viajero, en voz natural.

**Otras preguntas para probar:** qué vuelos tienes en tu cuenta, qué vuelos hay disponibles a un destino, cuánto cuesta un vuelo específico, el estado de una reserva.

### 2.3 Reserva de vuelo por voz (prueba separada)

Vale la pena probar esta acción por separado, porque por voz **no** se usa el formulario: la confirmación es conversacional y explícita.

> **Tú:** "Quiero reservar un vuelo a Medellín"

**Qué esperar:** el agente presenta los vuelos disponibles en esa ruta, y antes de ejecutar la acción pide una **confirmación explícita** (la confirmación de usuario está activada en voz). Solo al confirmar crea la reserva y te devuelve el identificador.

**Verificación:** navega a `/datos` en el sitio web → verás la nueva reserva con status **`pending`**.

### 2.4 Probar con número telefónico (opcional)

Para una demo con una llamada telefónica con reconocimiento automático del cliente:

1. En la consola de **DynamoDB** → tabla `airline-accounts` → edita uno de los registros de prueba (p. ej. Diego Fernández) y reemplaza el `phoneNumber` con **tu número de teléfono real** en formato E.164 (p. ej. `+573001234567`). Esto permite que el flujo te identifique automáticamente al llamar, sin preguntarte quién eres.
2. En la consola de **Amazon Connect** → **Phone numbers** → reclama un número telefónico (DID).
3. Asócialo al flujo de contacto de self-service (el flujo inbound desplegado, `airline-selfservice-es-inbound`).
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

> **Tú:** Hola, me cobraron dos veces el vuelo AL150 y necesito que me devuelvan el cargo duplicado.

**Qué esperar:** el agente reconoce que las disputas de cobro están fuera de su alcance, lo explica y anuncia la transferencia a un representante.

**Lo que sucede por detrás:** el agente de IA ejecuta la herramienta `Escalate` con la razón (`billing_question`), el sentimiento detectado y un resumen de lo intentado en el autoservicio.

### 3.3 Recibir la escalación en el Agent Workspace

En tu pantalla de agente verás (algo por el estilo):

1. **Screen-pop inmediato** con la vista de "Contacto escalado" que muestra:
   - **Motivo de escalación:** billing_question
   - **Sentimiento del cliente:** neutral / frustrado
   - **Intención del cliente:** devolución de un cargo duplicado de un vuelo
   - **Resumen de escalación:** (generado por la IA) — qué pidió el cliente, qué intentó el autoservicio, por qué necesita un humano
   - **Acción recomendada:** verificar el cobro duplicado y gestionar la devolución si corresponde
   - **Ya intentado en autoservicio:** se verificó la cuenta y los vuelos del cliente

2. Haz clic en **aceptar el contacto** para comenzar la atención.

> Esto demuestra que el agente humano tiene **contexto completo** sin que el cliente repita nada.

---

## 4. Agent Assist (Asistencia al Agente Humano)

> ### ⚠️ Requisito previo: el agente HUMANO también necesita los permisos
>
> En agent-assistance las llamadas a herramientas se autorizan contra la
> **intersección** del perfil de seguridad del agente de IA **y** el del agente
> humano. No basta con que el agente de IA (`airline-agent-assist-iac`) tenga los
> permisos: el usuario humano que abre el panel debe llevar **los mismos**, o las
> herramientas fallan solo en su sesión.
>
> El agente humano necesita las tres cosas:
>
> | Necesita | Permiso / concesión | Sin esto no funciona |
> |---|---|---|
> | **Wisdom** | `Wisdom.View` | las sugerencias de la KB y las consultas al asistente (4.1, 4.3) |
> | **Views** | `CustomViews.Access` | la guía paso a paso de maleta perdida (4.2) |
> | **MCP tools** | aplicación `Type: MCP` en el perfil, con namespace = id del gateway y los nueve ids `airline-rest-api-oas-target___<operación>` | las consultas de datos en vivo (4.4) |
>
> Lo más simple es asignar al usuario humano el mismo perfil **`airline-agent-assist-iac`** que despliega la Fase 3 (su id se publica en SSM como `SP_ASSIST_ID`), o añadir esos permisos y la concesión MCP a su perfil actual.
>
> **Publica una nueva versión del perfil después de editarlo.** El agente en ejecución usa la versión publicada; si adjuntaste el perfil pero no publicaste, las llamadas MCP fallan con `Target entity not found` aunque el gateway y la REST API estén sanos.

Una vez que aceptaste el contacto escalado, el panel de **Agent Assist** se activa:

### 4.1 Sugerencias automáticas de la KB

Mientras hablas con el cliente, Q in Connect escucha la conversación y sugiere respuestas. Por ejemplo, si el cliente menciona temas cubiertos por la KB:

> **Cliente:** "Además, en mi último viaje mi maleta no llegó y no sé cómo reportarla"

**En el panel de Agent Assist verás:**
- Una respuesta con la información para reportar el equipaje y el link a la entrada de la KB (del artículo `maleta-perdida.txt`)
- Un **botón de guía "Reportar maleta perdida"** sugerido automáticamente

### 4.2 La guía paso a paso (maleta perdida)

Haz clic en el botón **"Reportar maleta perdida"** en el panel de sugerencias.

Lo que aporta la guía no es información nueva: es el **paso a paso asociado a la entrada de la KB**, presentado un paso a la vez con botones "Anterior" y "Siguiente". El valor está en que el agente **resuelve más rápido** — no tiene que leer y resumir el artículo completo en vivo — y en que todos los agentes dan las mismas instrucciones, en el mismo orden, en cada contacto. Human in the Loop de nuevo, pero ahora el Agente.

### 4.3 Consultas directas al asistente

El agente humano puede escribir preguntas directamente en el panel de Agent Assist:

> **Agente escribe:** "¿Cuál es la franquicia de equipaje para un cliente platinum?"

**Qué esperar:** la respuesta con los datos tomados del artículo de equipaje de la KB.

### 4.4 Herramientas MCP desde Agent Assist

El asistente también puede invocar las mismas herramientas MCP que el self-service, sobre el cliente del contacto activo:

> **Agente escribe:** "¿Cuántas millas tiene este cliente?"

> **Agente escribe:** "¿Qué reservas tiene?"

**Qué esperar:** datos en vivo de la cuenta (millas y categoría, vuelos y reservas con su estado), sin que el agente tenga que salir del workspace ni consultar otra herramienta.

---

## 5. Escenarios Adicionales para Explorar

### 5.1 Escalación por solicitud del cliente

> **Tú (chat):** Prefiero hablar con una persona, por favor.

**Qué esperar:** el agente escala de inmediato con razón `customer_request`, sin insistir en resolverlo.

### 5.2 Tema fuera de alcance

> **Tú:** Quiero cancelar mi reserva

**Qué esperar:** el agente explica que los cambios y cancelaciones de reserva los gestiona un representante y escala con razón `out_of_scope`.

### 5.3 Cliente sin reservas

Inicia sesión como `aisha.khan@example.com` (categoría platinum, con vuelos en la cuenta pero sin reservas) y pregunta:

> **Tú:** ¿Cuál es el estado de mis reservas?

**Qué esperar:** el agente consulta y reporta que no encuentra reservas, sin inventar ninguna, y puede ofrecer crear una. Contrasta con `james.carter@example.com`, cuya reserva `res-8002` está en estado `pending` por confirmación de pago.

### 5.4 Consulta de un vuelo específico

> **Tú:** ¿A qué hora sale el vuelo AL520 y cuánto dura?

### 5.5 Equipaje y artículos especiales

> **Tú:** ¿Puedo llevar una tabla de surf en el avión?

**Qué esperar:** respuesta basada en el artículo de equipaje de la KB.

---

## 6. Multi-Lenguaje (Cambio Dinámico de Idioma)

El agente soporta cambio dinámico de idioma sin necesidad de cambiar flujos ni configuración. Usa una voz multilingüe (polyglot) que soporta English, Spanish y Portuguese. El agente detecta el idioma del cliente desde la transcripción/texto y responde en ese mismo idioma, recuperando además los artículos de la KB en la carpeta de idioma correspondiente.

### 6.1 Cambio de idioma en Chat

Inicia sesión como cualquier cliente y abre el chat:

> **Tú:** Hi, how many miles do I have?

Ahora cambia a español:

> **Tú:** Gracias. ¿Cuánto equipaje de mano puedo llevar?

Prueba con portugués:

> **Tú:** Quais voos vocês têm de Bogotá para Lima?

**Qué esperar:** cada respuesta llega en el idioma del último mensaje del cliente, siguiendo el cambio de inmediato y sin perder el contexto de la conversación.

### 6.2 Cambio de idioma por Voz

Inicia una llamada web y habla en diferentes idiomas:

> **Tú (hablando en inglés):** "Hello, I want to check my miles balance"

> **Tú (cambiando a español):** "Sí, ¿me puedes decir qué vuelos tengo?"

> **Tú (cambiando a portugués):** "Obrigado, é tudo por hoje"

**Qué esperar:** la voz cambia de idioma dinámicamente siguiendo al cliente, dentro de la misma llamada y sin transferencias ni reinicios.

---

## Checklist de la Demo

- [ ] Sitio web carga correctamente (CloudFront)
- [ ] Login con email funciona y se refleja en el header
- [ ] Widget de chat se abre y responde
- [ ] Preguntas de KB obtienen respuestas basadas en los artículos del idioma en uso
- [ ] Consulta de millas devuelve datos reales de la cuenta (coinciden con `/datos`)
- [ ] El listado de vuelos disponibles coincide con la tabla *Vuelos (flights)*
- [ ] Formulario de reserva se muestra al pedir reservar un vuelo
- [ ] La reserva creada aparece en `/datos` con status `pending`
- [ ] Llamada web funciona y la voz suena natural
- [ ] La reserva por voz pide confirmación explícita antes de ejecutar
- [ ] Escalación transfiere al agente con contexto completo
- [ ] Screen-pop muestra resumen, razón y acción recomendada
- [ ] **El usuario humano lleva `Wisdom.View` + `CustomViews.Access` + la concesión MCP, en una versión publicada del perfil**
- [ ] Agent Assist sugiere respuestas de la KB
- [ ] Guía paso a paso de maleta perdida se despliega correctamente
- [ ] El asistente responde consultas directas del agente
- [ ] Chat responde en el idioma del cliente (probar inglés, español, portugués)
- [ ] Cambio de idioma mid-conversation funciona en chat
- [ ] Voz cambia de idioma dinámicamente al seguir al caller
