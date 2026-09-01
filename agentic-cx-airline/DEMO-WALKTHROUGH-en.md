# Demo Script — Airline PoC

> 🌐 **Languages:** [Español](./DEMO-WALKTHROUGH.md) · **English** (this file)

Step-by-step guide for demonstrating the airline PoC capabilities. It gives you the questions to use and what to expect at each step, without scripting the agent's replies (they are generated live and vary).

---

## Test Data

Before you start, get familiar with the available synthetic data:

| Customer | Email | Phone | Tier | Miles | Flights on account | Status |
|----------|-------|-------|------|-------|--------------------|--------|
| María González | maria.gonzalez@example.com | +12065550101 | gold | 48,250 | AL100, AL305 | active |
| James Carter | james.carter@example.com | +12065550102 | classic | 9,120 | AL200 | active |
| Aisha Khan | aisha.khan@example.com | +12065550103 | platinum | 132,540 | AL410, AL520 | active |
| Diego Fernández | diego.fernandez@example.com | +12065550104 | classic | 3,480 | AL150 | active |

**Available flights:**

| Flight | Route | Date | Time | Price | Seats |
|--------|-------|------|------|-------|-------|
| AL100 | Bogotá → Medellín (BOG→MDE) | 15 Aug 2026 | 06:30 → 07:45 | $89 USD | 42 |
| AL150 | Bogotá → Medellín (BOG→MDE) | 15 Aug 2026 | 18:00 → 19:15 | $95 USD | 12 |
| AL200 | Bogotá → Lima (BOG→LIM) | 15 Aug 2026 | 09:00 → 11:30 | $199 USD | 18 |
| AL305 | Medellín → Mexico City (MDE→MEX) | 16 Aug 2026 | 14:00 → 18:15 | $320 USD | 55 |
| AL410 | Lima → Santiago (LIM→SCL) | 17 Aug 2026 | 07:45 → 12:00 | $275 USD | 90 |
| AL520 | Santiago → São Paulo (SCL→GRU) | 18 Aug 2026 | 22:00 → 03:30 | $410 USD | 35 |

**Existing reservations:** `res-8001` (María González, AL100, **confirmed**, seat 12A) and `res-8002` (James Carter, AL200, **pending**, awaiting payment confirmation). **Aisha Khan and Diego Fernández have no reservations** — useful for demonstrating the difference between "flights on the account" and "reservations".

> The data can be viewed on the website at the `/datos` route ("Datos demo" link in the navigation), with the *Cuentas (accounts)*, *Vuelos (flights)* and *Reservas (reservations)* tables.

---

## 1. Chat Self-Service

### 1.1 Open the website

1. Open the CloudFormation output of the **CX-AIRLINE-WEBSITE** stack → take the value of `WebsiteDistributionDomainName` (the CloudFront domain, e.g. `https://d1234abcdef.cloudfront.net`). The `WebsiteDataViewerPath` output gives you the `/datos` URL directly.
2. Browse to the site. You will see the "AeroLatam" page with flights, miles and help sections.

### 1.2 Simulate a logged-in user

1. Click **"Iniciar sesión"** (Sign in) in the header.
2. Enter one of the test emails, for example: `diego.fernandez@example.com`
3. Click "Entrar". The site stores the email in sessionStorage and passes it to the chat widget as a contact attribute.

> This lets the AI agent identify the customer automatically, without asking.

### 1.3 Open the chat and talk

Click the **chat widget** (bubble in the lower-right corner). The conversation window opens.

---

### Demo 1: Knowledge Base questions

The agent answers these questions **from the knowledge base articles**, not from the model's own knowledge. The articles live in `knowledge_bases/airline/entries/<language>/`, one folder per language (`es`, `en`, `pt`): the agent retrieves the entry matching the language the customer is speaking.

Questions to try:

> **You:** How much carry-on baggage can I bring?

> **You:** How do I check in?

> **You:** How does the frequent-flyer miles program work?

> **You:** Where are the AeroLatam counters at the airport?

> **You:** What do I do if my bag didn't arrive?

