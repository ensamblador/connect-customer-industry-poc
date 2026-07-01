# View: telco-escalation-handoff

Customer-managed view that screen-pops the human agent with all the
escalation context the AI self-service agent captured before handing
off. Display-only (no form inputs) — the agent reads the context and
clicks one acknowledge button.

Paired with:
- Agent (RTC tool source): `projects/telco-cx/connect_ai_agents/telco-selfservice-es-us`
  (Escalate tool, v4).
- Main flow: `projects/telco-cx/flows/telco-selfservice-es-inbound/flow.json`
  (`copy-context` block writes the contact attributes this view reads).
- Screen-pop flow (DefaultAgentUI): `projects/telco-cx/flows/telco-agent-screenpop-es`
  (the flow that actually mounts this view via a `ShowView` block on
  agent accept).
- Escalate module: `projects/_samples/flows/escalate-to-agent` (sets the DefaultAgentUI
  event hook + transfers to queue).

## View spec

**Name:** telco-escalation-handoff
**View kind:** Customer-managed
**Channels:** Voice (escalation handoff from voice self-service)
**Audience:** Agent (in workspace)
**Host context:** DefaultAgentUI screen-pop flow → `ShowView` block,
mounted on agent accept via `UpdateContactEventHooks`.

### Purpose
Show the receiving human agent everything the AI agent learned during
self-service — reason, sentiment, priority, what was already tried,
recommended next action — so the agent acts fast and the customer
doesn't repeat themselves.

### Trigger
On agent accept of the escalated contact. The escalate-to-agent
module sets the `DefaultAgentUI` event hook to the screen-pop flow;
Connect runs that flow when the agent accepts, and its `ShowView`
block mounts this view.

### Data inputs (contact attributes set by the main flow `copy-context`)
- `escalationReason`   ← `$.Lex.SessionAttributes.escalationReason`
- `escalationSummary`  ← `$.Lex.SessionAttributes.escalationSummary`
- `customerIntent`     ← `$.Lex.SessionAttributes.customerIntent`
- `sentiment`          ← `$.Lex.SessionAttributes.sentiment`
- `escalationPriority` ← `$.Lex.SessionAttributes.escalationPriority`
- `resolutionAttempted`← `$.Lex.SessionAttributes.resolutionAttempted`
- `recommendedAction`  ← `$.Lex.SessionAttributes.recommendedAction`
- `topicsDiscussed`    ← `$.Lex.SessionAttributes.topicsDiscussed`

The screen-pop flow's `ShowView` block passes these into the view as
a flat `ViewContent` object whose keys match the `$.X` template
strings the view references (e.g. `escalationReason`, `sentiment`).

### Display elements
- Left column (4/12): priority Alert, "Contexto de escalación"
  heading, AttributeSection with Motivo / Sentimiento / Prioridad.
- Right column (8/12): customer-intent Alert, AttributeBar
  (Intención / Temas), disabled TextArea for escalationSummary,
  disabled TextArea for recommendedAction, label + TextBox for
  resolutionAttempted.
- Footer: full-width Container (`footer-col`) holding a single primary
  Button with text "Entendido" in its `Content` (the Button component
  has no `Label` prop). `Head.Columns` is `["4", "8", "12"]` so the
  footer gets its own full-width row below the two content columns.

### Form inputs
None. Display-only. The TextAreas are `Disabled: true` so they render
the AI-generated text read-only without collecting anything back.

### Actions and branches
- "Entendido" → `ActionSelected` → screen-pop flow ends the ShowView
  branch (agent stays on the live contact).

### Output
None captured. `$.Views.ViewResultData` is empty — this is a
read-only context card.

### Edge cases
- Missing attribute at runtime → the `$.X` string resolves to empty;
  the component renders blank rather than erroring. Acceptable for a
  context card (optional Escalate fields are frequently empty).
- Agent dismisses without clicking → no downstream effect; the
  contact is already connected.

### Success criteria
Agent can see reason + recommended action within the first seconds of
accept, without asking the customer to repeat context.

## Layout outline

```yaml
view: telco-escalation-handoff
view_kind: Customer-managed
host: DefaultAgentUI screen-pop flow → ShowView block

layout:
  Head:
    Title: "Contacto escalado"
    Configuration.Layout.Columns: ["4", "8", "12"]

  Body:
    - Container [_id: left-col, Columns: 12]
        - Alert [_id: priority-alert, type: warning, heading: "Prioridad"]
            Content ← $.escalationPriority
        - TextBox [_id: ctx-heading, bold heading-m] "Contexto de escalación"
        - AttributeSection [_id: esc-attrs]
            - Motivo       ← $.escalationReason
            - Sentimiento  ← $.sentiment
            - Prioridad    ← $.escalationPriority

    - Container [_id: right-col, Columns: 12]
        - Alert [_id: reason-alert, type: info, heading: "Motivo de escalación"]
            Content ← $.customerIntent
        - AttributeBar [_id: intent-bar]
            - Intención del cliente ← $.customerIntent
            - Temas tratados        ← $.topicsDiscussed
        - TextArea [_id: esc-summary, Disabled, Label "Resumen de escalación"]
            DefaultValue ← $.escalationSummary
        - TextArea [_id: recommended, Disabled, Label "Acción recomendada"]
            DefaultValue ← $.recommendedAction
        - TextBox [_id: attempted-label, bold] "Ya intentado en autoservicio:"
        - TextBox [_id: attempted, p]
            Content ← $.resolutionAttempted

    - Button [_id: ack, primary, Action: ActionSelected]
        Content: ["Entendido"]   # Button has no Label prop; text lives in Content
      (wrapped in full-width Container footer-col)

actions:
  - ActionSelected → ShowView block branch (agent acknowledges)

data inputs:
  - escalationReason, escalationSummary, customerIntent, sentiment,
    escalationPriority, resolutionAttempted, recommendedAction,
    topicsDiscussed  (all contact attributes from main flow copy-context)

outputs:
  - none (display-only)
```

## Deploy

```bash
AWS_PROFILE=connect-chat uv run --with boto3 python .kiro/skills/connect-view-author/scripts/deploy_connect_view.py \
  --view-file projects/telco-cx/views/telco-escalation-handoff/view.json \
  --view-name TelcoEscalationHandoff \
  --actions ActionSelected \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --region us-west-2 \
  --artifact-dir projects/telco-cx/views/telco-escalation-handoff
```

Validated clean with `validate_view_json` (0 errors, 0 warnings).
