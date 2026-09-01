"""
tests/unit/test_support_template.py — CX-AIRLINE-CONNECT-SUPPORT (Phase 3) asserts.

Two complementary layers of guard for the airline Connect support resources:

  1. CDK template assertions — synthesize a fresh ``ConnectSupportStack``
     (``config.HAS_REAL_INSTANCE`` is True, so the gated Support resources
     synthesize) and assert the Phase-3 contract against the resulting
     CloudFormation template:
       * exactly two ``AWS::Connect::SecurityProfile`` resources, each granting
         exactly the least-privilege permission set ``Wisdom.View`` +
         ``CustomViews.Access`` (Requirements 6.1, 6.5);
       * each security profile carries the MCP application grant — a single
         ``Type: MCP`` application whose ``ApplicationPermissions`` are exactly
         the nine ``<target>___<op>`` airline tool ids, namespaced on the
         gateway id resolved from SSM (Requirements 6.1, 6.7);
       * exactly one ``AWS::Lex::Bot`` with the three locales ``en_US`` /
         ``es_US`` / ``pt_BR`` (Requirement 6.5);
       * the four published SSM parameters exist under ``/agentic-cx-airline``:
         ``SP_SELFSERVICE_ID``, ``SP_ASSIST_ID``, ``VIEW_NEWLINE_ARN``, and
         ``LEX_BOT_ALIAS_ARN`` (Requirement 6.6).

  2. View structure-preservation diff — read each airline view and its telco
     source straight from the filesystem (no synth) and prove the re-theme is
     content-only: identical ``_id`` set and identical recursive component tree
     (``{_id, Type}`` at every node), with only text ``Content`` / ``Props``
     differing (Requirements 6.9, 6.10):
       * ``airline-lost-baggage-guide``  vs telco ``telco-esim-activation-guide``.

     The guided reservation form is excluded on purpose — see VIEW_PAIRS.

Validates: Requirements 6.1, 6.5, 6.6, 6.9, 6.10
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

import config
from shared import ssm_names
from agentic_cx_airline.connect_support_stack import ConnectSupportStack

# --------------------------------------------------------------------------- #
# Fixtures / constants
# --------------------------------------------------------------------------- #

# Project roots: tests/unit/<this file> -> parents[2] == agentic-cx-airline/.
AIRLINE_ROOT = Path(__file__).resolve().parents[2]
TELCO_ROOT = AIRLINE_ROOT.parent / "agentic-cx-telco"

# The exact least-privilege permission set both AI-agent profiles must carry.
EXPECTED_PERMISSIONS = {"Wisdom.View", "CustomViews.Access"}

# The nine airline MCP tool ids the profile grant must reference: the gateway
# target joined to each configured operationId ("<target>___<op>").
EXPECTED_MCP_TOOL_IDS = [
    f"{config.AI_AGENT_MCP_TARGET}___{op}" for op in config.AI_AGENT_MCP_OPERATIONS
]

EXPECTED_LOCALES = {"en_US", "es_US", "pt_BR"}

# The four SSM parameters Phase 3 publishes (Requirement 6.6).
EXPECTED_SSM_NAMES = {
    ssm_names.SP_SELFSERVICE_ID,
    ssm_names.SP_ASSIST_ID,
    ssm_names.VIEW_NEWLINE_ARN,
    ssm_names.LEX_BOT_ALIAS_ARN,
}

# (airline view, telco source view) pairs for the structure-preservation diff.
VIEW_PAIRS = {
    # NOTE: the guided reservation form has NO telco counterpart pair here. The
    # deployed AirlineReservationForm offers five flights where telco's
    # telco-newline-form offers three plans, so it is deliberately NOT a
    # structure-preserving re-theme and cannot be diffed against it. (A fossil
    # airline-card-request-form used to be kept solely to satisfy this pair; it
    # was never deployed — config.NEWLINE_VIEW_CONTENT points at
    # airline-reservation-form — so it was removed rather than maintained.)
    "lost-baggage-guide": (
        AIRLINE_ROOT / "views" / "airline-lost-baggage-guide" / "view-content.json",
        TELCO_ROOT / "views" / "telco-esim-activation-guide" / "view-content.json",
    ),
}


@pytest.fixture(scope="module")
def template() -> Template:
    """Synthesize a fresh ConnectSupportStack once and expose its template."""
    assert config.HAS_REAL_INSTANCE, (
        "this suite requires HAS_REAL_INSTANCE=True so the gated Support "
        "resources synthesize"
    )
    app = cdk.App()
    stack = ConnectSupportStack(app, "CX-AIRLINE-CONNECT-SUPPORT")
    return Template.from_stack(stack)


# --------------------------------------------------------------------------- #
# View structure-preservation helpers
# --------------------------------------------------------------------------- #

def _child_components(node: dict) -> list[dict]:
    """The component children of a node: the dict entries of its Content list.

    A view component's ``Content`` is a list mixing plain text (strings) and
    nested component dicts. Only the dicts are structural children; the strings
    are the re-themeable text content we deliberately ignore.
    """
    content = node.get("Content", [])
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def _component_tree(node: dict):
    """Recursive ``(Type, _id, (children...))`` structure of a component.

    Captures only the structural skeleton — every node's ``Type`` and ``_id``
    and its ordered children — and nothing content-bearing (``Content`` text,
    ``Props``, titles), so an equal tree proves the re-theme changed content
    only.
    """
    return (
        node.get("Type"),
        node.get("_id"),
        tuple(_component_tree(child) for child in _child_components(node)),
    )


def _body_trees(view: dict) -> tuple:
    """The ordered tuple of component trees for a view's Template.Body."""
    body = view["Template"]["Body"]
    return tuple(_component_tree(node) for node in body)


