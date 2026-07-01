# telco-kb-es — KB content spec

Spanish (US) telco self-service knowledge base. Feeds the deployed
`telco-selfservice-es-us` Connect AI agent via its system `Retrieve`
tool. v1 RAG scope: general information only; anything account-touching
is out of scope and the agent escalates.

> **All facts in these entries are generic placeholders.** Replace
> prices, speeds, coverage claims, store hours, and roaming terms with
> the carrier's real data before going to production. Placeholder
> values are written so they read naturally but are obviously
> illustrative (e.g. "desde 20 dólares al mes").

## Spec (stage 1)

| Field | Value |
|---|---|
| Domain | US Spanish telco self-service (v1) |
| Knowledge base | `telco-kb-es` — **must be created as type CUSTOM** (does not exist yet) |
| Locale | `es-US` (matches AI agent locale, Lex bot `es_US`, Polly Lupe) |
| Audience | End-customer self-service, voice-first / chat-ready |
| Retrieve tool(s) | Single system `Retrieve`; tags segment within the one KB |
| Domain (assistant) | `e1de1c2a-08ea-49e9-9dae-2ad3c80e78fd` (us-west-2) |

### Topics in scope
1. **plans** — Planes móviles, datos, precios generales.
2. **coverage** — Cobertura 4G/5G, disponibilidad por zona.
3. **devices** — Compatibilidad de equipos, BYOD, eSIM.
4. **stores** — Horarios y ubicaciones de tiendas.
5. **faq** — Preguntas frecuentes (activación, APN, roaming básico).

### Out of scope (agent escalates via `Escalate`, not answered from KB)
- Saldo, factura, fecha de vencimiento (account access).
- Estado de cortes / averías de red (outage status).
- Pagos, cambios de plan, altas / bajas de línea (transactions).
- Disputas de facturación, asesoría legal.

### Entry inventory
| Entry | Title | Source | Format | Tags |
|---|---|---|---|---|
| planes-moviles | Planes móviles y qué incluyen | drafted | text/plain | topic=plans |
| cobertura-4g-5g | Cobertura 4G y 5G por zona | drafted | text/plain | topic=coverage |
| compatibilidad-equipos | Compatibilidad de equipos y BYOD | drafted | text/plain | topic=devices |
| esim-activacion | eSIM: qué es y cómo activarla | drafted | text/plain | topic=devices |
| horarios-tiendas | Horarios y ubicaciones de tiendas | drafted | text/plain | topic=stores |
| faq-general | Preguntas frecuentes | drafted | text/plain | topic=faq |
| roaming-basico | Roaming internacional (información general) | drafted | text/plain | topic=faq |

### Success criteria
A coverage question retrieves `cobertura-4g-5g`, not `planes-moviles`.
Store-hours questions hit `horarios-tiendas`. All answers in Spanish,
TTS-friendly. Account/billing questions retrieve nothing useful (→
agent escalates).

## Tag taxonomy (stage 4)

| Key | Values | Purpose |
|---|---|---|
| topic | plans, coverage, devices, stores, faq | primary content segment |
| locale | es-US | language alignment |

Retrieve tool filter (per segment), set as Retrieve-tool override input
values:

```
retrievalConfiguration.filter.equals.key   = topic
retrievalConfiguration.filter.equals.value = coverage   # (or plans/devices/stores/faq)
```

v1 ships a single Retrieve with no filter (queries the whole KB). The
tags are in place so a future build can add per-topic Retrieve tools or
a filtered Retrieve without re-tagging.

## Deploy dependencies

1. **Create the CUSTOM KB first** (does not exist):
   ```bash
   aws qconnect create-knowledge-base \
     --name telco-kb-es \
     --knowledge-base-type CUSTOM \
     --region us-west-2 --profile connect-chat
   ```
   Then associate it with the assistant
   (`e1de1c2a-...`) as a KB association so the `Retrieve` tool can
   query it.
2. Upload + tag each entry (Stage 5 in the skill / `_deploy.py`).
3. Tag the KB content with `topic` + `locale` via `tag-resource`.
