"""
tests/unit/test_tag_kb_content.py — mock-based unit tests for the post-deploy
KB tagging script ``knowledge_bases/tag_kb_content.py``.

Two behaviours are guarded here, both with boto3 stubbed out so no real AWS
call is ever made:

  1. ``_detect_language`` — infers the per-item ``language`` tag (es | pt | en)
     from a content item's ``airline/<lang>/`` source path segment, and returns
     ``None`` when no configured language segment is present
     (Requirements 10.5, 10.6).

  2. ``_resolve_kb_id`` — resolves the knowledge-base id in the exact order
     explicit argument -> manifest ``knowledgeBaseId`` -> SSM ``KB_ID`` and
     uses the first non-empty value found (Requirement 10.7); when none of the
     three sources yields a value it returns ``None`` so ``main`` can halt with
     the "no kb-id" error (Requirement 10.8).

Validates: Requirements 10.5, 10.6, 10.7, 10.8
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest

# tag_kb_content.py lives under knowledge_bases/ (a plain script directory, not
# an importable package on the default test path), so put it on sys.path and
# import it by module name. Importing the module runs its own sys.path shim to
# reach config/shared at the app root, so `import boto3` and
# `from shared import ssm_names` both resolve.
_APP_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
_KB_DIR = os.path.join(_APP_ROOT, "knowledge_bases")
if _KB_DIR not in sys.path:
    sys.path.insert(0, _KB_DIR)

tag_kb_content = importlib.import_module("tag_kb_content")


LANGUAGES = ["es", "pt", "en"]


# --------------------------------------------------------------------------- #
# _detect_language — Requirements 10.5, 10.6


@pytest.mark.parametrize(
    "name, expected",
    [
        ("airline/es/activar-tarjeta.txt", "es"),
        ("airline/pt/activar-tarjeta.txt", "pt"),
        ("airline/en/activar-tarjeta.txt", "en"),
    ],
)
def test_detect_language_from_airline_lang_segment(name, expected):
    """A ``airline/<lang>/`` path segment yields the matching language code."""
    assert tag_kb_content._detect_language({"name": name}, LANGUAGES) == expected


def test_detect_language_handles_windows_style_separators():
    """Backslash separators are split the same as forward slashes."""
    item = {"name": "airline\\pt\\cartoes.txt"}
    assert tag_kb_content._detect_language(item, LANGUAGES) == "pt"


def test_detect_language_falls_back_to_title_and_metadata():
    """When ``name`` has no segment, ``title`` then ``metadata`` are scanned."""
    by_title = {"name": "no-language-here.txt", "title": "airline/en/faq.txt"}
    assert tag_kb_content._detect_language(by_title, LANGUAGES) == "en"

    by_metadata = {
        "name": "no-language-here.txt",
        "metadata": {"sourcePath": "airline/es/cuentas.txt"},
    }
    assert tag_kb_content._detect_language(by_metadata, LANGUAGES) == "es"


@pytest.mark.parametrize(
    "name",
    [
        "airline/activar-tarjeta.txt",          # no language segment at all
        "other/es-mx/activar-tarjeta.txt",   # 'es-mx' is not a configured code
        "activar-tarjeta.txt",               # bare file name
    ],
)
def test_detect_language_returns_none_when_absent(name):
    """No configured language segment -> ``None`` (caller then errors out)."""
    assert tag_kb_content._detect_language({"name": name}, LANGUAGES) is None


# --------------------------------------------------------------------------- #
# _resolve_kb_id — Requirements 10.7, 10.8


def _mock_ssm_client(monkeypatch, value):
    """Patch the module's boto3 so ``client('ssm').get_parameter`` returns
    ``value``. Returns the boto3.client Mock so callers can assert on it."""
    ssm = MagicMock()
    ssm.get_parameter.return_value = {"Parameter": {"Value": value}}
    client = MagicMock(return_value=ssm)
    monkeypatch.setattr(tag_kb_content.boto3, "client", client)
    return client


def test_resolve_kb_id_prefers_explicit_argument(monkeypatch):
    """Explicit --kb-id wins over both manifest and SSM, and short-circuits
    before any boto3/SSM call is made (Requirement 10.7)."""
    client = _mock_ssm_client(monkeypatch, "kb-from-ssm")
    manifest = {"knowledgeBaseId": "kb-from-manifest"}

    resolved = tag_kb_content._resolve_kb_id("kb-explicit", manifest)

    assert resolved == "kb-explicit"
    client.assert_not_called()


def test_resolve_kb_id_uses_manifest_before_ssm(monkeypatch):
    """With no explicit arg, a non-empty manifest ``knowledgeBaseId`` is used
    and the SSM lookup is never reached (Requirement 10.7)."""
    client = _mock_ssm_client(monkeypatch, "kb-from-ssm")
    manifest = {"knowledgeBaseId": "kb-from-manifest"}

    resolved = tag_kb_content._resolve_kb_id(None, manifest)

    assert resolved == "kb-from-manifest"
    client.assert_not_called()


def test_resolve_kb_id_falls_through_to_ssm(monkeypatch):
    """Empty explicit arg and empty manifest id fall through to the SSM
    ``KB_ID`` parameter (Requirement 10.7)."""
    client = _mock_ssm_client(monkeypatch, "kb-from-ssm")
    # Mirrors the real repo manifest, whose knowledgeBaseId is "".
    manifest = {"knowledgeBaseId": ""}

    resolved = tag_kb_content._resolve_kb_id(None, manifest)

    assert resolved == "kb-from-ssm"
    client.assert_called_once_with("ssm")
    ssm = client.return_value
    ssm.get_parameter.assert_called_once_with(Name=tag_kb_content.ssm_names.KB_ID)


def test_resolve_kb_id_missing_manifest_key_falls_through_to_ssm(monkeypatch):
    """A manifest with no ``knowledgeBaseId`` key at all still reaches SSM."""
    client = _mock_ssm_client(monkeypatch, "kb-from-ssm")

    resolved = tag_kb_content._resolve_kb_id(None, {})

    assert resolved == "kb-from-ssm"
    client.assert_called_once_with("ssm")


def test_resolve_kb_id_returns_none_when_nothing_resolves(monkeypatch):
    """When explicit + manifest are empty and the SSM lookup fails, the
    resolver returns ``None`` so ``main`` can halt with the no-kb-id error
    (Requirement 10.8)."""
    ssm = MagicMock()
    ssm.get_parameter.side_effect = Exception("ParameterNotFound")
    monkeypatch.setattr(tag_kb_content.boto3, "client", MagicMock(return_value=ssm))

    resolved = tag_kb_content._resolve_kb_id(None, {"knowledgeBaseId": ""})

    assert resolved is None
