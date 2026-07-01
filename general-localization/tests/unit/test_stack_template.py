"""CDK template snapshot/unit tests for GeneralLocalizationStack (task 10.7).

These are ordinary unit/snapshot tests built on ``aws_cdk.assertions.Template``
(NOT Hypothesis property tests). They assert the synthesized CloudFormation
template shape against the placeholder ``config.py`` (``es_US`` enabled,
``pt_BR`` disabled), covering:

  - offline synth with placeholder config (Req 2.1)
  - fail-closed on a blank required constant (Req 1.7, 2.2)
  - the four distinct AI prompts + versions per enabled locale (Req 5.1, 5.2, 5.6)
  - the three utility AI agents with correct Type/locale (Req 6.1, 7.1, 8.1)
  - the shared answer-generation prompt version (Req 5.2, 6.2, 7.2)
  - the Note Taking noteTakingAIPromptId wiring (Req 8.2)
  - the single localized queue flow's block sequence + distinct name (Req 3.1, 3.5)
  - one ARN output per created resource with unique logical names (Req 11.1-11.4)

The AI agents are native ``AWS::Wisdom::AIAgent`` (+ ``AWS::Wisdom::AIAgentVersion``)
L1 resources; there is no boto3 custom resource. The agent configuration is a
structured ``Configuration`` block (not a serialized ConfigJson string).
"""

import json

import aws_cdk as core
import aws_cdk.assertions as assertions
import pytest

import config
from config_validation import ConfigError
from general_localization.general_localization_stack import GeneralLocalizationStack

# CloudFormation resource type strings.
AI_PROMPT_TYPE = "AWS::Wisdom::AIPrompt"
AI_PROMPT_VERSION_TYPE = "AWS::Wisdom::AIPromptVersion"
AI_AGENT_TYPE = "AWS::Wisdom::AIAgent"
AI_AGENT_VERSION_TYPE = "AWS::Wisdom::AIAgentVersion"
CONTACT_FLOW_TYPE = "AWS::Connect::ContactFlow"


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def template() -> assertions.Template:
    """Synth the stack against the placeholder config and return its Template.

    Building the Template offline (no AWS profile/credentials/lookup) is itself
    the realization of Requirement 2.1 — synthesis completes without any AWS
    API call against a live Connect instance or Q in Connect assistant.
    """
    app = core.App()
    stack = GeneralLocalizationStack(app, "general-localization-test")
    return assertions.Template.from_stack(stack)


def _agent_config_block(props) -> dict:
    """Return the single ``*AIAgentConfiguration`` block of an AI agent's
    native ``Configuration`` property (the one non-None typed-union member)."""
    configuration = props["Configuration"]
    assert len(configuration) == 1, configuration
    return next(iter(configuration.values()))


def _collect_getatt_logical_ids(node) -> set:
    """Recursively collect every ``Fn::GetAtt`` target logical id under ``node``."""
    found: set = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "Fn::GetAtt" and isinstance(value, list) and value:
                found.add(value[0])
            else:
                found |= _collect_getatt_logical_ids(value)
    elif isinstance(node, list):
        for item in node:
            found |= _collect_getatt_logical_ids(item)
    return found


def _flow_content_actions(content) -> list:
    """Return the flow Content's Actions list, tolerating a tokenized Content.

    When the flow JSON embeds no CDK tokens, ``Content`` is a plain JSON string.
    Once it embeds tokens (e.g. the queue music prompt ARN built from
    ``Aws.REGION``/``Aws.ACCOUNT_ID``), CloudFormation renders ``Content`` as an
    ``Fn::Join`` of literal fragments interleaved with ``Ref``/``GetAtt`` dicts.
    We rebuild a parseable string by substituting each token with a placeholder
    (tokens always sit inside a quoted JSON string value, so the result stays
    valid JSON)."""
    if isinstance(content, str):
        return json.loads(content)["Actions"]
    parts = content["Fn::Join"][1]
    rebuilt = "".join(p if isinstance(p, str) else "TOKEN" for p in parts)
    return json.loads(rebuilt)["Actions"]


def _agents_by_type(template: assertions.Template) -> dict:
    """Map each AWS::Wisdom::AIAgent's agent Type -> its Properties dict."""
    resources = template.find_resources(AI_AGENT_TYPE)
    by_type = {}
    for resource in resources.values():
        props = resource["Properties"]
        by_type[props["Type"]] = props
    return by_type


