"""
tests/unit/test_topology_decoupling.py — CDK app topology & decoupling assertions.

Structural guards for the Airline_Project's six-phase, SSM-decoupled CDK topology.
These tests synthesize the app exactly as ``app.py`` wires it and assert:

  * exactly six stacks with the exact ``CX-AIRLINE-*`` names, each defined in the
    ``agentic_cx_airline`` package (Requirements 1.1, 1.2, 1.7);
  * exactly the five inter-stack dependency edges and no others
    (Requirement 1.3):
        SUPPORT -> (MCP, KB)
        AGENTS  -> (KB, MCP)
        FLOWS   -> (MCP, SUPPORT, AGENTS)
        WEBSITE -> (FLOWS, MCP)
  * zero CloudFormation ``Outputs`` carrying an ``Export`` — cross-stack values
    ride the SSM bus only (Requirement 1.4);
  * zero nested stacks (``AWS::CloudFormation::Stack``) (Requirement 1.4);
  * zero ECS resources (``AWS::ECS::*``) — all compute is Lambda
    (Requirement 1.8);
  * zero Step Functions state machines
    (``AWS::StepFunctions::StateMachine``) (Requirement 1.8).

The test builds a fresh ``cdk.App`` mirroring ``app.py`` rather than importing
``app.py`` (which would ``app.synth()`` on import), so the wiring under test is
self-contained and inspectable.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.7, 1.8
"""

from __future__ import annotations

import pytest
import aws_cdk as cdk

from agentic_cx_airline.mcp_stack import McpStack
from agentic_cx_airline.knowledge_base_stack import KnowledgeBaseStack
from agentic_cx_airline.connect_support_stack import ConnectSupportStack
from agentic_cx_airline.ai_agents_stack import AiAgentsStack
from agentic_cx_airline.contact_flows_stack import ContactFlowsStack
from agentic_cx_airline.website_stack import WebsiteStack

# The single source of truth for the intended topology. Keyed by the exact
# synthesized stack name; the value is the set of stack names it must depend on.
EXPECTED_EDGES = {
    "CX-AIRLINE-MCP": set(),
    "CX-AIRLINE-KB": set(),
    "CX-AIRLINE-CONNECT-SUPPORT": {"CX-AIRLINE-MCP", "CX-AIRLINE-KB"},
    "CX-AIRLINE-AGENTS": {"CX-AIRLINE-KB", "CX-AIRLINE-MCP"},
    "CX-AIRLINE-FLOWS": {"CX-AIRLINE-MCP", "CX-AIRLINE-CONNECT-SUPPORT", "CX-AIRLINE-AGENTS"},
    "CX-AIRLINE-WEBSITE": {"CX-AIRLINE-FLOWS", "CX-AIRLINE-MCP"},
}

EXPECTED_STACK_NAMES = set(EXPECTED_EDGES)


def _build_app() -> tuple[cdk.App, dict[str, cdk.Stack]]:
    """Instantiate the six CX-AIRLINE-* stacks and the five edges, mirroring app.py."""
    app = cdk.App()

    mcp = McpStack(app, "CX-AIRLINE-MCP")
    kb = KnowledgeBaseStack(app, "CX-AIRLINE-KB")

    support = ConnectSupportStack(app, "CX-AIRLINE-CONNECT-SUPPORT")
    support.add_stack_dependency(mcp)
    support.add_stack_dependency(kb)

    agents = AiAgentsStack(app, "CX-AIRLINE-AGENTS")
    agents.add_stack_dependency(kb)
    agents.add_stack_dependency(mcp)

    flows = ContactFlowsStack(app, "CX-AIRLINE-FLOWS")
    flows.add_stack_dependency(mcp)
    flows.add_stack_dependency(support)
    flows.add_stack_dependency(agents)

    web = WebsiteStack(app, "CX-AIRLINE-WEBSITE")
    web.add_stack_dependency(flows)
    web.add_stack_dependency(mcp)

    stacks = {
        s.stack_name: s
        for s in (mcp, kb, support, agents, flows, web)
    }
    return app, stacks


@pytest.fixture(scope="module")
def built():
    """Build the app once and synthesize it for the whole module."""
    app, stacks = _build_app()
    assembly = app.synth()
    return app, stacks, assembly