**What to expect:** an answer written from the matching article, in the customer's language and citing the retrieved source. If no article covers the question, the agent must not invent the answer.

**More questions to keep exploring** (same sources, still inside the KB): how to change or cancel a reservation, seat selection, special items and sports equipment, excess weight charges, how to enroll in AeroLatam Club.

---

### Demo 2: Account lookup (MCP Tools)

These questions trigger MCP tools that query the API in real time.

> **You:** How many miles do I have?

> **You:** What flights do I have on my account?

> **You:** What flights are available from Bogotá to Medellín?

**What to expect:** the agent first resolves the account from the session email, then invokes the MCP tool. The answer may be something like the **miles balance and the traveler's tier**, or the list of flights with their times and prices, pulled live from the API via MCP. Cross-check against `/datos` that the values match the customer's record.

**Follow-up questions to try:**

> **You:** What is my frequent-flyer tier?

> **You:** How much does flight AL305 cost?

> **You:** Do I have any active reservations?

> **You:** Are there flights to Lima?

> Note: "what flights do I have?" and "do I have reservations?" use different tools (`getAccountFlights` vs `listCustomerReservations`). With Diego or Aisha the first returns data and the second comes back empty — a good moment to show that the agent picks the tool based on intent.

---

### Demo 3: Book a flight (guided form)

This demo shows a deterministic action with **human-in-the-loop, where the human in the loop is the customer**: instead of letting the model interpret the choice conversationally, the customer confirms it in a form.

> **You:** I want to book a flight

**What to expect:** the agent identifies your account, briefly says it will open a form, and returns control to the flow. In the chat you will see a **form with buttons** to pick an option (or cancel).

> **You:** *(Click one of the options in the form)*

**What to expect:** the agent picks the conversation back up, confirms the request, and gives you the new reservation's identifier with its initial status.

**Verification:** browse to `/datos` on the website → you will see the new reservation with status **`pending`**.

**Optional follow-up**, to close the loop in the same conversation:

> **You:** Can I see my reservations?

---

## 2. Voice Self-Service

### 2.1 Simulate the login and start the web call

1. Same as in chat: open the site, click **"Iniciar sesión"** and enter `diego.fernandez@example.com`. That way the call arrives already identified and the agent does not have to ask who you are.
2. In the chat widget, click the **phone / web call** icon (WebRTC call).
3. The browser will ask for **microphone** access → grant it.
4. The call connects and you will hear an **agentic voice** greeting you.

> **Note:** No phone number is required to test. The web call uses the same self-service flow and offers the same capabilities as a real call.

### 2.2 Voice dialogues

#### Knowledge base question

> **You (speaking):** "Hi, I want to know how much carry-on baggage I can bring"

**What to expect:** a spoken answer based on the KB articles, in the same language you asked in.

**Other questions to try by voice:** how to check in, how to report lost baggage, airport counter hours, how to earn and redeem miles.

#### Account lookup by voice

> **You:** "I want to know how many miles I have"

**What to expect:** it answers with the miles balance and the traveler's tier, in a natural voice.

**Other questions to try:** what flights you have on your account, what flights are available to a destination, how much a specific flight costs, the status of a reservation.

### 2.3 Flight booking by voice (separate test)

This action is worth testing on its own, because voice does **not** use the form: the confirmation is conversational and explicit.

> **You:** "I want to book a flight to Medellín"

**What to expect:** the agent presents the available flights on that route, and before executing the action it asks for an **explicit confirmation** (user confirmation is enabled on voice). Only once you confirm does it create the reservation and return the identifier.

**Verification:** browse to `/datos` on the website → you will see the new reservation with status **`pending`**.

### 2.4 Test with a phone number (optional)

For a demo with a real phone call and automatic customer recognition:

1. In the **DynamoDB** console → `airline-accounts` table → edit one of the test records (e.g. Diego Fernández) and replace `phoneNumber` with **your real phone number** in E.164 format (e.g. `+573001234567`). This lets the flow identify you automatically when you call, without asking who you are.
2. In the **Amazon Connect** console → **Phone numbers** → claim a phone number (DID).
3. Associate it with the self-service contact flow (the deployed inbound flow, `airline-selfservice-es-inbound`).
4. Call the number from your mobile — the AI agent will recognize you automatically by your number and personalize the interaction.

