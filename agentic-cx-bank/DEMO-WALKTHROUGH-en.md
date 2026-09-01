# Demo Script — Bank PoC

> 🌐 **Languages:** [Español](./DEMO-WALKTHROUGH.md) · **English** (this file)

Step-by-step guide for demonstrating the banking PoC capabilities. It gives you the questions to use and what to expect at each step, without scripting the agent's replies (they are generated live and vary).

---

## Test Data

Before you start, get familiar with the available synthetic data:

| Customer | Email | Phone | Product | Balance | Due date | Status |
|----------|-------|-------|---------|---------|----------|--------|
| María González | maria.gonzalez@example.com | +12065550101 | Cuenta Nómina | $1,540.75 | 20 Jun 2026 | active |
| James Carter | james.carter@example.com | +12065550102 | Tarjeta Clásica | $320.00 | 28 Jun 2026 | active |
| Aisha Khan | aisha.khan@example.com | +12065550103 | Tarjeta Oro | $5,820.40 | 10 Jun 2026 | suspended |
| Diego Fernández | diego.fernandez@example.com | +12065550104 | Cuenta Nómina | $980.15 | 1 Jul 2026 | active |

**Available products:**
- Cuenta Nómina (payroll account): no maintenance fee, free debit card, $0/year
- Tarjeta Clásica: contactless payments and purchase protection, $30/year
- Tarjeta Oro: 2% cashback, travel insurance, VIP lounges, $120/year
- Tarjeta Platino: 3% cashback, premium insurance, VIP lounges and concierge, $180/year

**Existing cards:** `card-9001` (María González, Clásica, **active**, ending 4821) and `card-9002` (Aisha Khan, Oro, **requested**, pending issuance). **James Carter and Diego Fernández have no cards** — useful for a request from scratch.

> The data can be viewed on the website at the `/datos` route ("Datos demo" link in the navigation), with the *Cuentas (accounts)*, *Productos (products)* and *Tarjetas (cards)* tables.

---

## 1. Chat Self-Service

### 1.1 Open the website

1. Open the CloudFormation output of the **CX-BANCO-WEBSITE** stack → take the value of `WebsiteDistributionDomainName` (the CloudFront domain, e.g. `https://d1234abcdef.cloudfront.net`). The `WebsiteDataViewerPath` output gives you the `/datos` URL directly.
2. Browse to the site. You will see the "Latam Banco" page with accounts, cards and digital banking sections.

### 1.2 Simulate a logged-in user

1. Click **"Iniciar sesión"** (Sign in) in the header.
2. Enter one of the test emails, for example: `diego.fernandez@example.com`
3. Click "Entrar". The site stores the email in sessionStorage and passes it to the chat widget as a contact attribute.

> This lets the AI agent identify the customer automatically, without asking.

### 1.3 Open the chat and talk

Click the **chat widget** (bubble in the lower-right corner). The conversation window opens.

---

### Demo 1: Knowledge Base questions

The agent answers these questions **from the knowledge base articles**, not from the model's own knowledge. The articles live in `knowledge_bases/bank/entries/<language>/`, one folder per language (`es`, `en`, `pt`): the agent retrieves the entry matching the language the customer is speaking.

Questions to try:

> **You:** How do I activate my new card?

> **You:** What fees do you charge for maintaining the account?

> **You:** What are the branch opening hours?

> **You:** How do I transfer money to another bank?

> **You:** What's the difference between the debit and the credit card?

**What to expect:** an answer written from the matching article, in the customer's language and citing the retrieved source. If no article covers the question, the agent must not invent the answer.

**More questions to keep exploring** (same sources, still inside the KB): what account types exist and what they include, contactless payments, managing cards from the mobile app, trouble signing in to online banking, transfer limits and timing.

---

### Demo 2: Account lookup (MCP Tools)

These questions trigger MCP tools that query the API in real time.

> **You:** What is my account balance?

> **You:** What products do you have available?

> **You:** What cards do I have?

**What to expect:** the agent first resolves the account from the session email, then invokes the MCP tool. The answer may be something like the **balance and its due date**, pulled live from the API via MCP. Cross-check against `/datos` that the values match the customer's record.

**Follow-up questions to try:**

> **You:** When is my next payment due?

> **You:** Which card has the lowest annual fee?

> **You:** How much cashback does the Tarjeta Platino give?

> **You:** Do I have any card request in progress?

> Note: `listProducts` accepts a maximum-annual-fee filter, so questions like "which cards cost less than 50 a year?" show the filtering happening on the tool side, not in the model.

---

### Demo 3: Request a card (guided form)

This demo shows a deterministic action with **human-in-the-loop, where the human in the loop is the customer**: instead of letting the model interpret the choice conversationally, the customer confirms it in a form.