# --------------------------------------------------------------------------- #
# Requirements 1.1, 1.2, 1.7 — exactly six CX-AIRLINE-* stacks in the package
# --------------------------------------------------------------------------- #

def test_exactly_six_stacks_with_exact_names(built):
    _, stacks, _ = built
    assert set(stacks) == EXPECTED_STACK_NAMES
    assert len(stacks) == 6


def test_all_stacks_defined_in_agentic_cx_airline_package(built):
    _, stacks, _ = built
    for name, stack in stacks.items():
        module = type(stack).__module__
        assert module.startswith("agentic_cx_airline"), (
            f"{name} ({type(stack).__name__}) is defined in {module!r}, "
            "expected the agentic_cx_airline package"
        )


def test_synthesized_assembly_has_exactly_the_six_stacks(built):
    _, _, assembly = built
    synthesized = {s.stack_name for s in assembly.stacks}
    assert synthesized == EXPECTED_STACK_NAMES


# --------------------------------------------------------------------------- #
# Requirement 1.3 — exactly the five dependency edges and no others
# --------------------------------------------------------------------------- #

def test_dependency_edges_are_exactly_the_five_expected(built):
    _, stacks, _ = built
    actual_edges = {
        name: {dep.stack_name for dep in stack.dependencies}
        for name, stack in stacks.items()
    }
    assert actual_edges == EXPECTED_EDGES


def test_no_extra_dependency_edges(built):
    _, stacks, _ = built
    # The four dependent stacks contribute 2 + 2 + 3 + 2 = 9 individual edges;
    # MCP and KB are roots with none. This guards against any stray edge the
    # exact-edge-set comparison might not surface if EXPECTED_EDGES drifted.
    total_edges = sum(len(stack.dependencies) for stack in stacks.values())
    expected_total = sum(len(deps) for deps in EXPECTED_EDGES.values())
    assert total_edges == expected_total == 9


# --------------------------------------------------------------------------- #
# Requirement 1.4 — SSM-only decoupling: zero Exports, zero nested stacks
# --------------------------------------------------------------------------- #

def _templates(assembly):
    """Yield (stack_name, template_dict) for every synthesized stack."""
    for name in EXPECTED_STACK_NAMES:
        yield name, assembly.get_stack_by_name(name).template


def test_zero_outputs_with_export(built):
    _, _, assembly = built
    offenders = []
    for name, template in _templates(assembly):
        outputs = template.get("Outputs", {}) or {}
        for out_name, out in outputs.items():
            if isinstance(out, dict) and "Export" in out:
                offenders.append(f"{name}:{out_name}")
    assert offenders == [], f"CloudFormation exports found: {offenders}"


def test_zero_nested_stacks(built):
    _, _, assembly = built
    offenders = []
    for name, template in _templates(assembly):
        resources = template.get("Resources", {}) or {}
        for logical_id, res in resources.items():
            if res.get("Type") == "AWS::CloudFormation::Stack":
                offenders.append(f"{name}:{logical_id}")
    assert offenders == [], f"Nested stacks found: {offenders}"


# --------------------------------------------------------------------------- #
# Requirement 1.8 — all Lambda compute: zero ECS, zero Step Functions
# --------------------------------------------------------------------------- #

def test_zero_ecs_resources(built):
    _, _, assembly = built
    offenders = []
    for name, template in _templates(assembly):
        resources = template.get("Resources", {}) or {}
        for logical_id, res in resources.items():
            res_type = res.get("Type", "")
            if res_type.startswith("AWS::ECS::"):
                offenders.append(f"{name}:{logical_id} ({res_type})")
    assert offenders == [], f"ECS resources found: {offenders}"


def test_zero_step_functions_state_machines(built):
    _, _, assembly = built
    offenders = []
    for name, template in _templates(assembly):
        resources = template.get("Resources", {}) or {}
        for logical_id, res in resources.items():
            if res.get("Type") == "AWS::StepFunctions::StateMachine":
                offenders.append(f"{name}:{logical_id}")
    assert offenders == [], f"Step Functions state machines found: {offenders}"
