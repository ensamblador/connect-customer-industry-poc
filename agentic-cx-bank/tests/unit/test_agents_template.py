"""
tests/unit/test_agents_template.py — CX-BANCO-AGENTS (Phase 4) asserts.

Two complementary layers of guard for the banking AI agents:

  1. CDK template assertions — synthesize a fresh ``AiAgentsStack``
     (``config.HAS_REAL_INSTANCE`` is True, so the gated agents synthesize) and
     assert the Phase-4 contract against the resulting CloudFormation template:
       * exactly three orchestration prompts (``AWS::Wisdom::AIPrompt``) and
         three agents (``AWS::Wisdom::AIAgent``), each carrying the expected
         ``banco-*`` identifier (Requirements 7.1, 7.2, 7.3);
       * the expected per-surface tool surfaces, read straight off each agent's
         ``Configuration.OrchestrationAIAgentConfiguration.ToolConfigurations``
         list (Requirement 7.1):
           - voice  = Retrieve + 9 MCP + Escalate + Complete            (12 tools)
           - chat   = voice surface + ShowCardRequestGuide              (13 tools)
           - assist = Retrieve + 9 MCP                                  (10 tools)
       * a complementary check on ``connect.ai_agents.build_tools`` for the same
         three surfaces confirms the 12 / 13 / 10 counts and exact tool-name
         sets independently of synth.

  2. Prompt structure-preservation check — read each banking prompt YAML and its
     telco source straight from the filesystem (no synth) and prove the re-theme
     is content-only: identical top-level YAML keys, identical ``messages`` shape,
     and an identical ordered sequence of section markers (the ``<tag>`` /
     ``</tag>`` XML-like markers embedded in the ``system`` body), with only the
     domain text differing (Requirements 7.3, 7.11).

Validates: Requirements 7.1, 7.2, 7.3, 7.11
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
import aws_cdk as cdk
from aws_cdk.assertions import Template

import config
from cdk_constructs.connect import AgentSurface, build_tools
from connect.agent_tools import TOOLSET
from agentic_cx_bank.ai_agents_stack import AiAgentsStack

# --------------------------------------------------------------------------- #
# Fixtures / constants
# --------------------------------------------------------------------------- #

# Project roots: tests/unit/<this file> -> parents[2] == agentic-cx-bank/.
BANK_ROOT = Path(__file__).resolve().parents[2]
TELCO_ROOT = BANK_ROOT.parent / "agentic-cx-telco"

# The three banking prompt identifiers (Requirement 7.3) and agent identifiers.
EXPECTED_PROMPT_NAMES = {
    "banco-selfservice-voice-orchestration",
    "banco-selfservice-chat-orchestration",
    "banco-agent-assist-orchestration",
}
EXPECTED_AGENT_NAMES = {
    "banco-selfservice-voice-es",
    "banco-selfservice-chat-es",
    "banco-agent-assist-es",
}

# The nine banking MCP tool names bound to every surface (Requirement 7.4/7.6).
MCP_TOOL_NAMES = {
    "getAccountByPhone",
    "getAccountByEmail",
    "getAccount",
    "getAccountBalance",
    "listProducts",
    "getProduct",
    "requestCard",
    "listCustomerCards",
    "getCard",
}

# Expected exact tool-name set per agent identifier.
VOICE_TOOLS = {"Retrieve", *MCP_TOOL_NAMES, "Escalate", "Complete"}   # 12
CHAT_TOOLS = VOICE_TOOLS | {"ShowCardRequestGuide"}                   # 13
ASSIST_TOOLS = {"Retrieve", *MCP_TOOL_NAMES}                          # 10

EXPECTED_TOOLS_BY_AGENT = {
    "banco-selfservice-voice-es": VOICE_TOOLS,
    "banco-selfservice-chat-es": CHAT_TOOLS,
    "banco-agent-assist-es": ASSIST_TOOLS,
}

# (surface, expected count, expected tool-name set) for the build_tools complement.
SURFACE_EXPECTATIONS = {
    "voice": (AgentSurface.VOICE, 12, VOICE_TOOLS),
    "chat": (AgentSurface.CHAT, 13, CHAT_TOOLS),
    "assist": (AgentSurface.ASSIST, 10, ASSIST_TOOLS),
}

# (bank prompt, telco source prompt) pairs for the structure-preservation check.
PROMPT_PAIRS = {
    "voice": (
        BANK_ROOT / config.AI_AGENT_VOICE_PROMPT,
        TELCO_ROOT
        / "connect_ai_agents/telco-selfservice-voice/prompts/telco-selfservice-orchestration-voice.yaml",
    ),
    "chat": (
        BANK_ROOT / config.AI_AGENT_CHAT_PROMPT,
        TELCO_ROOT
        / "connect_ai_agents/telco-selfservice-chat/prompts/telco-selfservice-orchestration-chat.yaml",
    ),
    "assist": (
        BANK_ROOT / config.AI_AGENT_ASSIST_PROMPT,
        TELCO_ROOT
        / "connect_ai_agents/telco-agent-assist-es/prompts/telco-agent-assist-orchestration-es.yaml",
    ),
}

# XML-like section marker, e.g. <core_behavior> or </security>. Template
# placeholders ({{$.locale}}) never match this pattern.
_SECTION_MARKER = re.compile(r"</?[a-z][a-z0-9_]*>")


@pytest.fixture(scope="module")
def template() -> Template:
    """Synthesize a fresh AiAgentsStack once and expose its template."""
    assert config.HAS_REAL_INSTANCE, (
        "this suite requires HAS_REAL_INSTANCE=True so the gated agents synthesize"
    )
    app = cdk.App()
    stack = AiAgentsStack(app, "CX-BANCO-AGENTS")
    return Template.from_stack(stack)


# --------------------------------------------------------------------------- #
# Prompt structure-preservation helpers
# --------------------------------------------------------------------------- #

def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _messages_shape(prompt: dict) -> list:
    """The structural shape of the ``messages`` list: ``"str"`` for a plain
    string entry, or the sorted key tuple for a mapping entry."""
    shape = []
    for msg in prompt.get("messages", []):
        if isinstance(msg, str):
            shape.append("str")
        elif isinstance(msg, dict):
            shape.append(tuple(sorted(msg.keys())))
        else:
            shape.append(type(msg).__name__)
    return shape


def _section_markers(prompt: dict) -> list[str]:
    """Ordered sequence of XML-like section markers in the ``system`` body."""
    system = prompt.get("system", "")
    return _SECTION_MARKER.findall(system)


def _marker_structure(markers: list[str]) -> list[tuple[bool, int]]:
    """Domain-agnostic skeleton of a marker sequence.

    Each marker becomes ``(is_close, first_appearance_index_of_its_name)``, so a
    section that was re-themed (e.g. ``<new_line_tool_guidance>`` ->
    ``<new_card_tool_guidance>``) still maps to the same position/index as long
    as it opens and closes in the same place. This asserts the *structure* —
    section count, order, and open/close nesting — while tolerating the
    content-only re-theme of a section's name (Requirement 7.11 permits renaming
    identifiers; it forbids adding/removing/reordering sections).
    """
    order: dict[str, int] = {}
    structure: list[tuple[bool, int]] = []
    for marker in markers:
        is_close = marker.startswith("</")
        name = marker.strip("</>")
        if name not in order:
            order[name] = len(order)
        structure.append((is_close, order[name]))
    return structure


def _agent_tool_names(agent: dict) -> set[str]:
    tool_configs = (
        agent["Properties"]["Configuration"]
        ["OrchestrationAIAgentConfiguration"]["ToolConfigurations"]
    )
    return {tc["ToolName"] for tc in tool_configs}


def _agents_by_name(template: Template) -> dict[str, dict]:
    agents = template.find_resources("AWS::Wisdom::AIAgent")
    return {a["Properties"]["Name"]: a for a in agents.values()}


# --------------------------------------------------------------------------- #
# Requirements 7.1, 7.2 — exactly three prompts and three agents
# --------------------------------------------------------------------------- #

def test_exactly_three_prompts(template: Template):
    template.resource_count_is("AWS::Wisdom::AIPrompt", 3)


def test_exactly_three_agents(template: Template):
    template.resource_count_is("AWS::Wisdom::AIAgent", 3)


# --------------------------------------------------------------------------- #
# Requirement 7.3 — banking identifiers on prompts and agents
# --------------------------------------------------------------------------- #

def test_prompt_identifiers_are_banking(template: Template):
    prompts = template.find_resources("AWS::Wisdom::AIPrompt")
    names = {p["Properties"]["Name"] for p in prompts.values()}
    assert names == EXPECTED_PROMPT_NAMES, (
        f"prompt identifiers {sorted(names)} != {sorted(EXPECTED_PROMPT_NAMES)}"
    )


def test_agent_identifiers_are_banking(template: Template):
    names = set(_agents_by_name(template))
    assert names == EXPECTED_AGENT_NAMES, (
        f"agent identifiers {sorted(names)} != {sorted(EXPECTED_AGENT_NAMES)}"
    )


# --------------------------------------------------------------------------- #
# Requirement 7.1 — per-surface tool surfaces (12 / 13 / 10) from the template
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("agent_name", sorted(EXPECTED_TOOLS_BY_AGENT))
def test_agent_tool_surface_matches(template: Template, agent_name: str):
    agents = _agents_by_name(template)
    assert agent_name in agents, f"missing agent {agent_name}"
    tool_names = _agent_tool_names(agents[agent_name])
    expected = EXPECTED_TOOLS_BY_AGENT[agent_name]
    assert tool_names == expected, (
        f"{agent_name} tool set diverged — "
        f"missing={sorted(expected - tool_names)}, "
        f"extra={sorted(tool_names - expected)}"
    )
    assert len(tool_names) == len(expected), (
        f"{agent_name} has duplicate tools: expected {len(expected)} distinct, "
        f"found {len(tool_names)}"
    )


def test_agent_tool_counts(template: Template):
    agents = _agents_by_name(template)
    counts = {
        name: len(
            agent["Properties"]["Configuration"]
            ["OrchestrationAIAgentConfiguration"]["ToolConfigurations"]
        )
        for name, agent in agents.items()
    }
    assert counts == {
        "banco-selfservice-voice-es": 12,
        "banco-selfservice-chat-es": 13,
        "banco-agent-assist-es": 10,
    }, f"per-agent tool counts diverged: {counts}"


# --------------------------------------------------------------------------- #
# Requirement 7.1 — build_tools complement (independent of synth)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("surface", sorted(SURFACE_EXPECTATIONS), ids=sorted(SURFACE_EXPECTATIONS))
def test_build_tools_surface_counts_and_names(surface: str):
    agent_surface, expected_count, expected_names = SURFACE_EXPECTATIONS[surface]
    tools = build_tools(
        agent_surface,
        TOOLSET,
        assistant_association_id="assoc-test",
        mcp_tool_prefix="gateway_test__banco-rest-api-oas-target___",
        content_language=config.AI_AGENT_CONTENT_LANGUAGE,
    )
    assert len(tools) == expected_count, (
        f"{surface}: build_tools produced {len(tools)} tools, expected {expected_count}"
    )
    names = {t["toolName"] for t in tools}
    assert names == expected_names, (
        f"{surface}: tool-name set diverged — "
        f"missing={sorted(expected_names - names)}, "
        f"extra={sorted(names - expected_names)}"
    )


# --------------------------------------------------------------------------- #
# Requirements 7.3, 7.11 — prompt structure-preservation vs the telco source
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("pair", sorted(PROMPT_PAIRS), ids=sorted(PROMPT_PAIRS))
def test_prompt_source_files_exist(pair: str):
    bank_path, telco_path = PROMPT_PAIRS[pair]
    assert bank_path.is_file(), f"missing banking prompt {bank_path}"
    assert telco_path.is_file(), f"missing telco source prompt {telco_path}"


@pytest.mark.parametrize("pair", sorted(PROMPT_PAIRS), ids=sorted(PROMPT_PAIRS))
def test_prompt_top_level_keys_identical(pair: str):
    bank_path, telco_path = PROMPT_PAIRS[pair]
    bank = _load_yaml(bank_path)
    telco = _load_yaml(telco_path)
    assert set(bank.keys()) == set(telco.keys()), (
        f"{pair}: top-level YAML keys diverged — "
        f"bank={sorted(bank.keys())}, telco={sorted(telco.keys())}"
    )


@pytest.mark.parametrize("pair", sorted(PROMPT_PAIRS), ids=sorted(PROMPT_PAIRS))
def test_prompt_messages_shape_identical(pair: str):
    bank_path, telco_path = PROMPT_PAIRS[pair]
    bank = _load_yaml(bank_path)
    telco = _load_yaml(telco_path)
    assert _messages_shape(bank) == _messages_shape(telco), (
        f"{pair}: messages shape diverged — "
        f"bank={_messages_shape(bank)}, telco={_messages_shape(telco)}"
    )


@pytest.mark.parametrize("pair", sorted(PROMPT_PAIRS), ids=sorted(PROMPT_PAIRS))
def test_prompt_section_markers_identical(pair: str):
    """The <section> structure in the system body must match the telco source —
    same section count, order, and open/close nesting — allowing only the
    content-only re-theme of a section's *name* (e.g. new_line -> new_card)."""
    bank_path, telco_path = PROMPT_PAIRS[pair]
    bank_markers = _section_markers(_load_yaml(bank_path))
    telco_markers = _section_markers(_load_yaml(telco_path))

    # Same number of markers.
    assert len(bank_markers) == len(telco_markers), (
        f"{pair}: section-marker count diverged — "
        f"bank={len(bank_markers)}, telco={len(telco_markers)}"
    )
    # Same structural skeleton (order + open/close nesting), tolerating a
    # re-themed section name that keeps the same position.
    assert _marker_structure(bank_markers) == _marker_structure(telco_markers), (
        f"{pair}: section structure diverged from the telco source — "
        f"bank={bank_markers}, telco={telco_markers}"
    )
    # Any marker that is not byte-identical must be a re-themed *name only* —
    # never a telco token surviving in the bank prompt.
    for marker in bank_markers:
        assert "telco" not in marker.lower(), (
            f"{pair}: telco token survives in a section marker: {marker!r}"
        )


@pytest.mark.parametrize("pair", sorted(PROMPT_PAIRS), ids=sorted(PROMPT_PAIRS))
def test_prompt_content_actually_rethemed(pair: str):
    """Structure is preserved, but the content must have changed — guard against
    an accidental verbatim copy that would leave telco wording in a bank prompt."""
    bank_path, telco_path = PROMPT_PAIRS[pair]
    bank = _load_yaml(bank_path)
    telco = _load_yaml(telco_path)
    assert bank != telco, (
        f"{pair}: banking prompt is identical to the telco source — not re-themed"
    )
    assert "telco" not in json.dumps(bank).lower(), (
        f"{pair}: a 'telco' substring survives in the banking prompt content"
    )
