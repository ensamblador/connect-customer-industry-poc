# Script de Demo — Telco PoC

Guía paso a paso para demostrar las capacidades de la PoC de telecomunicaciones. Incluye diálogos exactos y respuestas esperadas.

---

## Datos de Prueba

Antes de comenzar, familiarízate con los datos sintéticos disponibles:

| Cliente | Email | Teléfono | Plan | Saldo | Estado |
|---------|-------|----------|------|-------|--------|
| María González | maria.gonzalez@example.com | +12065550101 | Unlimited 5G ($70/mes) | $42.50 | activa |
| James Carter | james.carter@example.com | +12065550102 | Plus ($45/mes) | $0 | activa |
| Aisha Khan | aisha.khan@example.com | +12065550103 | Basic ($25/mes) | $88.00 | suspendida |
| Diego Fernández | diego.fernandez@example.com | +12065550104 | Plus ($45/mes) | $15.75 | activa |

**Planes disponibles:**
- Telco Basic: 5 GB, $25/mes (sin hotspot)
- Telco Plus: 25 GB, $45/mes (con hotspot)
- Telco Unlimited 5G: 100 GB, $70/mes (con hotspot, acceso prioritario)

> Los datos se pueden ver en el sitio web en la ruta `/datos` (link "Datos demo" en la navegación).

---

## 1. Self-Service por Chat

### 1.1 Acceder al sitio web

1. Abre el output de CloudFormation del stack **CX-TELCO-WEBSITE** → toma el valor de `WebhostingDistributionDomainName` (dominio CloudFront, p. ej. `https://d1234abcdef.cloudfront.net`).
2. Navega al sitio web. Verás la página de "Latam Telco" con secciones de planes, cobertura y ayuda.

### 1.2 Simular un usuario logueado

1. Haz clic en **"Iniciar sesión"** en el header.
2. Ingresa un email de los datos de prueba, por ejemplo: `maria.gonzalez@example.com`
3. Haz clic en "Entrar". El sitio guarda el email en sessionStorage y lo envía como atributo del contacto al widget de chat.

> Esto permite que el agente de IA identifique automáticamente al cliente sin preguntar.

### 1.3 Abrir el chat y conversar

Haz clic en el **widget de chat** (burbuja en la esquina inferior derecha). Se abre la ventana de conversación.

---

### Demo 1: Preguntas de Knowledge Base

Estas preguntas se responden desde la base de conocimiento (artículos en `knowledge_bases/telco/entries/es/`).

#### Roaming internacional

> **Tú:** ¿Cómo puedo usar mi teléfono en el extranjero?

**Respuesta esperada del agente:**
> Tu teléfono funciona en el extranjero si tu plan incluye roaming. Algunos planes lo incluyen para ciertos países; otros requieren un paquete de viaje. Para evitar cargos sorpresa: revisa si tu plan cubre tu destino, desactiva los datos en roaming desde los ajustes, y usa WiFi cuando sea posible. Las llamadas y mensajes pueden tener tarifas diferentes; las apps de mensajería por WiFi son la opción más económica.

#### Llamadas por WiFi

> **Tú:** ¿Cómo activo las llamadas por WiFi?

**Respuesta esperada:**
> Para activar las llamadas por WiFi, ve a los ajustes de tu teléfono, busca la sección de llamadas o red móvil, y habilita la opción de llamadas por WiFi (WiFi Calling). Esto te permite hacer y recibir llamadas usando tu conexión WiFi cuando la señal celular es débil.

#### Cobertura 5G

> **Tú:** ¿Tienen cobertura 5G en mi zona?

**Respuesta esperada:**
> Tenemos cobertura 5G en la mayoría de áreas metropolitanas y 4G LTE a nivel nacional. Puedes verificar la cobertura exacta en tu zona usando el mapa de cobertura en nuestro sitio web con tu código postal. Si tu plan incluye 5G, no tiene costo adicional. Tu teléfono debe ser compatible con 5G para aprovechar esa velocidad; si es solo 4G, seguirá funcionando sin la velocidad 5G.

#### Horarios de tiendas

> **Tú:** ¿A qué hora abren las tiendas?

**Respuesta esperada:**
> Nuestras tiendas tienen el siguiente horario general: lunes a viernes de 9:00 AM a 9:00 PM, sábados de 10:00 AM a 8:00 PM, y domingos de 11:00 AM a 6:00 PM. Tenemos tiendas en Los Ángeles, San Francisco, Houston, Miami y Phoenix. La tienda de Phoenix no abre los domingos.

#### Compatibilidad de equipos

> **Tú:** ¿Cómo sé si mi teléfono es compatible con ustedes?

