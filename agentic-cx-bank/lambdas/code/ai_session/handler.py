"""
ai-session-banco Lambda handler.

Invoked synchronously by the ``set-customer-session-banco`` contact flow module
(InvokeLambdaFunction, STRING_MAP). Given the captured contact endpoint
(``email`` or ``phoneNumber``) it:

  1. Looks the customer up in the banco-accounts DynamoDB table — by phone via
     the ``phoneNumber-index`` GSI, else by email via the ``email-index`` GSI.
  2. If found, writes every field of the customer record into the contact's
     Q in Connect (Wisdom) session via ``qconnect:UpdateSessionData`` (so the
     fields surface to the downstream AI agents as ``$.Custom.<field>``). The
     session id is discovered with ``connect:DescribeContact`` ->
     ``Contact.WisdomInfo.SessionArn`` (the session is associated to the contact
     by the main flow's CreateWisdomSession step before this module runs).
  3. Returns a FLAT string map (STRING_MAP contract): ``is_customer`` ("TRUE" /
     "FALSE"), and on a hit also ``session_updated`` plus the
     ``customerId`` / ``name`` / ``phoneNumber`` / ``email`` the module promotes
     to contact attributes.

Second mode — generic session write: when invoked WITHOUT a lookup endpoint
(no ``phoneNumber`` / ``email`` parameter), it writes every other parameter
passed by the flow into the Wisdom session as ``$.Custom.<key>`` and echoes
them back. This is how the card-request product picker persists
``selectedProduct``, but any future attribute can be written the same way with
no code change — the flow just passes it as a parameter.

Read-only on DynamoDB; no PII is logged. Never raises on a session-write
failure (the contact must not be blocked by a personalization error).

Environment:
  ACCOUNTS_TABLE        - banco-accounts table name
  ACCOUNTS_PHONE_INDEX  - phone-number GSI name (default "phoneNumber-index")
  ACCOUNTS_EMAIL_INDEX  - email GSI name (default "email-index")
  AI_ASSISTANT_ID       - Q in Connect assistant id (for UpdateSessionData)
  CONNECT_INSTANCE_ID   - Amazon Connect instance id (for DescribeContact)
"""

import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

_TABLE_NAME = os.environ["ACCOUNTS_TABLE"]
_PHONE_INDEX = os.environ.get("ACCOUNTS_PHONE_INDEX", "phoneNumber-index")
_EMAIL_INDEX = os.environ.get("ACCOUNTS_EMAIL_INDEX", "email-index")
_ASSISTANT_ID = os.environ["AI_ASSISTANT_ID"]
_INSTANCE_ID = os.environ.get("CONNECT_INSTANCE_ID", "")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TABLE_NAME)
_qconnect = boto3.client("qconnect")
_connect = boto3.client("connect")

# Customer-record fields promoted to contact attributes by the module on a hit.
# Returned (flat, stringified) in the STRING_MAP response as $.External.<field>.
_ATTRIBUTE_FIELDS = ("customerId", "name", "phoneNumber", "email")