---

## 3. Escalation to a Human Agent

### 3.1 Prepare the human agent's environment

1. Sign in to the Amazon Connect **agent workspace** (CCP / Agent Workspace).
2. Check that your user is assigned to **BasicQueue** in its routing profile.
3. Check that the user has security-profile permissions to interact with Tools, Views and Wisdom (the same ones as the Agent Assist AI agent). **This is mandatory for section 4** — the breakdown of which permission enables what is at the top of that section.
4. Set your status to **Available** so you can receive contacts.

### 3.2 Trigger the escalation (chat)

From the website chat widget (signed in as `diego.fernandez@example.com`):

> **You:** Hi, I was charged twice for flight AL150 and I need the duplicate charge refunded.

**What to expect:** the agent recognizes that charge disputes are out of its scope, explains it, and announces the transfer to a representative.

**What happens behind the scenes:** the AI agent runs the `Escalate` tool with the reason (`billing_question`), the detected sentiment, and a summary of what self-service attempted.

### 3.3 Receive the escalation in the Agent Workspace

On your agent screen you will see (something along these lines):

1. **Immediate screen-pop** with the "escalated contact" view showing:
   - **Escalation reason:** billing_question
   - **Customer sentiment:** neutral / frustrated
   - **Customer intent:** refund of a duplicate charge on a flight
   - **Escalation summary:** (AI-generated) — what the customer asked, what self-service tried, why a human is needed
   - **Recommended action:** verify the duplicate charge and process the refund if applicable
   - **Already tried in self-service:** the account and the customer's flights were checked

2. Click **accept the contact** to start handling it.

> This demonstrates that the human agent has **full context** without the customer repeating anything.

---

## 4. Agent Assist (Helping the Human Agent)

> ### ⚠️ Prerequisite: the HUMAN agent needs the permissions too
>
> In agent assistance, tool calls are authorized against the **intersection** of
> the AI agent's security profile **and** the human agent's. It is not enough for
> the AI agent (`airline-agent-assist-iac`) to hold the permissions: the human
> user who opens the panel must carry **the same ones**, or the tools fail in
> their session only.
>
> The human agent needs all three:
>
> | Needs | Permission / grant | Without it, this breaks |
> |---|---|---|
> | **Wisdom** | `Wisdom.View` | KB suggestions and direct queries to the assistant (4.1, 4.3) |
> | **Views** | `CustomViews.Access` | the lost-baggage step-by-step guide (4.2) |
> | **MCP tools** | a `Type: MCP` application on the profile, with namespace = gateway id and the nine `airline-rest-api-oas-target___<operation>` ids | live data lookups (4.4) |
>
> The simplest path is to assign the human user the same **`airline-agent-assist-iac`** profile that Phase 3 deploys (its id is published to SSM as `SP_ASSIST_ID`), or to add those permissions and the MCP grant to their current profile.
>
> **Publish a new version of the profile after editing it.** The running agent uses the published version; if you attached the profile but did not publish, MCP calls fail with `Target entity not found` even though the gateway and the REST API are healthy.

Once you have accepted the escalated contact, the **Agent Assist** panel activates:

### 4.1 Automatic KB suggestions

While you talk to the customer, Q in Connect listens to the conversation and suggests answers. For example, if the customer brings up topics covered by the KB:

> **Customer:** "Also, on my last trip my bag didn't arrive and I don't know how to report it"

**In the Agent Assist panel you will see:**
- An answer with the baggage reporting information and a link to the KB entry (from the `maleta-perdida.txt` article)
- A **guide button "Reportar maleta perdida"** suggested automatically

### 4.2 The step-by-step guide (lost baggage)

Click the **"Reportar maleta perdida"** button in the suggestions panel.

What the guide adds is not new information: it is the **step-by-step tied to the KB entry**, presented one step at a time with "Previous" and "Next" buttons. The value is that the agent **resolves faster** — no need to read and summarize the whole article live — and that every agent gives the same instructions, in the same order, on every contact. Human in the Loop again, but now it's the Agent.