def _collect_ids(node: dict) -> set[str]:
    """Every ``_id`` in the subtree rooted at ``node``."""
    ids: set[str] = set()
    if "_id" in node:
        ids.add(node["_id"])
    for child in _child_components(node):
        ids |= _collect_ids(child)
    return ids


def _view_ids(view: dict) -> set[str]:
    ids: set[str] = set()
    for node in view["Template"]["Body"]:
        ids |= _collect_ids(node)
    return ids


# --------------------------------------------------------------------------- #
# Requirements 6.1, 6.5 — exactly two profiles with the exact permission set
# --------------------------------------------------------------------------- #

def test_exactly_two_security_profiles(template: Template):
    profiles = template.find_resources("AWS::Connect::SecurityProfile")
    assert len(profiles) == 2, (
        f"expected exactly 2 security profiles, found {len(profiles)}"
    )


def test_each_security_profile_has_exact_permission_set(template: Template):
    profiles = template.find_resources("AWS::Connect::SecurityProfile")
    for logical_id, profile in profiles.items():
        permissions = profile["Properties"].get("Permissions", [])
        assert set(permissions) == EXPECTED_PERMISSIONS, (
            f"{logical_id} permissions {sorted(permissions)} != "
            f"{sorted(EXPECTED_PERMISSIONS)}"
        )
        assert len(permissions) == len(EXPECTED_PERMISSIONS), (
            f"{logical_id} has duplicate/extra permissions: {permissions}"
        )


# --------------------------------------------------------------------------- #
# Requirements 6.1, 6.7 — the MCP grant: namespace + nine <target>___<op> ids
# --------------------------------------------------------------------------- #

def test_each_security_profile_has_mcp_grant(template: Template):
    profiles = template.find_resources("AWS::Connect::SecurityProfile")
    for logical_id, profile in profiles.items():
        applications = profile["Properties"].get("Applications") or []
        mcp_apps = [a for a in applications if a.get("Type") == "MCP"]
        assert len(mcp_apps) == 1, (
            f"{logical_id} must have exactly one MCP application grant, "
            f"found {len(mcp_apps)}"
        )
        app = mcp_apps[0]

        # Namespace is the gateway id resolved from SSM at deploy time, so it
        # renders as an intrinsic Ref to the SSM template parameter — assert it
        # is present and reference-shaped (not a literal telco value).
        namespace = app.get("Namespace")
        assert isinstance(namespace, dict) and "Ref" in namespace, (
            f"{logical_id} MCP namespace must reference the SSM gateway id, "
            f"found {namespace!r}"
        )

        # The nine airline tool ids, exact and in order.
        assert app.get("ApplicationPermissions") == EXPECTED_MCP_TOOL_IDS, (
            f"{logical_id} MCP tool ids != the nine airline <target>___<op> ids"
        )


