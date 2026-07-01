# telco-esim-activation-guide-es — eSIM activation step-by-step guide flow

The flow that walks a Representative through the eSIM activation
procedure one step at a time, rendering the `TelcoEsimActivationGuide`
customer-managed view on the agent workspace via a chain of `ShowView`
blocks. It is the `flowARN` referenced by the `AMAZON_CONNECT_GUIDE`
content association, so it launches natively from the
`telco-agent-assist-es` recommendation of the `esim-activacion` article.

Like `telco-agent-screenpop-es`, it is **not** in the customer's call
path — it runs as its own agent-workspace surface. Its terminal
`DisconnectParticipant` ends the *guide* contact and removes the view
from the workspace; the underlying customer contact is a separate leg
that stays connected.

## Architecture (why a separate surface, one block per step)

The guide is a **single parameterized customer-managed view rendered by
one `ShowView` block per step**. The flow chains the six step blocks
with `Next` / `Previous` condition branches and an `End` action:

1. Each `ShowView` block renders exactly one step and blocks on the
   Representative's action — the native step-by-step guide mechanic. The
   block's conditional branches *are* the `Next` / `Previous` / `End`
   actions the view declares.
2. Per-step content (heading, body, step number, button visibility) is
   supplied by each block's `ViewData` ("Set manually"), so the view
   template stays generic and the Spanish step text lives here in the
   flow JSON.
3. This extends the proven screen-pop pattern (`telco-agent-screenpop-es`):
   a single customer-managed view + `ShowView` on the agent-workspace
   surface, referenced by `:$LATEST` qualified ARN — from one block to a
   six-block chain.

### Surface choice

`ShowView`-based step-by-step guides route to the **agent workspace** as
their own surface, so the terminal `DisconnectParticipant` ends the
guide contact and removes the view from the workspace — it does **not**
disconnect, transfer, or otherwise change the underlying customer
contact, which is a separate leg. Rendering on the end customer's screen
is out of scope for this flow and is only reachable if a customer-facing
display target is deliberately selected on a `ShowView` block — which
this flow does not do.

### Explicit-only termination graph

Termination is **explicit-only**: the single terminal block is reachable
*only* via a Representative's explicit **End** action. Every other branch
routes back into the step graph:

- Each step's `Next` / `Previous` condition branches target the adjacent
  step block.
- Each step's `End` condition branch targets the single terminal block.
- Each step's error branches — `NoMatchingCondition`, `NoMatchingError`,
  and `TimeLimitExceeded` (the timeout) — target **the same step block**
  (re-display). No error or timeout branch reaches the terminal.
- Step 1 declares **no** `Previous` branch (`showPrevious=false`); step 6
  declares **no** `Next` branch (`showNext=false`).

### Re-display tradeoff

The `ShowView` docs warn that looping an error/timeout branch back to the
same step can run until the chat contact times out, and recommend a
`Loop` block to cap retries. The requirements (2.3 / 2.7) deliberately
require re-display **without** auto-termination, so this flow re-displays
the current step directly and does **not** cap retries. This is low-risk
here because the surface is the agent's own workspace during a live
contact (agent-driven, short-lived), not an unattended customer leg. The
only exit is the explicit `End` action. If a retry cap is ever wanted, it
must still end on the explicit `End` path to honor Req 2.3.

## Spec

| Field | Value |
|---|---|
| Name | `telco-esim-activation-guide-es` |
| Artifact kind | Contact flow (`CONTACT_FLOW`) |
| Instance | `30b0e238-b3bd-4f61-9f04-c0b24e4a2f74` (us-west-2) |
| View shown | `TelcoEsimActivationGuide` (`:$LATEST`, injected at synth) |
| ARN marker | `ESIM_GUIDE_VIEW_ARN_PLACEHOLDER` → resolved by CDK `replacements` |
| Steps | 6 (sourced from `knowledge_bases/telco-kb-es/entries/es/esim-activacion.html`) |

## Structure

```
StartAction: set-logging
  set-logging  (UpdateFlowLoggingBehavior: Enabled)   # no Errors array (see learnings)
    → step-1
  step-1 .. step-6  (ShowView, ViewResource.Id = ESIM_GUIDE_VIEW_ARN_PLACEHOLDER)
    Conditions: Next → step k+1 (except step-6), Previous → step k-1 (except step-1), End → end-guide
    Errors:     NoMatchingCondition | TimeLimitExceeded | NoMatchingError → step k (re-display)
  end-guide  (DisconnectParticipant)   # reachable only via an End branch
```