# --------------------------------------------------------------------------- #
# Req 2.1 — offline synth with placeholder config
# --------------------------------------------------------------------------- #
def test_synth_offline_with_placeholder_config(template):
    """Instantiating the stack and rendering the template succeeds offline,
    performing no AWS lookup/API call (Req 2.1)."""
    # The fixture already synthesized; a non-empty template proves success.
    assert template.to_json()["Resources"]


# --------------------------------------------------------------------------- #
# Req 1.7, 2.2 — fail-closed on a blank required constant
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("blank_value", ["", "   "])
def test_blank_required_constant_raises_named_configerror(monkeypatch, blank_value):
    """Blanking a required constant (ASSISTANT_ID) raises ConfigError naming it,
    before any resource is defined, so no template is produced (Req 1.7, 2.2)."""
    monkeypatch.setattr(config, "ASSISTANT_ID", blank_value)

    app = core.App()
    with pytest.raises(ConfigError) as exc_info:
        GeneralLocalizationStack(app, "general-localization-blank")

    # The error names the missing constant; resolution fails in the constructor
    # before any construct is created (the stack defines no resources).
    assert "ASSISTANT_ID" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Req 5.1, 5.2, 5.6 — four distinct AI prompts + matching versions per locale
# --------------------------------------------------------------------------- #
def test_four_ai_prompts_for_enabled_locale(template):
    """Exactly four AI prompts exist (one enabled AI-agent locale, es_US), each
    created under the configured assistant (Req 5.1, 5.3)."""
    template.resource_count_is(AI_PROMPT_TYPE, 4)
    prompts = template.find_resources(AI_PROMPT_TYPE)
    for resource in prompts.values():
        assert resource["Properties"]["AssistantId"] == config.ASSISTANT_ID


def test_four_ai_prompt_versions_for_enabled_locale(template):
    """A matching published version exists for each of the four prompts
    (Req 5.6/5.7)."""
    template.resource_count_is(AI_PROMPT_VERSION_TYPE, 4)


# --------------------------------------------------------------------------- #
# Req 6.1, 7.1, 8.1 — three utility agents with correct Type + locale
# --------------------------------------------------------------------------- #
def test_three_ai_agents_with_correct_types(template):
    """Exactly three AWS::Wisdom::AIAgent resources exist, one of each type
    (Req 6.1, 7.1, 8.1)."""
    template.resource_count_is(AI_AGENT_TYPE, 3)
    by_type = _agents_by_type(template)
    assert set(by_type) == {
        "ANSWER_RECOMMENDATION",
        "MANUAL_SEARCH",
        "NOTE_TAKING",
    }


def test_each_agent_publishes_a_version(template):
    """Each native AI agent publishes one AIAgentVersion (Req 5.6 parity with
    the previous custom-resource behavior)."""
    template.resource_count_is(AI_AGENT_VERSION_TYPE, 3)


def test_agents_carry_es_us_locale(template):
    """Each agent's configuration is stamped with the active es_US locale, and
    the agent name encodes es_US (Req 6.1, 7.1, 8.1 + Req 6.3/7.3/8.3)."""
    by_type = _agents_by_type(template)
    for agent_type, props in by_type.items():
        block = _agent_config_block(props)
        assert block["Locale"] == "es_US", agent_type
        assert "es_US" in props["Name"]


# --------------------------------------------------------------------------- #
# Req 5.2, 6.2, 7.2 — Answer Rec + Manual Search share the SAME answer-gen version
# --------------------------------------------------------------------------- #
def test_answer_rec_and_manual_search_share_answer_generation_version(template):
    """The Answer Recommendation and Manual Search agents reference the SAME
    answer-generation prompt version (Req 5.2, 6.2, 7.2).

    Pragmatic token handling: the version id is a CFN token, so the ConfigJson
    is an ``Fn::Join`` carrying an ``Fn::GetAtt`` to the version's logical id.
    The single logical id shared between the two agents' GetAtt sets must be the
    answer-generation AIPromptVersion (identified by logical-id name).
    """
    versions = template.find_resources(AI_PROMPT_VERSION_TYPE)
    answer_gen_version_ids = {
        logical_id for logical_id in versions if "AnswerGeneration" in logical_id
    }
    assert len(answer_gen_version_ids) == 1, answer_gen_version_ids

    by_type = _agents_by_type(template)
    ar_getatts = _collect_getatt_logical_ids(by_type["ANSWER_RECOMMENDATION"]["Configuration"])
    ms_getatts = _collect_getatt_logical_ids(by_type["MANUAL_SEARCH"]["Configuration"])

    # Both agents reference the answer-generation version...
    assert answer_gen_version_ids <= ar_getatts
    assert answer_gen_version_ids <= ms_getatts
    # ...and it is the ONLY prompt-version logical id they share (Manual Search
    # references only the shared answer-generation version).
    assert ar_getatts & ms_getatts == answer_gen_version_ids


