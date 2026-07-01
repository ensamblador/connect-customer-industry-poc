# View design — TelcoEsimActivationGuide

Customer-managed view (`AWS::Connect::View`) for the **agent-facing**
eSIM activation step-by-step guide. Authored as `view-content.json` (the
`Content` payload of `CreateView` / `UpdateView`) and deployed via CDK
(`connect/views.py`, the existing `CustomerManagedView` construct). This
document records the view's purpose, structure, the data-binding contract
with the guide flow, the ARN convention, the Req 4 manual permission
note, and the server-deploy verification status.

_Source spec: `.kiro/specs/esim-activation-guided-view/` (Requirements
1.3–1.11, 2.1, 2.2, 5.1, 5.7). Step content sourced from
`knowledge_bases/telco-kb-es/entries/es/esim-activacion.html`._

## Purpose

Render the eSIM activation procedure one step at a time on the
Representative's agent workspace, so the Representative can walk a
customer through activation on a live contact. A single parameterized
view is rendered by one `ShowView` block per step in the guide flow
(`telco-esim-activation-guide-es`); each block supplies that step's
content via `ViewData`. The Representative advances with **Anterior** /
**Siguiente** and ends with **Finalizar**.

The view template is generic — it carries no step text itself. The
ordered Spanish step content (heading + body) lives in the flow JSON and
is injected per step through the data-binding contract below. The one
constant Representative-visible element baked into the view is the
brand/model note (Req 1.3), which never changes between steps.

The view collects no form output — it only renders the current step and
surfaces the three navigation actions back to the flow as branches.

## Structure

`Content` = `{ "Template": { Head, Body }, "Actions": ["Previous","Next","End"] }`.

- **Head** — `Title: "Guía de activación de eSIM"`; layout
  `Columns: ["12","12","12"]` (three stacked full-width rows: the step
  content, the previous-button row, then the footer).
- **Body** — top-level items are `Container`s (the server requires
  top-level Body items to be Containers):
  - `header-col` `Container` (`Columns: "12"`) — the step content:
    - `step-counter` `TextBox` (`Variant: "div"`, bold) →
      `Paso $.stepNumber de $.totalSteps` (Req 1.4).
    - `step-heading` `TextBox` (`Variant: "h3"`) → `$.stepHeading`.
    - `step-body` `TextBox` (`Variant: "p"`) → `$.stepBody`.
    - `brand-model-note` `Alert` (`type: "info"`, heading "Nota") — the
      static "los pasos exactos varían según la marca y el modelo del
      teléfono" note (Req 1.3 — constant, so static in the view).
  - `prev-col` `Container` (`Columns: "12"`, border hidden) — the
    **Previous** `Button` (`btn-previous`, `Action: "Previous"`, label
    "Anterior"). The container's `Visibility` is bound to
    `$.showPrevious` (Req 1.5, 1.6).
  - `footer-col` `Container` (`Columns: "12"`, border hidden) — the
    **Next** `Button` (`btn-next`, `Action: "Next"`, label "Siguiente",
    `Visibility` bound to `$.showNext`, Req 1.7, 1.8) and the **End**
    `Button` (`btn-end`, `Action: "End"`, label "Finalizar", always
    visible, Req 1.9).
- **Actions** — `["Previous", "Next", "End"]`: the three flow-branching
  actions the `ShowView` block surfaces as branches.

All visible text is Spanish (es-US) (Req 1.10).

## Components

| `_id` | Type | Role | Key props |
|---|---|---|---|
| `header-col` | Container | top-level row holding the step content | `Columns: "12"` |
| `step-counter` | TextBox | current/total step counter | `Variant: div`, `FontWeight: bold`, binds `$.stepNumber` / `$.totalSteps` |
| `step-heading` | TextBox | step title | `Variant: h3`, binds `$.stepHeading` |
| `step-body` | TextBox | step instructions | `Variant: p`, binds `$.stepBody` |
| `brand-model-note` | Alert | static brand/model caveat | `type: info`, `heading: "Nota"`, `dismissible: false` |
| `prev-col` | Container | row holding the Previous button | `Columns: "12"`, `Visibility: $.showPrevious` |
| `btn-previous` | Button | move to preceding step | `Action: Previous`, label "Anterior" |
| `footer-col` | Container | row holding Next + End buttons | `Columns: "12"` |
| `btn-next` | Button | move to following step | `Action: Next`, label "Siguiente", `Visibility: $.showNext` |
| `btn-end` | Button | end the guide | `Action: End`, label "Finalizar", always visible |

## Data-binding contract

The flow's per-step `ShowView` block (`step-1` .. `step-6`) drives this
view. The bindings are the contract between the flow and the view; the
`ViewData` keys must match the template refs below exactly. Each step
block supplies one step's worth of data; the view template is reused
verbatim across all six steps.

### Inputs (`ViewData` → `$.<name>` in the view)

| Template ref | Type (string in JSON) | Source (flow) | Meaning |
|---|---|---|---|
| `$.stepNumber` | string (`"1"`..`"6"`) | per-step `ViewData.stepNumber` | current step number (Req 1.4) |
| `$.totalSteps` | string (`"6"`) | per-step `ViewData.totalSteps` | total steps (Req 1.4) |
| `$.showPrevious` | string (`"true"`/`"false"`) | per-step `ViewData.showPrevious` | Previous-row visibility (Req 1.5, 1.6) |
| `$.showNext` | string (`"true"`/`"false"`) | per-step `ViewData.showNext` | Next-button visibility (Req 1.7, 1.8) |
| `$.stepHeading` | string (es-US) | per-step `ViewData.stepHeading` | step title |
| `$.stepBody` | string (es-US) | per-step `ViewData.stepBody` | step instructions |

