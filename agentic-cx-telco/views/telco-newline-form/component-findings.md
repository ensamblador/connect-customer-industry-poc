# Component findings — TelcoNewLineForm (task 3.2)

Source: `get_view_component_doc` (Connect View Dictionary / Storybook),
re-confirmed during task 3.2. Feeds `view-design.md` (3.3) and the flow's
`nl-set-attrs` block (task 7).

## FormInput (`areaCode`) — no validation/pattern prop

Documented props for `FormInput` (UI Component, slug
`ui-component-forminput--with-all`):

| Prop | Required | Type | Default |
|---|---|---|---|
| `Label` | yes | string | — |
| `Name` | yes | string | — |
| `DefaultValue` | no | string | — |
| `InputType` | no | `number \| text \| password \| email \| tel \| url` | `text` |
| `Required` | no | `true \| false` | `false` |
| `HelperText` | no | string | — |

**There is no `pattern`, `regex`, `maxLength`, `minLength`, or any other
length/format constraint prop.** The only input constraint available is
`InputType`, which switches the input mode (e.g. numeric for `number` /
`tel`) but does **not** enforce a 3-digit length.

### Decision: rely on backend validation (view unchanged)

- Client-side "exactly 3 digits" validation (Req 3.3) is **not
  expressible** on `FormInput`. We do not add a pattern prop because none
  exists.
- `InputType` was considered and **not applied**:
  - `number` risks stripping leading zeros (an area code like `012`) and
    permits decimals/sign — wrong shape for a 3-digit code.
  - `tel` only hints a numeric keypad on mobile; it enforces neither
    digits-only on desktop nor length, so it adds no real guarantee.
  - Neither delivers the 3-digit rule, so the view keeps the default
    `text` input and leans on the two real guards below.
- The 3-digit rule is enforced by:
  1. **Backend** — the `newLine` backend (`lines/handler.py`) rejects a
     non-3-digit `areaCode` (the authoritative rule, Req 3.3).
  2. **Agent error handling** — on a backend validation error the chat
     agent apologizes / re-asks or escalates (Req 4.7).
  3. **`HelperText: "3 dígitos"`** already guides the customer in-form.
- `areaCode` is **optional**, so an empty value is valid and must pass
  through untouched.

No change was made to `view-content.json` for task 3.2.

## Dropdown (`planId`) — output is an array (string[]), not a scalar

Documented props for `Dropdown` (FormView Component, slug
`formview-component-dropdown--with-all`):

| Prop | Required | Type |
|---|---|---|
| `Label` | yes | string |
| `Name` | yes | string |
| `Options` | yes | `Option[]` |
| `DefaultValue` | no | `string[]` |
| `MultiSelect` | no | boolean |
| `Clearable` | no | boolean |
| `Required` | no | `true \| false` |
| `HelperText` | no | string |

`DefaultValue` is typed **`string[]`** and described as "Initial value of
selected option(s)" — the component models its selection as an **array of
values even when single-select** (`MultiSelect` is a separate, defaulted
flag). The current view binds `DefaultValue: "$.defaultPlanId"`, so the
flow must supply an **array** (e.g. `["plan-plus"]`), and the result
`$.Views.ViewResultData.planId` comes back as a **1-element array**, not a
scalar string.

### Implication for `nl-set-attrs` (task 7)

- The form prefill `defaultPlanId` passed in `ViewData` should be an array
  (`["<planId>"]`), not a bare string, to match the `string[]` shape.
- When copying the submitted plan into a contact attribute, dereference
  the **first element**: `$.Views.ViewResultData.planId[0]` (not
  `$.Views.ViewResultData.planId`). `areaCode` and `notes` (FormInput /
  TextArea) remain scalar strings.
- This array-vs-scalar behavior should be re-confirmed at runtime against
  the `--status SAVED` deploy in task 3.3 / the end-to-end check in task
  10, since the docs describe input props rather than the exact result
  serialization. The `string[]` typing is the strongest available signal
  and the safe assumption to build on.
