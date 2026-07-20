# View design — TelcoNewLineForm

Customer-managed view (`AWS::Connect::View`) for the **chat** new-line
guided form. Authored as `view-content.json` (the `Content` payload of
`CreateView` / `UpdateView`) and deployed via CDK (`cdk_constructs/connect/views.py`,
task 4). This document records the view's purpose, structure, the
data-binding contract with the flow, the validation decisions, the ARN
convention, and the server-deploy verification status.

_Source spec: `.kiro/specs/telco-newline-guided-form/` (Requirements
3.1–3.5, 6.6). Component research: `component-findings.md` (task 3.2)._

## Purpose

Render a structured new-line request form in the customer's chat window
after the chat agent hands control back to the flow via the
`ShowNewLineGuide` Return-to-Control tool. The customer picks a plan,
optionally enters a 3-digit area code and notes, then **Submit**s (or
**Cancel**s). The form's output is bridged back into the chat assistant,
which creates the line via the existing `newLine` MCP tool and confirms
the `lineId`. Voice never reaches this view (only the chat agent carries
`ShowNewLineGuide`).

The view collects input only — it never creates the line itself. The
single creation route stays the `newLine` MCP tool (shared with voice).

## Structure

`Content` = `{ "Template": { Head, Body }, "Actions": ["Submit","Cancel"] }`.

- **Head** — `Title: "Nueva línea"`; layout `Columns: ["12","12"]` (two
  stacked full-width rows: the form, then the footer).
- **Body** — top-level items are `Container`s (the server requires
  top-level Body items to be Containers):
  - `form-col` `Container` (`Columns: "12"`) → contains the `Form`
    (`newline-form`) with one `Section` ("Solicitud de nueva línea"):
    - `Dropdown` `plan-id` — `Name: "planId"`, `Required: "true"`,
      `Options: "$.planOptions"` (bound at mount), `DefaultValue:
      "$.defaultPlanId"` (prefill), `Label: "Plan"`, helper text in
      Spanish.
    - `FormInput` `area-code` — `Name: "areaCode"`, optional, `Label:
      "Código de área (opcional)"`, `DefaultValue: "$.defaultAreaCode"`,
      `HelperText: "3 dígitos"`.
    - `TextArea` `notes` — `Name: "notes"`, optional, `Label: "Notas
      (opcional)"`.
  - `footer-col` `Container` (`Columns: "12"`, border hidden) →
    `SubmitButton` `submit` (`Action: "Submit"`, label "Enviar
    solicitud") and `Button` `cancel` (`Action: "Cancel"`, text via
    `Content: ["Cancelar"]`, not `Label`).
- **Actions** — `["Submit", "Cancel"]`: the two flow-branching actions
  the `ShowView` block surfaces as branches.

All visible text is Spanish (es-US), consistent with the chat agent's
locale (Req 3.5).

## Components

| `_id` | Type | Role | Key props |
|---|---|---|---|
| `form-col` | Container | top-level row holding the form | `Columns: "12"` |
| `newline-form` | Form | groups the inputs in one Section | `Sections[].Components` |
| `plan-id` | Dropdown | required plan selection | `Name: planId`, `Options: $.planOptions`, `DefaultValue: $.defaultPlanId`, `Required` |
| `area-code` | FormInput | optional 3-digit area code | `Name: areaCode`, `DefaultValue: $.defaultAreaCode`, `HelperText: "3 dígitos"` |
| `notes` | TextArea | optional free-text notes | `Name: notes` |
| `footer-col` | Container | top-level row holding the buttons | `Columns: "12"` |
| `submit` | SubmitButton | submit the form | `Action: Submit` |
| `cancel` | Button | cancel the form | `Action: Cancel`, label via `Content` |

## Data-binding contract

The flow's `ShowView` block (`nl-show-form`, task 7) drives this view.
The bindings are the contract between the flow and the view; they must
match the names below exactly.

### Inputs (`ViewData` → `$.<name>` in the view)

| Template ref | Type | Source (flow) | Meaning |
|---|---|---|---|
| `$.planOptions` | `Option[]` (`{Label, Value}`) | `$.External.planOptions` from the plans Lambda (`ResponseType: JSON`) | live plan list for the Dropdown |
| `$.defaultPlanId` | `string[]` | `$.Lex.SessionAttributes.planId` (wrapped as a 1-element array) | prefill the Dropdown selection |
| `$.defaultAreaCode` | `string` | `$.Lex.SessionAttributes.areaCode` | prefill the area-code input |

`defaultPlanId` is an **array** because the Dropdown's `DefaultValue` is
typed `string[]` (single-select still models its selection as an array —
see `component-findings.md`). The flow must supply `["<planId>"]`, not a
bare string.