### 4.3 Direct queries to the assistant

The human agent can type questions straight into the Agent Assist panel:

> **Agent types:** "What is the baggage allowance for a platinum customer?"

**What to expect:** the answer with the details taken from the KB baggage article.

### 4.4 MCP tools from Agent Assist

The assistant can also invoke the same MCP tools as self-service, scoped to the customer on the active contact:

> **Agent types:** "How many miles does this customer have?"

> **Agent types:** "What reservations do they have?"

**What to expect:** live account data (miles and tier, flights and reservations with their status), without the agent leaving the workspace or opening another tool.

---

## 5. Additional Scenarios to Explore

### 5.1 Escalation on customer request

> **You (chat):** I'd rather talk to a person, please.

**What to expect:** the agent escalates immediately with reason `customer_request`, without insisting on solving it.

### 5.2 Out-of-scope topic

> **You:** I want to cancel my reservation

**What to expect:** the agent explains that reservation changes and cancellations are handled by a representative and escalates with reason `out_of_scope`.

### 5.3 Customer with no reservations

Sign in as `aisha.khan@example.com` (platinum tier, with flights on the account but no reservations) and ask:

> **You:** What is the status of my reservations?

**What to expect:** the agent looks it up and reports that it finds no reservations, without inventing any, and may offer to create one. Contrast with `james.carter@example.com`, whose reservation `res-8002` is in `pending` status awaiting payment confirmation.

### 5.4 Specific flight lookup

> **You:** What time does flight AL520 depart and how long is it?

### 5.5 Baggage and special items

> **You:** Can I bring a surfboard on the plane?

**What to expect:** an answer based on the KB baggage article.

---

## 6. Multi-Language (Dynamic Language Switching)

The agent supports dynamic language switching with no flow or configuration changes. It uses a multilingual (polyglot) voice covering English, Spanish and Portuguese. The agent detects the customer's language from the transcript/text and replies in that same language, also retrieving the KB articles from the matching language folder.

### 6.1 Language switching in Chat

Sign in as any customer and open the chat:

> **You:** Hi, how many miles do I have?

Now switch to Spanish:

> **You:** Gracias. ¿Cuánto equipaje de mano puedo llevar?

Try Portuguese:

> **You:** Quais voos vocês têm de Bogotá para Lima?

**What to expect:** every reply arrives in the language of the customer's last message, following the switch immediately and without losing conversation context.

### 6.2 Language switching by Voice

Start a web call and speak in different languages:

> **You (speaking English):** "Hello, I want to check my miles balance"

> **You (switching to Spanish):** "Sí, ¿me puedes decir qué vuelos tengo?"

> **You (switching to Portuguese):** "Obrigado, é tudo por hoje"

**What to expect:** the voice switches language dynamically following the customer, within the same call and with no transfers or restarts.

---

## Demo Checklist

- [ ] Website loads correctly (CloudFront)
- [ ] Email login works and is reflected in the header
- [ ] Chat widget opens and responds
- [ ] KB questions get answers based on the articles for the language in use
- [ ] Miles lookup returns real account data (matches `/datos`)
- [ ] The list of available flights matches the *Vuelos (flights)* table
- [ ] The reservation form appears when asking to book a flight
- [ ] The created reservation shows up in `/datos` with status `pending`
- [ ] Web call works and the voice sounds natural
- [ ] Booking by voice asks for explicit confirmation before executing
- [ ] Escalation transfers to the agent with full context
- [ ] Screen-pop shows the summary, reason and recommended action
- [ ] **The human user carries `Wisdom.View` + `CustomViews.Access` + the MCP grant, on a published version of the profile**
- [ ] Agent Assist suggests answers from the KB
- [ ] The lost-baggage step-by-step guide renders correctly
- [ ] The assistant answers the agent's direct queries
- [ ] Chat replies in the customer's language (test English, Spanish, Portuguese)
- [ ] Mid-conversation language switching works in chat
- [ ] Voice switches language dynamically following the caller