The six steps, sourced from `esim-activacion.html`, in order:

| # | `stepHeading` (es-US) | `showPrevious` | `showNext` |
|---|---|---|---|
| 1 | Confirma que el teléfono es compatible con eSIM (ajustes de red / datos móviles) | false | true |
| 2 | Conecta el teléfono a una red wifi | true | true |
| 3 | Abre los ajustes de red y elige "agregar eSIM" | true | true |
| 4 | Escanea el código QR enviado por correo o sigue las instrucciones en pantalla | true | true |
| 5 | Espera a que se complete la activación (suele tardar unos minutos) | true | true |
| 6 | Confirma que la línea está activa | true | false |

### ViewData → view binding

Each `ShowView` block supplies the view's flat keys per step. The view
template binds these (`$.stepNumber`, `$.showPrevious`, etc.); the
Spanish step text lives in the flow:

```json
"ViewData": {
  "stepNumber":   "1",
  "totalSteps":   "6",
  "showPrevious": "false",
  "showNext":     "true",
  "stepHeading":  "Confirma que el teléfono es compatible con eSIM ...",
  "stepBody":     "En los ajustes del teléfono, ve a la sección de red ..."
}
```

`showPrevious` / `showNext` drive the view's `Visibility` bindings, and
on each step the flow declares the matching condition branch only where
the button is shown (no `Previous` branch on step 1, no `Next` branch on
step 6) — the two mechanisms reinforce each other. All `ViewData` values
are strings, including the booleans (`"true"` / `"false"`) and the step
numbers (`"1"`..`"6"`).

## Learnings (carried over from telco-agent-screenpop-es)

1. **`UpdateFlowLoggingBehavior` must NOT carry an `Errors` array.**
   The create API rejects it with `Invalid Action error. Error:
   NoMatchingError, Path: Actions[0]`. The `set-logging` block declares
   only `Transitions.NextAction`. The MCP `validate_flow_json` does
   **not** catch this — it passes locally then 400's server-side.
2. **`ShowView.ViewResource.Id` takes the view ARN with a `:$LATEST`
   suffix**, not a bare view ID. Here it is the
   `ESIM_GUIDE_VIEW_ARN_PLACEHOLDER` marker, resolved by the CDK
   `ContactFlow` `replacements` to the view's `view_qualified_arn`
   (`:$LATEST`) at synth, so the repo carries no hard-coded ARN.
3. **`InvocationTimeLimitSeconds` is a string** in the flow JSON
   (`"1200"`), matching the screen-pop reference.

## Deploy

In this project the flow is deployed by CDK (`connect/flows.py`
`ContactFlow`), gated by `config.BUILD_ESIM_GUIDE` (+ `HAS_REAL_INSTANCE`),
with `replacements={"ESIM_GUIDE_VIEW_ARN_PLACEHOLDER": view.view_qualified_arn}`.
For a manual create/update against the reference instance:

```bash
# Create  (resolve ESIM_GUIDE_VIEW_ARN_PLACEHOLDER to a real :$LATEST ARN first)
AWS_PROFILE=connect-chat aws connect create-contact-flow \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --name telco-esim-activation-guide-es --type CONTACT_FLOW \
  --content file://projects/telco-cx/flows/telco-esim-activation-guide-es/flow.json \
  --region us-west-2

# Update
AWS_PROFILE=connect-chat aws connect update-contact-flow-content \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --contact-flow-id <flow-id> \
  --content file://projects/telco-cx/flows/telco-esim-activation-guide-es/flow.json \
  --region us-west-2
```

## Verification status

- **Local** — `validate_flow_json` → 0 errors; graph property tests
  (`tests/unit/test_esim_guide_flow_properties.py`) cover step-block
  well-formedness, per-step navigation/visibility/timeout invariants, and
  termination/reference integrity.
- **Live (pending creds)** — single `cdk deploy` resolves the view ARN
  marker, creates the flow, and the content association launches it from
  the recommendation. Confirm on a live instance that the
  `Visibility`-bound buttons render per step and that **End** removes the
  view while the customer contact stays connected.
- **Permissions (manual, live instance)** — human-agent security profiles
  need "Connect AI agents - View" and "Custom views - Access" for the
  recommendation and the guide to render (Req 4).
