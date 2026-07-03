"""
tests/unit/test_flows_template.py — CX-BANCO-FLOWS (Phase 5) asserts.

Three complementary layers of guard for the banking contact flows / modules:

  1. CDK template assertions — synthesize a fresh ``ContactFlowsStack``
     (``config.HAS_REAL_INSTANCE`` is True, so the gated flows synthesize) and
     assert the Phase-5 contract against the resulting CloudFormation template:
       * exactly two ``AWS::Connect::ContactFlow`` — ``banco-agent-screenpop-es``
         and ``banco-selfservice-es-inbound`` (Requirement 8.1);
       * exactly two ``AWS::Connect::ContactFlowModule`` —
         ``banco-escalate-to-agent`` and ``set-customer-session-banco``
         (Requirement 8.1);
       * every provisioned flow/module name is banking-themed and matches no
         live telco flow name (Requirements 8.1, 8.7).

  2. Flow structure-preservation diff — read each banking flow JSON and its
     telco source straight from the filesystem (no synth) and prove the re-theme
     is content-only (Requirements 8.7, 8.11): identical ``Actions[].Identifier``
     set and identical transition/branch graph (the ``NextAction`` +
     ``Conditions[].NextAction`` + ``Errors[].NextAction`` edges). The one
     intended rename — the inbound flow's ``set-customer-session-telco`` action
     id becomes ``set-customer-session-banco`` — is normalized away in the
     comparison so it does not register as a structural divergence.

  3. Flow-language + view-content structural validation (Requirements 8.1, 8.11)
     — validate each flow the way ``mcp_connect_knowledge_validate_flow_json``
     would, but locally: parse the JSON, require ``Version`` / ``StartAction`` /
     ``Actions``, assert ``Identifier`` uniqueness, and prove every
     ``NextAction`` reference (and ``StartAction``) resolves to a real action.
     The inbound flow inherits friendly-name identifiers with spaces from telco
     (``VOICE Self Service`` etc.); these are accepted as-is because the
     resolution check only requires them to be internally consistent. The
     escalation handoff view is validated structurally too: ``Template`` /
     ``Actions`` present and every ``_id`` unique.

Validates: Requirements 8.1, 8.7, 8.11
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

import config
from agentic_cx_bank.contact_flows_stack import ContactFlowsStack

# --------------------------------------------------------------------------- #
# Fixtures / constants
# --------------------------------------------------------------------------- #

# Project roots: tests/unit/<this file> -> parents[2] == agentic-cx-bank/.
BANK_ROOT = Path(__file__).resolve().parents[2]
TELCO_ROOT = BANK_ROOT.parent / "agentic-cx-telco"

# The four banking flow/module names the stack provisions (Requirement 8.1).
EXPECTED_CONTACT_FLOW_NAMES = {
    "banco-agent-screenpop-es",
    "banco-selfservice-es-inbound",
}
EXPECTED_FLOW_MODULE_NAMES = {
    "banco-escalate-to-agent",
    "set-customer-session-banco",
}
EXPECTED_ALL_NAMES = EXPECTED_CONTACT_FLOW_NAMES | EXPECTED_FLOW_MODULE_NAMES

# The live telco flow/module names on the shared instance. No banking flow name
# may collide with any of these (Requirement 8.7).
TELCO_FLOW_NAMES = {
    "telco-agent-screenpop-es",
    "telco-selfservice-es-inbound",
    "escalate-to-agent",
    "set-customer-session-telco",
}

# The one intended action-id rename: the inbound flow's set-customer-session
# InvokeFlowModule action was renamed telco -> banco. Normalizing the banking id
# back to the telco id lets the structural diff treat everything else as a
# content-only retheme (Requirement 8.11).
RENAME_BANK_TO_TELCO = {"set-customer-session-banco": "set-customer-session-telco"}

# (bank flow JSON, telco source flow JSON) pairs for the structure diff.
FLOW_PAIRS = {
    "screenpop": (
        BANK_ROOT / "flows" / "banco-agent-screenpop-es" / "flow.json",
        TELCO_ROOT / "flows" / "telco-agent-screenpop-es" / "flow.json",
    ),
    "escalate-module": (
        BANK_ROOT / "flows" / "banco-escalate-to-agent" / "flow.json",
        TELCO_ROOT / "flows" / "escalate-to-agent" / "flow.json",
    ),
    "set-customer-session": (
        BANK_ROOT / "flows" / "set-customer-session-banco" / "flow.json",
        TELCO_ROOT / "flows" / "set-customer-session-telco" / "flow.json",
    ),
    "inbound": (
        BANK_ROOT / "flows" / "banco-selfservice-es-inbound" / "flow.json",
        TELCO_ROOT / "flows" / "telco-selfservice-es-inbound" / "flow.json",
    ),
}

# All four banking flow JSONs, for the flow-language structural validation.
BANK_FLOWS = {name: pair[0] for name, pair in FLOW_PAIRS.items()}

# Flows that carry re-themeable domain content (name/description/wording), so a
# content-only retheme MUST leave them non-identical to their telco source. The
# screen-pop flow is deliberately excluded: it is a generic, purely-structural
# flow (logging -> show-view placeholder -> disconnect) with no domain text, so
# being byte-identical to the telco source is correct, not a missed retheme.
RETHEMED_FLOW_PAIRS = {"escalate-module", "set-customer-session", "inbound"}

# The escalation handoff view provisioned by this stack (Requirement 8.11).
HANDOFF_VIEW = BANK_ROOT / config.ESCALATION_HANDOFF_VIEW_CONTENT


@pytest.fixture(scope="module")
def template() -> Template:
    """Synthesize a fresh ContactFlowsStack once and expose its template."""
    assert config.HAS_REAL_INSTANCE, (
        "this suite requires HAS_REAL_INSTANCE=True so the gated flows synthesize"
    )
    app = cdk.App()
    stack = ContactFlowsStack(app, "CX-BANCO-FLOWS")
    return Template.from_stack(stack)


# --------------------------------------------------------------------------- #
# Structure-preservation / validation helpers (filesystem, no synth)
# --------------------------------------------------------------------------- #

def _load_flow(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(identifier: str) -> str:
    """Canonicalize an action id by undoing the one intended banco->telco rename."""
    return RENAME_BANK_TO_TELCO.get(identifier, identifier)


def _identifier_set(flow: dict) -> set[str]:
    """The set of ``Actions[].Identifier`` values, rename-normalized."""
    return {_norm(a["Identifier"]) for a in flow.get("Actions", [])}


def _transition_edges(flow: dict) -> set[tuple[str, str, str]]:
    """The transition/branch graph as a set of ``(source, kind, target)`` edges.

    Captures the three documented edge kinds — the default ``NextAction``, each
    ``Conditions[].NextAction`` branch, and each ``Errors[].NextAction`` branch
    (keyed by its ``ErrorType``) — with every id rename-normalized so the
    banco/telco graphs line up node-for-node.
    """
    edges: set[tuple[str, str, str]] = set()
    for action in flow.get("Actions", []):
        src = _norm(action["Identifier"])
        transitions = action.get("Transitions", {}) or {}

        nxt = transitions.get("NextAction")
        if nxt:
            edges.add((src, "next", _norm(nxt)))

        for cond in transitions.get("Conditions", []) or []:
            target = cond.get("NextAction")
            if target:
                edges.add((src, "condition", _norm(target)))

        for err in transitions.get("Errors", []) or []:
            target = err.get("NextAction")
            if target:
                edges.add((src, f"error:{err.get('ErrorType', '')}", _norm(target)))
    return edges


def _validate_flow_language(flow: dict) -> None:
    """Local stand-in for Connect Flow-language validation.

    Asserts the structural invariants the runtime enforces: the top-level
    ``Version`` / ``StartAction`` / ``Actions`` shape, unique ``Identifier``s,
    and every ``NextAction`` reference (plus ``StartAction``) resolving to a
    defined action. Friendly-name identifiers with spaces are accepted as-is.
    """
    assert flow.get("Version"), "flow missing Version"
    start = flow.get("StartAction")
    assert start, "flow missing StartAction"

    actions = flow.get("Actions")
    assert isinstance(actions, list) and actions, "flow Actions must be a non-empty list"

    ids = [a["Identifier"] for a in actions]
    assert len(ids) == len(set(ids)), (
        f"duplicate action Identifiers: "
        f"{sorted({i for i in ids if ids.count(i) > 1})}"
    )
    id_set = set(ids)

    assert start in id_set, f"StartAction {start!r} does not resolve to an action"

    for action in actions:
        transitions = action.get("Transitions", {}) or {}
        targets: list[str] = []
        if transitions.get("NextAction"):
            targets.append(transitions["NextAction"])
        for cond in transitions.get("Conditions", []) or []:
            if cond.get("NextAction"):
                targets.append(cond["NextAction"])
        for err in transitions.get("Errors", []) or []:
            if err.get("NextAction"):
                targets.append(err["NextAction"])
        for target in targets:
            assert target in id_set, (
                f"action {action['Identifier']!r} references undefined "
                f"NextAction {target!r}"
            )


def _collect_view_ids(node) -> list[str]:
    """Every ``_id`` anywhere in a parsed view Template subtree, in order."""
    ids: list[str] = []
    if isinstance(node, dict):
        if "_id" in node:
            ids.append(node["_id"])
        for value in node.values():
            ids.extend(_collect_view_ids(value))
    elif isinstance(node, list):
        for item in node:
            ids.extend(_collect_view_ids(item))
    return ids


def _flow_names(template: Template, resource_type: str) -> set[str]:
    resources = template.find_resources(resource_type)
    return {r["Properties"]["Name"] for r in resources.values()}


# --------------------------------------------------------------------------- #
# Requirement 8.1 — the four flows/modules exist with the expected names
# --------------------------------------------------------------------------- #

def test_exactly_two_contact_flows(template: Template):
    template.resource_count_is("AWS::Connect::ContactFlow", 2)


def test_exactly_two_flow_modules(template: Template):
    template.resource_count_is("AWS::Connect::ContactFlowModule", 2)


def test_contact_flow_names(template: Template):
    names = _flow_names(template, "AWS::Connect::ContactFlow")
    assert names == EXPECTED_CONTACT_FLOW_NAMES, (
        f"contact flow names {sorted(names)} != {sorted(EXPECTED_CONTACT_FLOW_NAMES)}"
    )


def test_flow_module_names(template: Template):
    names = _flow_names(template, "AWS::Connect::ContactFlowModule")
    assert names == EXPECTED_FLOW_MODULE_NAMES, (
        f"flow module names {sorted(names)} != {sorted(EXPECTED_FLOW_MODULE_NAMES)}"
    )


# --------------------------------------------------------------------------- #
# Requirement 8.7 — banking names collide with no live telco flow name
# --------------------------------------------------------------------------- #

def test_no_flow_name_matches_telco(template: Template):
    provisioned = (
        _flow_names(template, "AWS::Connect::ContactFlow")
        | _flow_names(template, "AWS::Connect::ContactFlowModule")
    )
    assert provisioned == EXPECTED_ALL_NAMES, (
        f"provisioned flow names {sorted(provisioned)} != {sorted(EXPECTED_ALL_NAMES)}"
    )
    collisions = provisioned & TELCO_FLOW_NAMES
    assert not collisions, f"banking flow names collide with telco: {sorted(collisions)}"
    for name in provisioned:
        assert "telco" not in name.lower(), (
            f"provisioned flow name {name!r} carries a 'telco' token"
        )


# --------------------------------------------------------------------------- #
# Requirements 8.7, 8.11 — flow structure-preservation diff vs telco source
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pair", sorted(FLOW_PAIRS), ids=sorted(FLOW_PAIRS))
def test_flow_source_files_exist(pair: str):
    bank_path, telco_path = FLOW_PAIRS[pair]
    assert bank_path.is_file(), f"missing banking flow {bank_path}"
    assert telco_path.is_file(), f"missing telco source flow {telco_path}"


@pytest.mark.parametrize("pair", sorted(FLOW_PAIRS), ids=sorted(FLOW_PAIRS))
def test_flow_identifier_set_is_identical(pair: str):
    bank_path, telco_path = FLOW_PAIRS[pair]
    bank = _identifier_set(_load_flow(bank_path))
    telco = _identifier_set(_load_flow(telco_path))
    assert bank == telco, (
        f"{pair}: Identifier set diverged (after rename-normalization) — "
        f"only-in-bank={sorted(bank - telco)}, only-in-telco={sorted(telco - bank)}"
    )


@pytest.mark.parametrize("pair", sorted(FLOW_PAIRS), ids=sorted(FLOW_PAIRS))
def test_flow_transition_graph_is_identical(pair: str):
    bank_path, telco_path = FLOW_PAIRS[pair]
    bank = _transition_edges(_load_flow(bank_path))
    telco = _transition_edges(_load_flow(telco_path))
    assert bank == telco, (
        f"{pair}: transition/branch graph diverged (after rename-normalization) — "
        f"only-in-bank={sorted(bank - telco)}, only-in-telco={sorted(telco - bank)}"
    )


@pytest.mark.parametrize("pair", sorted(FLOW_PAIRS), ids=sorted(FLOW_PAIRS))
def test_no_telco_token_survives_in_flow(pair: str):
    """No banking flow — generic or re-themed — may leak a 'telco' token."""
    bank_path, _ = FLOW_PAIRS[pair]
    bank = _load_flow(bank_path)
    assert "telco" not in json.dumps(bank).lower(), (
        f"{pair}: a 'telco' substring survives in the banking flow content"
    )


@pytest.mark.parametrize(
    "pair", sorted(RETHEMED_FLOW_PAIRS), ids=sorted(RETHEMED_FLOW_PAIRS)
)
def test_content_bearing_flow_actually_rethemed(pair: str):
    """The structure is preserved, but a content-bearing flow must differ from
    its telco source — guards against a verbatim copy that leaves telco wording
    (or the telco module name) in a banking flow."""
    bank_path, telco_path = FLOW_PAIRS[pair]
    bank = _load_flow(bank_path)
    telco = _load_flow(telco_path)
    assert bank != telco, (
        f"{pair}: banking flow is byte-identical to the telco source — not re-themed"
    )


# --------------------------------------------------------------------------- #
# Requirements 8.1, 8.11 — Connect Flow-language structural validation
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", sorted(BANK_FLOWS), ids=sorted(BANK_FLOWS))
def test_flow_language_is_structurally_valid(name: str):
    _validate_flow_language(_load_flow(BANK_FLOWS[name]))


def test_inbound_flow_accepts_friendly_name_identifiers():
    """The inbound flow inherits friendly-name identifiers with spaces from the
    telco source (e.g. ``VOICE Self Service``); the structural validation must
    accept them as-is."""
    flow = _load_flow(BANK_FLOWS["inbound"])
    ids = {a["Identifier"] for a in flow["Actions"]}
    friendly = {i for i in ids if " " in i}
    assert "VOICE Self Service" in friendly and "CHAT Self Service" in friendly, (
        f"expected inherited friendly-name identifiers, found {sorted(friendly)}"
    )
    # They must still resolve like any other identifier.
    _validate_flow_language(flow)


# --------------------------------------------------------------------------- #
# Requirement 8.11 — handoff view content structural validation
# --------------------------------------------------------------------------- #

def test_handoff_view_file_exists():
    assert HANDOFF_VIEW.is_file(), f"missing handoff view {HANDOFF_VIEW}"


def test_handoff_view_is_structurally_valid():
    raw = json.loads(HANDOFF_VIEW.read_text(encoding="utf-8"))
    assert "Template" in raw, "handoff view missing Template"
    assert "Actions" in raw, "handoff view missing Actions"
    assert isinstance(raw["Actions"], list) and raw["Actions"], (
        "handoff view Actions must be a non-empty list"
    )

    # The view's Template is authored as an escaped JSON string; parse it.
    template = raw["Template"]
    if isinstance(template, str):
        template = json.loads(template)
    assert isinstance(template, dict), "handoff view Template must be an object"
    assert "Body" in template, "handoff view Template missing Body"

    ids = _collect_view_ids(template["Body"])
    assert len(ids) == len(set(ids)), (
        f"handoff view has duplicate _id(s): "
        f"{sorted({i for i in ids if ids.count(i) > 1})}"
    )
    assert ids, "handoff view Body has no components"
