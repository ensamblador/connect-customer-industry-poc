# Feature: message-localization, Property 3: Localized single-flow rendering
"""Property-based test for localized single-flow rendering (Property 3).

Validates: Requirements 3.1, 3.2, 3.3, 3.4

Property 3 (Localized single-flow rendering):
    For any valid English, Spanish, and Portuguese hold-message texts and TTS
    voice ids, rendering the single Localized_Queue_Flow substitutes the markers
    so the resulting Flow-language JSON contains three internal language paths —
    Spanish, Portuguese, and English — where each path's ``LoopPrompts``
    (``MessageParticipantIteratively``) block loops both that language's hold
    text and the shared queue audio, and each path's
    ``UpdateContactTextToSpeechVoice`` parameter contains exactly that
    language's voice; every path's block-type sequence remains that of the
    Default Customer Queue (``UpdateContactTextToSpeechVoice`` ->
    ``MessageParticipantIteratively`` loop prompts, where the single loop block
    carries both the TTS hold text and the queue audio — exactly like the live
    Default Customer Queue); and the English path is the target of the branch's
    ``NoMatchingCondition`` (default) transition.

The flow is rendered through the same ``connect.flows._load`` raw string
substitution that the ``ContactFlow`` construct uses at synth, so the test
reflects real rendering behavior. The rendered string is then ``json.loads``-ed
and its structure asserted.
"""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from connect.flows import _load

# The single localized customer-queue flow JSON (markers resolved at synth).
_FLOW_PATH = str(
    Path(__file__).resolve().parents[2]
    / "flows"
    / "localized-customer-queue"
    / "flow.json"
)

# Internal language paths inside the single Localized_Queue_Flow. Each path is a
# (set-voice, loop-prompts) Identifier pair, keyed by language. The queue audio
# now lives INSIDE the loop-prompts block (no separate Play prompt block),
# mirroring the live Default Customer Queue.
_PATHS = {
    "es": ("es-set-voice", "es-loop-prompts"),
    "pt": ("pt-set-voice", "pt-loop-prompts"),
    "en": ("en-set-voice", "en-loop-prompts"),
}

# The Default Customer Queue block-type sequence every path must reproduce:
# Set voice -> Loop prompts (the loop block plays both the TTS hold text and the
# queue audio, exactly like the live Default Customer Queue).
_EXPECTED_SEQUENCE = (
    "UpdateContactTextToSpeechVoice",
    "MessageParticipantIteratively",
)

# The S3 queue audio looped inside each loop-prompts block.
_QUEUE_MUSIC_MARKER = "__QUEUE_MUSIC_PROMPT_ARN__"

# JSON-safe alphabet: printable text WITHOUT the characters that would break the
# document when substituted by raw ``str.replace`` (double quote, backslash) and
# WITHOUT the underscore, so a generated value can never collide with a
# ``__MARKER__`` token. Includes spaces and accented characters relevant to
# Spanish/Portuguese hold messages.
_SAFE_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " .,!?:;'-/()"
    "áéíóúñüÁÉÍÓÚÑÜàâãçêõôÀÂÃÇÊÕÔ"
)

# Non-empty, JSON-safe free text (hold messages). Bounded length keeps the
# substituted document well under the 3000-char ceiling.
_hold_text = st.text(alphabet=_SAFE_ALPHABET, min_size=1, max_size=120)

# Polly voice ids are simple identifiers (e.g. "Joanna", "Lupe", "Camila").
_voice_id = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    min_size=1,
    max_size=20,
)


def _by_identifier(doc: dict) -> dict:
    return {action["Identifier"]: action for action in doc["Actions"]}


def _next_action(action: dict) -> str:
    return action["Transitions"]["NextAction"]


def _text_messages(loop_block: dict) -> list[str]:
    """The Text entries in a loop block's Messages array."""
    return [m["Text"] for m in loop_block["Parameters"]["Messages"] if "Text" in m]