**Respuesta esperada:**
> La mayoría de los teléfonos recientes desbloqueados son compatibles. Puedes verificar marcando *#06# para obtener tu IMEI, o buscándolo en Configuración → Acerca del teléfono. Luego consulta la compatibilidad en nuestro sitio web. Tu teléfono debe estar desbloqueado (no ligado a otro operador). Si está bloqueado, debes pedir a tu operador anterior que lo desbloquee.

---

### Demo 2: Consulta de cuenta (MCP Tools)

Estas preguntas disparan herramientas MCP que consultan la base de datos en tiempo real.

#### Consultar saldo

> **Tú:** ¿Cuánto debo de mi factura?

**Respuesta esperada:**
> *(El agente primero busca la cuenta por el email de sesión, luego consulta el saldo)*
>
> Tu saldo pendiente es de **$42.50 USD** con fecha de vencimiento el **20 de junio de 2026**. ¿Hay algo más en lo que pueda ayudarte?

#### Ver plan actual

> **Tú:** ¿Qué plan tengo contratado?

**Respuesta esperada:**
> Tienes el plan **Telco Unlimited 5G**: 100 GB de datos premium 5G con hotspot y acceso prioritario a la red, llamadas y mensajes ilimitados, por $70.00 USD al mes.

#### Listar planes disponibles

> **Tú:** ¿Qué planes ofrecen?

**Respuesta esperada:**
> Tenemos tres planes disponibles:
> 1. **Telco Basic** — 5 GB de datos, $25/mes. Ideal para usuarios ligeros. Llamadas y mensajes ilimitados.
> 2. **Telco Plus** — 25 GB de datos con hotspot, $45/mes. Llamadas y mensajes ilimitados.
> 3. **Telco Unlimited 5G** — 100 GB de datos premium 5G con hotspot y acceso prioritario, $70/mes.
>
> ¿Te interesa alguno en particular?

---

### Demo 3: Solicitar una nueva línea (Formulario guiado)

Esta demo muestra cómo el agente usa un formulario visual para una acción determinística (sin interpretación).

> **Tú:** Quiero agregar una nueva línea a mi cuenta

**Respuesta esperada:**
> *(El agente identifica tu cuenta y abre el formulario guiado)*
>
> Perfecto, voy a abrir un formulario para que elijas el plan de tu nueva línea.

**Lo que verás en el chat:** Un formulario visual con botones:
- Telco Basic — 5 GB — $25/mes
- Telco Plus — 25 GB — $45/mes
- Telco Unlimited 5G — 100 GB — $70/mes
- Cancelar

> **Tú:** *(Haz clic en "Telco Plus — 25 GB — $45/mes")*

**Respuesta esperada del agente:**
> He solicitado tu nueva línea con el plan Telco Plus. Tu número de solicitud es **line-XXXXXXXX** y el estado es "solicitada" (pendiente de aprovisionamiento). ¿Hay algo más en lo que pueda ayudarte?

**Verificación:** Navega a `/datos` en el sitio web → tabla "Líneas (lines)" → verás la nueva línea con status "requested".

---

### Demo 4: Verificar líneas existentes

> **Tú:** ¿Puedo ver mis líneas activas?

**Respuesta esperada:**
> Tienes las siguientes líneas asociadas a tu cuenta:
> - **line-9001** — Plan Telco Plus, código de área 206, estado: activa. Nota: línea adicional para un miembro de la familia.
> - *(La línea recién solicitada también aparecerá aquí)*
>
> ¿Necesitas algo más?

---

## 2. Self-Service por Voz

### 2.1 Iniciar llamada web

1. En el widget de chat (ya abierto), haz clic en el ícono de **teléfono/llamada web** (WebRTC call).
2. El navegador pedirá acceso al **micrófono** → concédelo.
3. Se establece la llamada y escucharás una voz natural (Katie, Nova Sonic v2) saludándote.

> **Nota:** No se requiere un número telefónico para probar. La llamada web usa el mismo flujo de self-service y ofrece las mismas capacidades que una llamada real.

### 2.2 Diálogos de voz

#### Pregunta de knowledge base

> **Tú (hablando):** "Hola, quiero saber cómo activar las llamadas por WiFi en mi teléfono"

**Respuesta esperada (voz):**
> "Para activar las llamadas por WiFi, ve a los ajustes de tu teléfono, busca la sección de llamadas o red móvil, y habilita la opción. Esto te permite hacer y recibir llamadas usando tu conexión WiFi cuando la señal celular es débil. ¿Puedo ayudarte con algo más?"

#### Consulta de saldo por voz

> **Tú:** "Quiero saber cuánto debo"

