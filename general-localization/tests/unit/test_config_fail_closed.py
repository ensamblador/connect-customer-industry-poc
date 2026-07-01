"""Fail-closed config-resolution tests for GeneralLocalizationStack (task 7.4).

These are ordinary unit tests (NOT Hypothesis property tests). They assert the
Fail_Closed_Synth convention (design decision D11, Requirement 6.8): a missing or
blank value for any configuration constant that ``_resolve_config`` requires
raises ``ConfigError`` *naming* the offending constant, during config resolution,
**before any construct is created**, so the stack emits no template.

``_resolve_config`` runs first in the constructor and calls
``require(name, value)`` for the two reused identity constants ``INSTANCE_ID`` /
``ASSISTANT_ID``. ``require`` raises ``ConfigError`` naming the constant when the
value is ``None``, not a string, empty, or whitespace-only.

Each case blanks/removes exactly one required constant via monkeypatch and
asserts:
  1. constructing the stack raises ``ConfigError`` whose message names the
     blanked constant (resolution fails in the constructor), and
  2. synthesizing the app afterward yields a stack template with **no**
     ``Resources`` — i.e. no construct was created and no template was emitted.
"""

import aws_cdk as core
import pytest

import config
from config_validation import ConfigError
from general_localization.general_localization_stack import GeneralLocalizationStack

# The constants ``_resolve_config`` requires before any construct is created:
# the two reused Connect / Q in Connect identities.
REQUIRED_CONSTANTS = [
    "INSTANCE_ID",
    "ASSISTANT_ID",
]

# A blank value is the empty string, whitespace-only, or an absent value
# (``None``) — all three are treated as "missing or empty" by ``require``.
BLANK_OR_MISSING_VALUES = ["", "   ", "\t\n", None]


def _assert_no_template_emitted(app: core.App, stack_name: str) -> None:
    """Assert the (partially constructed) stack produced no CloudFormation
    template — i.e. config resolution failed before any construct was created,
    so the synthesized stack has an empty ``Resources`` map."""
    assembly = app.synth()
    stack_artifacts = [s for s in assembly.stacks if s.stack_name == stack_name]
    assert len(stack_artifacts) == 1, stack_artifacts
    resources = stack_artifacts[0].template.get("Resources", {})
    assert resources == {}, f"expected no resources, got {sorted(resources)}"


@pytest.mark.parametrize("constant_name", REQUIRED_CONSTANTS)
@pytest.mark.parametrize("blank_value", BLANK_OR_MISSING_VALUES)
def test_blank_or_missing_required_constant_fails_closed(
    monkeypatch, constant_name, blank_value
):
    """Blanking/removing any required constant raises ``ConfigError`` naming it
    during ``_resolve_config``, before any construct is created, emitting no
    template (Req 6.8, D11)."""
    monkeypatch.setattr(config, constant_name, blank_value)

    stack_name = f"gl-fail-closed-{constant_name.lower().replace('_', '-')}"
    app = core.App()
    with pytest.raises(ConfigError) as exc_info:
        GeneralLocalizationStack(app, stack_name)

    # 1) The error names the offending constant.
    assert constant_name in str(exc_info.value)

    # 2) No construct was created and no template was emitted.
    _assert_no_template_emitted(app, stack_name)


@pytest.mark.parametrize("constant_name", REQUIRED_CONSTANTS)
def test_required_constant_truly_absent_fails_closed(monkeypatch, constant_name):
    """Deleting a required constant entirely (truly absent attribute) also fails
    closed with a ``ConfigError`` naming it (``getattr(config, name, None)`` ->
    ``None``), confirming the same fail-closed path for a missing value."""
    monkeypatch.delattr(config, constant_name, raising=False)

    stack_name = f"gl-absent-{constant_name.lower().replace('_', '-')}"
    app = core.App()
    with pytest.raises(ConfigError) as exc_info:
        GeneralLocalizationStack(app, stack_name)

    assert constant_name in str(exc_info.value)
    _assert_no_template_emitted(app, stack_name)


def test_all_required_constants_present_synthesizes_resources():
    """Sanity baseline: with the placeholder config intact (every required
    constant present), resolution succeeds and the stack DOES emit a template
    with resources — proving the fail-closed cases above are caused by the blank
    value, not an unrelated synth failure."""
    app = core.App()
    stack = GeneralLocalizationStack(app, "gl-baseline")
    assembly = app.synth()
    artifact = next(s for s in assembly.stacks if s.stack_name == "gl-baseline")
    assert artifact.template.get("Resources"), "expected a non-empty template"
    assert stack is not None