# --------------------------------------------------------------------------- #
# Req 8.2 — Note Taking uses noteTakingAIAgentConfiguration.noteTakingAIPromptId
# --------------------------------------------------------------------------- #
def test_note_taking_uses_note_taking_prompt_id(template):
    """The Note Taking agent wires its prompt as
    NoteTakingAIAgentConfiguration.NoteTakingAIPromptId (Req 8.2)."""
    by_type = _agents_by_type(template)
    configuration = by_type["NOTE_TAKING"]["Configuration"]
    assert "NoteTakingAIAgentConfiguration" in configuration
    assert "NoteTakingAIPromptId" in configuration["NoteTakingAIAgentConfiguration"]


# --------------------------------------------------------------------------- #
# Req 3.1, 3.5 — single localized queue flow, block sequence + distinct name
# --------------------------------------------------------------------------- #
def test_single_customer_queue_flow_with_distinct_name(template):
    """Exactly one CUSTOMER_QUEUE contact flow exists with a name distinct from
    the Default Customer Queue (Req 3.1, 3.5)."""
    flows = template.find_resources(CONTACT_FLOW_TYPE)
    assert len(flows) == 1
    props = next(iter(flows.values()))["Properties"]
    assert props["Type"] == "CUSTOMER_QUEUE"
    assert props["Name"] != "Default Customer Queue"
    assert props["Name"] == "Localized Customer Queue"


def test_queue_flow_block_sequence_matches_default(template):
    """Each language path mirrors the Default block-type sequence:
    UpdateContactTextToSpeechVoice -> MessageParticipantIteratively, where the
    single loop block loops BOTH the TTS hold text and the queue audio, exactly
    like the live Default Customer Queue (Req 3.1)."""
    flows = template.find_resources(CONTACT_FLOW_TYPE)
    content = next(iter(flows.values()))["Properties"]["Content"]
    actions_by_id = {
        action["Identifier"]: action for action in _flow_content_actions(content)
    }

    for prefix in ("es", "pt", "en"):
        set_voice = actions_by_id[f"{prefix}-set-voice"]
        assert set_voice["Type"] == "UpdateContactTextToSpeechVoice"

        loop_id = set_voice["Transitions"]["NextAction"]
        loop = actions_by_id[loop_id]
        assert loop["Type"] == "MessageParticipantIteratively"

        # The loop block carries both the TTS hold text and the queue music
        # prompt together (no separate Play prompt block), like the Default.
        messages = loop["Parameters"]["Messages"]
        assert any("Text" in m for m in messages)
        assert any("PromptId" in m for m in messages)


# --------------------------------------------------------------------------- #
# Req 11.1-11.4 — one ARN output per created resource, unique logical names
# --------------------------------------------------------------------------- #
def test_outputs_correspond_to_created_resources(template):
    """Outputs exist with unique logical names: exactly one QueueFlowArn, four
    AiPrompt*EsUs*Arn, and three AiAgent*EsUs*Arn, each carrying a value
    (Req 11.1-11.4)."""
    outputs = template.to_json().get("Outputs", {})

    queue_outputs = [name for name in outputs if name == "QueueFlowArn"]
    prompt_outputs = [
        name
        for name in outputs
        if name.startswith("AiPrompt") and "EsUs" in name and name.endswith("Arn")
    ]
    agent_outputs = [
        name
        for name in outputs
        if name.startswith("AiAgent") and "EsUs" in name and name.endswith("Arn")
    ]

    assert len(queue_outputs) == 1
    assert len(prompt_outputs) == 4
    assert len(agent_outputs) == 3

    # Logical names are unique and every output carries a (token) ARN value.
    relevant = queue_outputs + prompt_outputs + agent_outputs
    assert len(set(relevant)) == len(relevant)
    for name in relevant:
        assert "Value" in outputs[name]