**Respuesta esperada:**
> *(Si no te ha identificado aún)*
> "Claro, necesito verificar tu cuenta. ¿Me puedes dar tu correo electrónico o número de teléfono?"

> **Tú:** "Mi correo es maria.gonzalez@example.com"

**Respuesta:**
> "Gracias María. Tu saldo pendiente es de cuarenta y dos dólares con cincuenta centavos, con vencimiento el veinte de junio. ¿Hay algo más en lo que pueda ayudarte?"

#### Solicitar nueva línea por voz

> **Tú:** "Quiero una línea nueva"

**Respuesta esperada:**
> "¡Perfecto! ¿Qué plan te gustaría para la nueva línea? Tenemos Telco Basic con 5 gigas por 25 dólares al mes, Telco Plus con 25 gigas por 45 dólares, y Telco Unlimited 5G con 100 gigas por 70 dólares."

> **Tú:** "El plan Plus"

**Respuesta:**
> "Entonces sería una nueva línea con el plan Telco Plus a 45 dólares mensuales. ¿Confirmas que deseas proceder?"

> **Tú:** "Sí, confirmo"

**Respuesta:**
> "Listo, tu solicitud de nueva línea ha sido creada con éxito. Tu número de solicitud es line-[id]. El estado es solicitada y se aprovisionará pronto. ¿Puedo ayudarte con algo más?"

> **Tú:** "No, eso es todo, gracias"

**Respuesta:**
> "Perfecto, gracias por comunicarte con Latam Telco. ¡Que tengas un excelente día!"

### 2.3 Probar con número telefónico (opcional)

Para una demo más realista:
1. En la consola de Amazon Connect → **Phone numbers** → reclama un número.
2. Asócialo al flujo de contacto de self-service (el flujo inbound desplegado).
3. Llama al número desde un teléfono real — la experiencia es idéntica a la llamada web.

---

## 3. Escalación a Agente Humano

### 3.1 Preparar el entorno del agente humano

1. Inicia sesión en el **workspace de agente** de Amazon Connect (CCP/Agent Workspace).
2. Verifica que tu usuario esté asignado a **BasicQueue** en el perfil de enrutamiento.
3. Coloca tu estado en **Available** (disponible) para recibir contactos.

### 3.2 Provocar la escalación (chat)

Desde el widget de chat del sitio web (logueado como maria.gonzalez@example.com):

> **Tú:** Hola, tengo un problema con mi factura. Me están cobrando $42.50 pero ya pagué el mes pasado. Necesito que me ajusten el saldo.

**Respuesta esperada del agente:**
> *(El agente reconoce que temas de facturación/disputas están fuera de su alcance)*
>
> Entiendo tu preocupación con el cobro. Los ajustes de facturación los maneja directamente un representante. Voy a transferirte con un agente que podrá resolver esto. Un momento por favor.

**Lo que sucede:** El agente de IA ejecuta la herramienta `Escalate` con:
- **Razón:** `billing_question`
- **Sentimiento:** frustrado/neutral
- **Resumen:** "El cliente reporta un cobro de $42.50 que considera incorrecto porque ya pagó. Solicita ajuste de saldo. Fuera del alcance del autoservicio."

### 3.3 Recibir la escalación en el Agent Workspace

En tu pantalla de agente verás:

1. **Screen-pop inmediato** con la vista de "Contacto escalado" que muestra:
   - **Motivo de escalación:** billing_question
   - **Sentimiento del cliente:** neutral / frustrado
   - **Intención del cliente:** Ajuste de saldo por cobro duplicado
   - **Resumen de escalación:** (generado por la IA) — qué pidió el cliente, qué intentó el autoservicio, por qué necesita un humano
   - **Acción recomendada:** Verificar pago y ajustar saldo si corresponde
   - **Ya intentado en autoservicio:** Se verificó la cuenta y el saldo pendiente

2. Haz clic en **"Entendido"** para aceptar el contacto y comenzar la atención.

> Esto demuestra que el agente humano tiene **contexto completo** sin que el cliente repita nada.

---

## 4. Agent Assist (Asistencia al Agente Humano)

Una vez que aceptaste el contacto escalado, el panel de **Q in Connect** (Agent Assist) se activa:

### 4.1 Sugerencias automáticas de la KB

Mientras hablas con el cliente, Q in Connect escucha la conversación y sugiere respuestas. Por ejemplo, si el cliente menciona temas cubiertos por la KB:

> **Cliente:** "Además, quiero saber si puedo activar una eSIM en mi teléfono nuevo"