### Outputs (`$.Views.ViewResultData.<Name>`)

| Output | Shape | Dereference in `nl-set-attrs` |
|---|---|---|
| `$.Views.ViewResultData.planId` | **1-element array** (`string[]`) | `$.Views.ViewResultData.planId[0]` |
| `$.Views.ViewResultData.areaCode` | scalar string | `$.Views.ViewResultData.areaCode` |
| `$.Views.ViewResultData.notes` | scalar string | `$.Views.ViewResultData.notes` |

The chosen action lands at `$.Views.Action` (`"Submit"` / `"Cancel"`).
`planId` comes back as a 1-element array (matching its `string[]` input
typing), so `nl-set-attrs` copies the **first element**
(`$.Views.ViewResultData.planId[0]`) into the `nlPlanId` contact
attribute. `areaCode` (FormInput) and `notes` (TextArea) are scalar
strings. This array-vs-scalar behavior is the strongest signal from the
component docs and must be re-confirmed at runtime (see Verification
status — pending items overlap with task 10).

## Validation decisions (from `component-findings.md`)

- **3-digit area-code validation is not expressible on the view.**
  `FormInput` has no `pattern` / `regex` / `maxLength` / `minLength`
  prop. The only constraint prop is `InputType`, which switches input
  mode but does not enforce a 3-digit length. We considered and rejected
  `InputType`:
  - `number` risks stripping leading zeros (e.g. `012`) and allows
    decimals/sign.
  - `tel` only hints a numeric keypad on mobile; enforces neither
    digits-only nor length.
  So the field keeps the default `text` input and the 3-digit rule
  (Req 3.3) is enforced by: (1) the `newLine` backend (the authoritative
  rule), (2) the chat agent's error handling on a backend validation
  error (Req 4.7), and (3) the in-form `HelperText: "3 dígitos"` guiding
  the customer. `areaCode` is optional, so an empty value is valid and
  passes through untouched.
- **Dropdown output is an array, not a scalar** (see the data-binding
  contract above). Drives the `[0]` dereference in `nl-set-attrs` and the
  array prefill on `defaultPlanId`.
- **Top-level Body items are Containers**, per the server rule the local
  validator and the SAVED deploy both check for.

No further changes were made to `view-content.json` during task 3.3 — the
local validator reports 0 errors as authored.

## Qualified-ARN convention ($LATEST)

The `ShowView` block references the view by its **qualified** ARN. The
CDK construct (`cdk_constructs/connect/views.py`, task 4) exposes:

- `view_arn` → `CfnView.attr_view_arn` (the unqualified ARN).
- `view_qualified_arn` → `f"{view_arn}:$LATEST"`.

The flow's `NEWLINE_VIEW_ARN_PLACEHOLDER` marker resolves at synth to
`view_qualified_arn`, i.e. the view is referenced as **`:$LATEST`**
(tracks the latest version) rather than a pinned numeric version. This
matches the existing screen-pop convention in this project (Req 6.6).
Revisit a pinned version only if a view change ever needs a staged
rollout.

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

### Server-schema deploy (`--status SAVED`) — PENDING (credentials)

A `--status SAVED` `create-view` catches server-schema gaps the local
validator misses (e.g. props the catalog does not yet model). It could
**not** be run during task 3.3: the environment's AWS credentials are
expired/invalid (`aws sts get-caller-identity` →
`InvalidClientTokenId`).

**Run this once valid credentials are available** (from
`projects/telco-cx/telco-cx-cdk/`, the project's standard AWS
profile/region; `view-content.json` already matches the `--content`
shape `{Template, Actions}`):

```bash
aws connect create-view \
  --region us-west-2 \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --name TelcoNewLineForm \
  --status SAVED \
  --content file://../views/telco-newline-form/view-content.json
```

Expected: the call succeeds and returns a `View` with `Status: SAVED`. A
schema error in the response indicates a server-side gap to fix in
`view-content.json` before the CDK `CfnView` deploy (task 4). This is a
throwaway probe — delete the probe view afterward so it does not collide
with the CDK-managed view (which owns the real `TelcoNewLineForm`):

```bash
aws connect delete-view \
  --region us-west-2 \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --view-id <ViewId-from-create-view-response>
```

### Runtime confirmation — PENDING (task 10)

The Dropdown result serialization (1-element array vs scalar) and the
live render with interactive content types are confirmed in the chat
end-to-end check (task 10), which needs a hosted/custom widget that
renders interactive messages (Assumption 1). The `string[]` typing is the
safe assumption to build `nl-set-attrs` on until then.
