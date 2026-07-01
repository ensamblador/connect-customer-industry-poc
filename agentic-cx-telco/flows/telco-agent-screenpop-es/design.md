# telco-agent-screenpop-es — DefaultAgentUI screen-pop flow

The flow that mounts the `TelcoEscalationHandoff` view on the agent's
screen when they accept an escalated contact. It is **not** in the
customer's call path — it runs as the `DefaultAgentUI` event-hook
flow, which Connect executes in the agent's workspace on accept.

## Architecture (why a separate flow)

The reference instance taught the pattern: the main customer flow
does **not** contain an inline `ShowView`. Instead:

1. The customer flow sets escalation context as **contact attributes**
   and registers this flow as the `DefaultAgentUI` event hook
   (`UpdateContactEventHooks`), then transfers to queue.
2. When an agent accepts, Connect runs **this** flow in the agent
   workspace. Its `ShowView` block reads the contact attributes and
   pops the view.

`ShowView` is documented as **chat-channel only** and routes
step-by-step guides to the agent workspace as a separate chat
contact — which is exactly how a `DefaultAgentUI` hook flow runs even
when the underlying customer contact is voice. That is why the view
works for a voice self-service call: the screen-pop runs as an agent
workspace surface, not on the voice leg.

## Spec

| Field | Value |
|---|---|
| Name | `telco-agent-screenpop-es` |
| Artifact kind | Contact flow (`CONTACT_FLOW`) |
| Deployed flow ID | `42e1ab22-bb19-4467-9645-914854e1049b` |
| Instance | `30b0e238-b3bd-4f61-9f04-c0b24e4a2f74` (us-west-2) |
| View shown | `TelcoEscalationHandoff` (`ef8070cb-0306-435a-af6c-201e23532306`) |

## Structure

```
StartAction: set-logging
  set-logging  (UpdateFlowLoggingBehavior: Enabled)
    → show-view  (ShowView)
        ViewResource.Id = <view ARN>:$LATEST
        ViewData = { 8 escalation attributes mapped from $.Attributes.* }
        Condition ActionSelected → disconnect
        Errors (NoMatchingCondition / TimeLimitExceeded / NoMatchingError) → disconnect
    → disconnect (DisconnectParticipant)
```

### ViewData → view binding

The view references flat keys (`$.escalationReason`, `$.sentiment`,
etc.). The `ShowView` block's `ViewData` map supplies them from the
contact attributes the main flow's `copy-context` block set:

```json
"ViewData": {
  "escalationReason":    "$.Attributes.escalationReason",
  "escalationSummary":   "$.Attributes.escalationSummary",
  "customerIntent":      "$.Attributes.customerIntent",
  "sentiment":           "$.Attributes.sentiment",
  "escalationPriority":  "$.Attributes.escalationPriority",
  "resolutionAttempted": "$.Attributes.resolutionAttempted",
  "recommendedAction":   "$.Attributes.recommendedAction",
  "topicsDiscussed":     "$.Attributes.topicsDiscussed"
}
```

## Learnings (deploy)

1. **`UpdateFlowLoggingBehavior` must NOT carry an `Errors` array.**
   The create API rejects it with `Invalid Action error. Error:
   NoMatchingError, Path: Actions[0]`. The reference flow declares
   only `Transitions.NextAction`. The MCP `validate_flow_json` does
   **not** catch this — it passed locally then 400'd server-side.
2. `ShowView.ViewResource.Id` takes the **view ARN with a version
   suffix** (`:$LATEST` or `:N`), not a bare view ID.
3. `InvocationTimeLimitSeconds` is a **string** in the flow JSON
   (`"1200"`), matching the reference.

## Deploy

```bash
# Create
AWS_PROFILE=connect-chat aws connect create-contact-flow \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --name telco-agent-screenpop-es --type CONTACT_FLOW \
  --content file://projects/telco-cx/flows/telco-agent-screenpop-es/flow.json \
  --region us-west-2

# Update
AWS_PROFILE=connect-chat aws connect update-contact-flow-content \
  --instance-id 30b0e238-b3bd-4f61-9f04-c0b24e4a2f74 \
  --contact-flow-id 42e1ab22-bb19-4467-9645-914854e1049b \
  --content file://projects/telco-cx/flows/telco-agent-screenpop-es/flow.json \
  --region us-west-2
```