def _stringify(value) -> str:
    """Render a DynamoDB attribute value as a flat string for session data.

    Numbers (DynamoDB Decimal) render without a trailing ``.0`` when integral;
    everything else uses ``str``. None becomes an empty string.
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(int(value)) if value % 1 == 0 else str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_session_data(item: dict) -> list:
    """Build the ``UpdateSessionData`` ``data`` list from a customer record.

    Emits one ``{"key": k, "value": {"stringValue": v}}`` entry for every field
    whose stringified value has at least one non-whitespace character. Pure and
    total: never raises, never mutates ``item``.
    """
    data = []
    for key, value in (item or {}).items():
        rendered = _stringify(value)
        if rendered.strip():
            data.append({"key": key, "value": {"stringValue": rendered}})
    return data


def _lookup_customer(phone: str, email: str):
    """Return the customer record matched by phone (preferred) or email, or None."""
    if phone and phone.strip():
        result = _table.query(
            IndexName=_PHONE_INDEX,
            KeyConditionExpression=Key("phoneNumber").eq(phone),
        )
        items = result.get("Items", [])
        if items:
            return items[0]
    if email and email.strip():
        result = _table.query(
            IndexName=_EMAIL_INDEX,
            KeyConditionExpression=Key("email").eq(email),
        )
        items = result.get("Items", [])
        if items:
            return items[0]
    return None


def _resolve_session_arn(contact_id: str) -> str:
    """Discover the contact's Wisdom session ARN via connect:DescribeContact.

    The main flow's CreateWisdomSession step associates the session to the
    contact, so ``Contact.WisdomInfo.SessionArn`` is populated by the time this
    module runs. Returns "" (and logs) when it is not yet available or on error.
    """
    if not contact_id:
        return ""
    try:
        contact = _connect.describe_contact(
            ContactId=contact_id, InstanceId=_INSTANCE_ID
        ).get("Contact", {})
        return (contact.get("WisdomInfo") or {}).get("SessionArn") or ""
    except Exception as exc:  # never block the contact on a discovery failure
        print(f"[ai-session] describe_contact failed (ignored): {exc}")
        return ""


def _write_session_values(contact_id: str, values: dict) -> str:
    """Write the given key/value pairs into the contact's Wisdom session.

    Resolves the session ARN via DescribeContact and calls UpdateSessionData
    with one entry per non-empty value (surfacing as ``$.Custom.<key>`` to the
    AI agents). Returns "true" on success, "false" otherwise. Never raises —
    a personalization write must not block the contact.
    """
    session_arn = _resolve_session_arn(contact_id)
    data = [
        {"key": k, "value": {"stringValue": _stringify(v)}}
        for k, v in values.items()
        if _stringify(v).strip()
    ]
    if not session_arn:
        print("[ai-session] no WisdomInfo.SessionArn on the contact; session write skipped")
        return "false"
    if not data:
        return "false"
    try:
        _qconnect.update_session_data(
            assistantId=_ASSISTANT_ID, sessionId=session_arn, data=data
        )
        return "true"
    except Exception as exc:  # never block the contact on a write failure
        print(f"[ai-session] session data write failed (ignored): {exc}")
        return "false"


def handler(event, _context):
    """Connect InvokeLambdaFunction entry point (STRING_MAP response)."""
    details = (event.get("Details", {}) or {})
    params = details.get("Parameters", {}) or {}
    contact_id = (details.get("ContactData", {}) or {}).get("ContactId")

    phone = (params.get("phoneNumber") or "").strip()
    email = (params.get("email") or "").strip()

    # Generic session-write mode: when invoked without a lookup endpoint
    # (no phoneNumber / email) the flow is asking us to persist arbitrary
    # key/value pairs into the contact's Wisdom session as $.Custom.<key>
    # (e.g. selectedProduct from the card-request product picker). Any future
    # attribute can be written this way with no Lambda code change — the flow
    # just passes it as a parameter.
    if not phone and not email:
        writable = {k: v for k, v in params.items() if _stringify(v).strip()}
        if writable:
            session_updated = _write_session_values(contact_id, writable)
            response = {"session_updated": session_updated}
            for key, value in writable.items():
                response[key] = _stringify(value)
            return response
        return {"session_updated": "false"}


    item = _lookup_customer(phone, email)
    if not item:
        return {"is_customer": "FALSE"}

    # Discover the Wisdom session via DescribeContact and write the full
    # customer record into it ($.Custom.*).
    session_updated = "false"
    session_arn = _resolve_session_arn(contact_id)
    data = build_session_data(item)
    if not session_arn:
        print("[ai-session] no WisdomInfo.SessionArn on the contact; session write skipped")
    elif data:
        try:
            _qconnect.update_session_data(
                assistantId=_ASSISTANT_ID, sessionId=session_arn, data=data
            )
            session_updated = "true"
        except Exception as exc:  # never block the contact on a write failure
            print(f"[ai-session] session data write failed (ignored): {exc}")

    # Flat STRING_MAP response: is_customer + the fields the module promotes to
    # contact attributes, all stringified.
    response = {"is_customer": "TRUE", "session_updated": session_updated}
    for field in _ATTRIBUTE_FIELDS:
        response[field] = _stringify(item.get(field))
    return response