Visibility is bound two ways that reinforce each other: the view sets
each navigation control's `Visibility` to a **structured view condition**
that tests the per-step data key, **and** the flow only declares the
corresponding condition branch on steps where it applies (step 1 sends
`showPrevious=false` with no `Previous` branch; step 6 sends
`showNext=false` with no `Next` branch). The conditions are:

- `prev-col` → `{"Conditions": [{"Equals": {"ElementByKey": "showPrevious", "ElementByValue": "true"}}]}`
- `btn-next` → `{"Conditions": [{"Equals": {"ElementByKey": "showNext", "ElementByValue": "true"}}]}`

The `End` action is always present, so `btn-end` has no `Visibility`
condition.

> **Server-schema learning (resolved).** A bare `$.showPrevious` /
> `$.showNext` placeholder string in the `Visibility` prop passes
> `validate_view_json` locally but the Connect view server **rejects** it
> at `CreateView` with an opaque `InternalServiceException` (HTTP 500),
> which surfaces in CloudFormation as a `CREATE_FAILED` on the
> `AWS::Connect::View`. Conditional visibility must instead be a
> structured condition object. Two validators disagree on its exact
> shape, and the `Visibility` value must satisfy **both**:
> - the **data plane** (`CreateView`) accepts a bare ViewCondition
>   (`{"Equals": {...}}`);
> - the **CloudFormation** `AWS::Connect::View` provider is stricter — it
>   requires the condition wrapped in a `Conditions` array
>   (`{"Conditions": [{"Equals": {...}}]}`) and rejects a bare `Equals`
>   key (`must NOT have additional properties` / `must have required
>   property 'Conditions'`).
>
> The `Conditions`-wrapped form satisfies both (confirmed: CFN deploy +
> `--status SAVED` data-plane probe → `SAVED`), so that is what the view
> uses. `$.` placeholders remain valid for **text interpolation** inside a
> component's `Content` (e.g. `$.stepHeading`); they are only invalid as a
> `Visibility` value.

### Outputs (`$.Views.Action`)

The chosen action lands at `$.Views.Action` (`"Previous"` / `"Next"` /
`"End"`), which the flow uses as the `ShowView` condition branch. This
guide collects no form output, so `$.Views.ViewResultData` is unused.

## Qualified-ARN convention ($LATEST)

The `ShowView` block references the view by its **qualified** ARN. The
CDK construct (`connect/views.py`) exposes:

- `view_arn` → `CfnView.attr_view_arn` (the unqualified ARN).
- `view_qualified_arn` → `f"{view_arn}:$LATEST"`.

The flow's `ESIM_GUIDE_VIEW_ARN_PLACEHOLDER` marker resolves at synth to
`view_qualified_arn`, i.e. the view is referenced as **`:$LATEST`**
(tracks the latest version) rather than a pinned numeric version. This
matches the existing screen-pop / newline-form convention in this
project (Req 5.3). Revisit a pinned version only if a view change ever
needs a staged rollout.

## Permissions (Requirement 4) — manual step

The view rendering in the agent workspace depends on a security-profile
permission that is **not** managed by CDK and must be applied to the
human-agent security profiles outside the stack (Assumption 4, mirroring
the project's existing agent-assist permission note):

- **Custom views - Access** (named "Agent Applications - Custom views -
  All" on the `ShowView` admin-guide page) — enables the step-by-step
  customer-managed view guide to render in the workspace (Req 4.2, 4.4).
- **Connect AI agents - View** — enables the AI-agent recommendation
  (and thus the native "Start guide" control from the content
  association) to appear (Req 4.1, 4.3).

Missing either permission degrades gracefully: the workspace omits only
the corresponding element and still renders the rest (Req 4.5) — native
Connect behavior, not something this view implements. This is the only
manual step after `cdk deploy` (Req 5.7).

## Verification status

### Local schema validation — PASS

`validate_view_json` on the `Content` payload of `view-content.json`:

```
valid: true, error_count: 0, warning_count: 0
"View is valid. No issues found."
```

The local validator checks structural rules (top-level shape, Head/Body
shape, per-component `_id`/`Type`/`Props`, `_id` uniqueness, `Type`
against the catalog, required props, and `Props.Action` ↔ top-level
`Actions` cross-checks). It does **not** validate the full per-component
`Props` schema or the runtime serialization of results.

### Server-schema deploy (`--status SAVED`) — PASS

A `--status SAVED` `create-view` probe against the reference instance
(`30b0e238-…`, us-west-2) catches server-schema gaps the local validator
misses. It **caught one**: a `$.`-bound `Visibility` prop (the original
authoring) was accepted locally but returned `InternalServiceException`
(500) at `CreateView`, which is why the first `cdk deploy` failed with a
`CREATE_FAILED` on the view. The fix — a structured `ViewCondition` on
`Visibility` (see the data-binding contract above) — was then confirmed
with the same probe: the view creates with `Status: SAVED`. The throwaway
probe views were deleted afterward so they do not collide with the
CDK-managed `TelcoEsimActivationGuide`.

### Runtime confirmation — PENDING (credentials)

The `Visibility`-bound-to-`ViewData` behavior (the Previous-row and Next
button showing/hiding per step from `$.showPrevious` / `$.showNext`) and
the live render of the step content on the agent workspace are confirmed
in the live end-to-end check, which needs a deployed instance and the
Req 4 security-profile permissions assigned. Binding `Visibility` to a
per-step `ViewData` boolean is the one item to re-confirm at runtime;
until then the dual flow-branch + view-binding design is the safe
assumption to build the flow on.