**En el panel de Agent Assist verás:**
- Una sugerencia con la información de activación de eSIM (del artículo `esim-activacion.txt`)
- Un **botón de guía "Activar eSIM"** — al hacer clic, se despliega una guía paso a paso con las instrucciones completas

### 4.2 La guía paso a paso (eSIM)

Haz clic en el botón **"Activar eSIM"** en el panel de sugerencias:

1. **Paso 1:** Verificar compatibilidad — ir a Configuración → Red/Datos móviles y buscar la opción eSIM
2. **Paso 2:** Conectar a WiFi para la descarga del perfil
3. **Paso 3:** Ir a Configuración → agregar eSIM → escanear el código QR enviado por email
4. **Paso 4:** Confirmar que la eSIM se activó (puede tardar unos minutos)

> Cada paso se muestra uno a la vez con botones "Anterior" y "Siguiente". Esto guía al agente para dar instrucciones consistentes.

### 4.3 Consultas directas al asistente

El agente humano puede escribir preguntas directamente en el panel de Agent Assist:

> **Agente escribe:** "¿Cuáles son los horarios de la tienda de Miami?"

**Respuesta en el panel:**
> La tienda de Miami (Tienda Midtown) está ubicada en 321 Ocean Blvd. Horario: lunes a viernes 9AM-9PM, sábados 10AM-8PM, domingos 11AM-6PM. Teléfono: 800-555-0103.

### 4.4 Herramientas MCP desde Agent Assist

El asistente también puede invocar las mismas herramientas MCP:

> **Agente escribe:** "¿Cuál es el saldo de este cliente?"

**Respuesta:**
> El saldo pendiente de María González (cuenta acct-1001) es de $42.50 USD con vencimiento el 20 de junio de 2026.

> **Agente escribe:** "¿Qué líneas tiene activas?"

**Respuesta:**
> María tiene 1 línea activa: line-9001 con plan Telco Plus, código de área 206. También puede haber una línea recién solicitada pendiente de aprovisionamiento.

---

## 5. Escenarios Adicionales para Explorar

### 5.1 Escalación por solicitud del cliente

> **Tú (chat):** Prefiero hablar con una persona, por favor.

**Respuesta:**
> Entendido, te transfiero con un representante ahora mismo. Un momento.
>
> *(Escala con razón "customer_request")*

### 5.2 Tema fuera de alcance

> **Tú:** Quiero cancelar mi línea

**Respuesta:**
> Las cancelaciones de línea las gestiona directamente un representante. Voy a transferirte para que te ayuden con eso.
>
> *(Escala con razón "out_of_scope")*

### 5.3 Cuenta suspendida

Inicia sesión como `aisha.khan@example.com` y pregunta:

> **Tú:** ¿Por qué no puedo hacer llamadas?

**Respuesta esperada:**
> *(El agente consulta la cuenta y detecta status "suspended")*
>
> Veo que tu cuenta está actualmente suspendida. Esto puede deberse a un saldo pendiente de $88.00 con fecha de vencimiento 10 de junio. Te recomiendo comunicarte con un representante para resolver la reactivación. ¿Quieres que te transfiera?

### 5.4 Consulta de un plan específico

> **Tú:** ¿Cuántos datos incluye el plan Basic?

**Respuesta:**
> El plan Telco Basic incluye 5 GB de datos de alta velocidad, llamadas y mensajes ilimitados, por $25 al mes. No incluye hotspot. Es ideal para usuarios con uso ligero de datos.

### 5.5 Portabilidad numérica

> **Tú:** ¿Puedo conservar mi número si me cambio a ustedes?

**Respuesta (de la KB):**
> Sí, puedes conservar tu número actual. Es importante que mantengas tu línea activa con tu operador actual durante el proceso de transferencia — no la canceles antes. La portabilidad se gestiona durante la activación de tu nueva línea con nosotros.

---

## Checklist de la Demo

- [ ] Sitio web carga correctamente (CloudFront)
- [ ] Login con email funciona y se refleja en el header
- [ ] Widget de chat se abre y responde
- [ ] Preguntas de KB obtienen respuestas con información del dominio
- [ ] Consulta de saldo devuelve datos reales de la cuenta
- [ ] Formulario de nueva línea se muestra al solicitar una línea
- [ ] La línea solicitada aparece en `/datos`
- [ ] Llamada web funciona y la voz es natural (Katie / Nova Sonic)
- [ ] Escalación transfiere al agente con contexto completo
- [ ] Screen-pop muestra resumen, razón y acción recomendada
- [ ] Agent Assist sugiere respuestas de la KB
- [ ] Guía paso a paso de eSIM se despliega correctamente
- [ ] El asistente responde consultas directas del agente