# --------------------------------------------------------------------------- #
# Requirement 6.5 — one Lex bot with the three locales
# --------------------------------------------------------------------------- #

def test_lex_bot_has_three_locales(template: Template):
    bots = template.find_resources("AWS::Lex::Bot")
    assert len(bots) == 1, f"expected exactly one Lex bot, found {len(bots)}"
    (bot,) = bots.values()
    locales = {loc["LocaleId"] for loc in bot["Properties"]["BotLocales"]}
    assert locales == EXPECTED_LOCALES, (
        f"Lex bot locales {sorted(locales)} != {sorted(EXPECTED_LOCALES)}"
    )


# --------------------------------------------------------------------------- #
# Requirement 6.6 — the four published SSM values under /agentic-cx-airline
# --------------------------------------------------------------------------- #

def test_four_published_ssm_params_exist(template: Template):
    params = template.find_resources("AWS::SSM::Parameter")
    published = {p["Properties"]["Name"] for p in params.values()}
    assert EXPECTED_SSM_NAMES <= published, (
        f"missing published SSM params: {sorted(EXPECTED_SSM_NAMES - published)}"
    )
    # Every published name is under the airline namespace.
    for name in EXPECTED_SSM_NAMES:
        assert name.startswith("/agentic-cx-airline"), (
            f"published SSM name {name!r} is outside the /agentic-cx-airline namespace"
        )


# --------------------------------------------------------------------------- #
# Requirements 6.9, 6.10 — view structure-preservation diff (content-only theme)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pair", sorted(VIEW_PAIRS), ids=sorted(VIEW_PAIRS))
def test_view_source_files_exist(pair: str):
    airline_path, telco_path = VIEW_PAIRS[pair]
    assert airline_path.is_file(), f"missing airline view {airline_path}"
    assert telco_path.is_file(), f"missing telco source view {telco_path}"


@pytest.mark.parametrize("pair", sorted(VIEW_PAIRS), ids=sorted(VIEW_PAIRS))
def test_view_id_set_is_identical(pair: str):
    airline_path, telco_path = VIEW_PAIRS[pair]
    airline = json.loads(airline_path.read_text(encoding="utf-8"))
    telco = json.loads(telco_path.read_text(encoding="utf-8"))
    assert _view_ids(airline) == _view_ids(telco), (
        f"{pair}: _id set diverged — "
        f"only-in-airline={sorted(_view_ids(airline) - _view_ids(telco))}, "
        f"only-in-telco={sorted(_view_ids(telco) - _view_ids(airline))}"
    )


@pytest.mark.parametrize("pair", sorted(VIEW_PAIRS), ids=sorted(VIEW_PAIRS))
def test_view_component_tree_is_identical(pair: str):
    airline_path, telco_path = VIEW_PAIRS[pair]
    airline = json.loads(airline_path.read_text(encoding="utf-8"))
    telco = json.loads(telco_path.read_text(encoding="utf-8"))
    assert _body_trees(airline) == _body_trees(telco), (
        f"{pair}: component tree (Type/_id skeleton) diverged from the telco source"
    )


@pytest.mark.parametrize("pair", sorted(VIEW_PAIRS), ids=sorted(VIEW_PAIRS))
def test_view_content_actually_differs(pair: str):
    """The structure is preserved, but the re-theme must have changed content —
    guards against an accidental verbatim copy that would leave telco text in a
    airline view."""
    airline_path, telco_path = VIEW_PAIRS[pair]
    airline = json.loads(airline_path.read_text(encoding="utf-8"))
    telco = json.loads(telco_path.read_text(encoding="utf-8"))
    assert airline != telco, (
        f"{pair}: airline view is byte-identical to the telco source — "
        "content was not re-themed"
    )
    # And no telco token should survive in the airline view's content.
    assert "telco" not in json.dumps(airline).lower(), (
        f"{pair}: a 'telco' substring survives in the airline view content"
    )