def _media_uris(loop_block: dict) -> list[str]:
    """The Media URIs in a loop block's Messages array."""
    return [
        m["Media"]["Uri"]
        for m in loop_block["Parameters"]["Messages"]
        if "Media" in m
    ]


def _prompt_ids(loop_block: dict) -> list[str]:
    """The PromptId entries in a loop block's Messages array."""
    return [m["PromptId"] for m in loop_block["Parameters"]["Messages"] if "PromptId" in m]


@settings(max_examples=150)
@given(
    hold_en=_hold_text,
    hold_es=_hold_text,
    hold_pt=_hold_text,
    voice_en=_voice_id,
    voice_es=_voice_id,
    voice_pt=_voice_id,
    engine=st.sampled_from(["neural", "standard"]),
)
def test_localized_single_flow_rendering(
    hold_en: str,
    hold_es: str,
    hold_pt: str,
    voice_en: str,
    voice_es: str,
    voice_pt: str,
    engine: str,
) -> None:
    replacements = {
        "__HOLD_MESSAGE_EN__": hold_en,
        "__HOLD_MESSAGE_ES__": hold_es,
        "__HOLD_MESSAGE_PT__": hold_pt,
        "__TTS_VOICE_EN__": voice_en,
        "__TTS_VOICE_ES__": voice_es,
        "__TTS_VOICE_PT__": voice_pt,
        "__TTS_ENGINE__": engine,
        _QUEUE_MUSIC_MARKER: "arn:aws:connect:us-west-2:111111111111:instance/abc/prompt/queue-music",
    }

    # Render via the same raw str.replace substitution the construct uses, then
    # parse the resulting Flow-language JSON.
    rendered = _load(_FLOW_PATH, replacements)
    doc = json.loads(rendered)
    actions = _by_identifier(doc)

    # No marker remains unresolved anywhere in the rendered document.
    for marker in replacements:
        assert marker not in rendered

    expected_hold = {"es": hold_es, "pt": hold_pt, "en": hold_en}
    expected_voice = {"es": voice_es, "pt": voice_pt, "en": voice_en}

    # There are three internal language paths: Spanish, Portuguese, English.
    for lang, (set_voice_id, loop_prompts_id) in _PATHS.items():
        assert set_voice_id in actions
        assert loop_prompts_id in actions

        set_voice = actions[set_voice_id]
        loop_prompts = actions[loop_prompts_id]

        # Each path's UpdateContactTextToSpeechVoice carries exactly this
        # language's voice (3.2/3.3/3.4).
        assert set_voice["Type"] == "UpdateContactTextToSpeechVoice"
        assert set_voice["Parameters"]["TextToSpeechVoice"] == expected_voice[lang]
        assert set_voice["Parameters"]["TextToSpeechEngine"] == engine

        # Each path's single LoopPrompts (MessageParticipantIteratively) block
        # loops BOTH this language's hold text AND the shared queue music
        # prompt, like the live Default Customer Queue (3.2/3.3/3.4).
        assert loop_prompts["Type"] == "MessageParticipantIteratively"
        assert expected_hold[lang] in _text_messages(loop_prompts)
        assert (
            "arn:aws:connect:us-west-2:111111111111:instance/abc/prompt/queue-music"
            in _prompt_ids(loop_prompts)
        )

        # Every path's block-type sequence matches the Default Customer Queue:
        # set voice -> loop prompts (the loop block carries text + audio) (3.1).
        assert _next_action(set_voice) == loop_prompts_id
        sequence = (set_voice["Type"], loop_prompts["Type"])
        assert sequence == _EXPECTED_SEQUENCE

    # The English path (en-set-voice) is the target of the Compare action's
    # NoMatchingCondition (default) transition (3.4 — English default/no-match).
    compare = next(a for a in doc["Actions"] if a["Type"] == "Compare")
    no_match = [
        err
        for err in compare["Transitions"]["Errors"]
        if err["ErrorType"] == "NoMatchingCondition"
    ]
    assert len(no_match) == 1
    assert no_match[0]["NextAction"] == "en-set-voice"