> **You:** I want to apply for a credit card

**What to expect:** the agent identifies your account, briefly says it will open a form, and returns control to the flow. In the chat you will see a **form with buttons** to pick an option (or cancel).

> **You:** *(Click one of the options in the form)*

**What to expect:** the agent picks the conversation back up, confirms the request, and gives you the new card's identifier with its initial status.

**Verification:** browse to `/datos` on the website → you will see the new product or service with status **`requested`**.

**Optional follow-up**, to close the loop in the same conversation:

> **You:** Can I see my requested cards?

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

> **You (speaking):** "Hi, I want to know how to activate my new card"

**What to expect:** a spoken answer based on the KB articles, in the same language you asked in.

**Other questions to try by voice:** account fees, branch hours, how to make a transfer, differences between debit and credit.

#### Account lookup by voice

> **You:** "I want to know how much I have in my account"

**What to expect:** it answers with the balance and its due date, in a natural voice.

**Other questions to try:** which product you hold, what products are available, when the next payment is due, the status of a card.

### 2.3 Card request by voice (separate test)

This action is worth testing on its own, because voice does **not** use the form: the confirmation is conversational and explicit.

> **You:** "I want to apply for a credit card"

**What to expect:** the agent presents the product options, and before executing the action it asks for an **explicit confirmation** (user confirmation is enabled on voice). Only once you confirm does it create the request and return the new card's identifier.

**Verification:** browse to `/datos` on the website → you will see the new card with status **`requested`**.

### 2.4 Test with a phone number (optional)

For a demo with a real phone call and automatic customer recognition:

1. In the **DynamoDB** console → `banco-accounts` table → edit one of the test records (e.g. Diego Fernández) and replace `phoneNumber` with **your real phone number** in E.164 format (e.g. `+573001234567`). This lets the flow identify you automatically when you call, without asking who you are.
2. In the **Amazon Connect** console → **Phone numbers** → claim a phone number (DID).
3. Associate it with the self-service contact flow (the deployed inbound flow, `banco-selfservice-es-inbound`).
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

> **You:** Hi, there's a $980.15 charge on my account I don't recognize. I need to dispute it and get my money back.

**What to expect:** the agent recognizes that charge disputes are out of its scope, explains it, and announces the transfer to a representative.

**What happens behind the scenes:** the AI agent runs the `Escalate` tool with the reason (`billing_question`), the detected sentiment, and a summary of what self-service attempted.

### 3.3 Receive the escalation in the Agent Workspace

On your agent screen you will see (something along these lines):

1. **Immediate screen-pop** with the "escalated contact" view showing:
   - **Escalation reason:** billing_question
   - **Customer sentiment:** neutral / frustrated
   - **Customer intent:** dispute of an unrecognized charge and a refund request
   - **Escalation summary:** (AI-generated) — what the customer asked, what self-service tried, why a human is needed
   - **Recommended action:** review the disputed charge and open the case if applicable
   - **Already tried in self-service:** the account and the outstanding balance were checked

2. Click **accept the contact** to start handling it.

> This demonstrates that the human agent has **full context** without the customer repeating anything.

---

## 4. Agent Assist (Helping the Human Agent)

> ### ⚠️ Prerequisite: the HUMAN agent needs the permissions too
>
> In agent assistance, tool calls are authorized against the **intersection** of
> the AI agent's security profile **and** the human agent's. It is not enough for
> the AI agent (`banco-agent-assist-iac`) to hold the permissions: the human user
> who opens the panel must carry **the same ones**, or the tools fail in their
> session only.
>
> The human agent needs all three:
>
> | Needs | Permission / grant | Without it, this breaks |
> |---|---|---|
> | **Wisdom** | `Wisdom.View` | KB suggestions and direct queries to the assistant (4.1, 4.3) |
> | **Views** | `CustomViews.Access` | the card-activation step-by-step guide (4.2) |
> | **MCP tools** | a `Type: MCP` application on the profile, with namespace = gateway id and the nine `banco-rest-api-oas-target___<operation>` ids | live data lookups (4.4) |
>
> The simplest path is to assign the human user the same **`banco-agent-assist-iac`** profile that Phase 3 deploys (its id is published to SSM as `SP_ASSIST_ID`), or to add those permissions and the MCP grant to their current profile.
>
> **Publish a new version of the profile after editing it.** The running agent uses the published version; if you attached the profile but did not publish, MCP calls fail with `Target entity not found` even though the gateway and the REST API are healthy.

Once you have accepted the escalated contact, the **Agent Assist** panel activates:

### 4.1 Automatic KB suggestions

While you talk to the customer, Q in Connect listens to the conversation and suggests answers. For example, if the customer brings up topics covered by the KB:

> **Customer:** "Also, a new card arrived and I don't know how to activate it"

**In the Agent Assist panel you will see:**
- An answer with the card activation information and a link to the KB entry (from the `activar-tarjeta.txt` article)
- A **guide button "Activar tarjeta"** suggested automatically

### 4.2 The step-by-step guide (activate card)

Click the **"Activar tarjeta"** button in the suggestions panel.

What the guide adds is not new information: it is the **step-by-step tied to the KB entry**, presented one step at a time with "Previous" and "Next" buttons. The value is that the agent **resolves faster** — no need to read and summarize the whole article live — and that every agent gives the same instructions, in the same order, on every contact. Human in the Loop again, but now it's the Agent.

### 4.3 Direct queries to the assistant

The human agent can type questions straight into the Agent Assist panel:

> **Agent types:** "What are the branch hours on Saturdays?"

**What to expect:** the answer with the details taken from the KB branches article.

### 4.4 MCP tools from Agent Assist

The assistant can also invoke the same MCP tools as self-service, scoped to the customer on the active contact:

> **Agent types:** "What is this customer's balance?"

> **Agent types:** "What cards do they have?"

**What to expect:** live account data (balance and due date, cards and their status), without the agent leaving the workspace or opening another tool.

---

## 5. Additional Scenarios to Explore

### 5.1 Escalation on customer request

> **You (chat):** I'd rather talk to a person, please.

**What to expect:** the agent escalates immediately with reason `customer_request`, without insisting on solving it.

### 5.2 Out-of-scope topic

> **You:** I want to transfer $500 to another account

**What to expect:** the agent explains that it does not execute payments or transfers and escalates with reason `out_of_scope`. Note the contrast with Demo 1: the agent **does** explain how to make a transfer (KB content), but **does not** execute it.

### 5.3 Suspended account

Sign in as `aisha.khan@example.com` and ask:

> **You:** Why can't I use my card?

**What to expect:** the agent looks up the account, detects the `suspended` status, ties it to the outstanding balance, and offers a transfer to a representative for reactivation.

> Aisha also already has a card request in `requested` status (`card-9002`), so asking for another card in that session is a good way to see how the agent handles a request already in progress.

### 5.4 Specific product lookup

> **You:** What benefits does the Tarjeta Oro include?

### 5.5 Fees

> **You:** Do you charge me anything for using online banking?

**What to expect:** an answer based on the KB fees article.

---

## 6. Multi-Language (Dynamic Language Switching)

The agent supports dynamic language switching with no flow or configuration changes. It uses a multilingual (polyglot) voice covering English, Spanish and Portuguese. The agent detects the customer's language from the transcript/text and replies in that same language, also retrieving the KB articles from the matching language folder.

### 6.1 Language switching in Chat

Sign in as any customer and open the chat:

> **You:** Hi, I'd like to know my balance

Now switch to Spanish:

> **You:** Gracias. ¿Cómo activo mi tarjeta nueva?

Try Portuguese:

> **You:** Quais produtos vocês oferecem?

**What to expect:** every reply arrives in the language of the customer's last message, following the switch immediately and without losing conversation context.

### 6.2 Language switching by Voice

Start a web call and speak in different languages:

> **You (speaking English):** "Hello, I want to check my account balance"

> **You (switching to Spanish):** "Sí, ¿me puedes decir qué comisiones tiene mi cuenta?"

> **You (switching to Portuguese):** "Obrigado, é tudo por hoje"

**What to expect:** the voice switches language dynamically following the customer, within the same call and with no transfers or restarts.

---

## Demo Checklist

- [ ] Website loads correctly (CloudFront)
- [ ] Email login works and is reflected in the header
- [ ] Chat widget opens and responds
- [ ] KB questions get answers based on the articles for the language in use
- [ ] Balance lookup returns real account data (matches `/datos`)
- [ ] The product list matches the *Productos (products)* table
- [ ] The card-request form appears when asking for a card
- [ ] The requested card shows up in `/datos` with status `requested`
- [ ] Web call works and the voice sounds natural
- [ ] Card request by voice asks for explicit confirmation before executing
- [ ] Escalation transfers to the agent with full context
- [ ] Screen-pop shows the summary, reason and recommended action
- [ ] **The human user carries `Wisdom.View` + `CustomViews.Access` + the MCP grant, on a published version of the profile**
- [ ] Agent Assist suggests answers from the KB
- [ ] The card-activation step-by-step guide renders correctly
- [ ] The assistant answers the agent's direct queries
- [ ] Chat replies in the customer's language (test English, Spanish, Portuguese)
- [ ] Mid-conversation language switching works in chat
- [ ] Voice switches language dynamically following the caller
