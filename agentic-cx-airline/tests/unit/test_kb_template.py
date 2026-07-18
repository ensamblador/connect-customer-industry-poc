"""
tests/unit/test_kb_template.py — CX-AIRLINE-KB (Phase 2) template + coverage asserts.

Two complementary layers of guard for the airline knowledge base:

  1. CDK template assertions — synthesize a fresh ``KnowledgeBaseStack`` and
     assert the Phase-2 KB contract against the resulting CloudFormation
     template:
       * exactly one EXTERNAL ``AWS::Wisdom::KnowledgeBase`` (Requirement 5.1);
       * exactly one ``AWS::Wisdom::AssistantAssociation`` of type
         ``KNOWLEDGE_BASE`` bound to the configured assistant (Requirement 5.1);
       * the KB ``Tags`` carry ``industry = airline`` (Requirements 5.1, 10.2).

  2. Coverage / manifest asset checks — read the repo's KB assets directly from
     the filesystem (no synth) and assert:
       * each of the seven self-service topics has exactly one file in each of
         ``es`` / ``pt`` / ``en`` (21 files total) (Requirement 5.5);
       * the manifest declares ``resourceTags == {"industry": "airline"}``
         (Requirement 10.2);
       * a strict one-to-one correspondence between the 21 manifest entries and
         the 21 on-disk files — no document omitted and no manifest entry
         without a document (Requirement 5.9).

Validates: Requirements 5.1, 5.5, 5.9, 10.2
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

import config
from agentic_cx_airline.knowledge_base_stack import KnowledgeBaseStack

# --------------------------------------------------------------------------- #
# Fixtures / constants
# --------------------------------------------------------------------------- #

# Project root (agentic-cx-airline/): tests/unit/<this file> -> parents[2].
PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_ROOT = PROJECT_ROOT / "knowledge_bases" / "airline"
ENTRIES_DIR = KB_ROOT / "entries"
MANIFEST_PATH = KB_ROOT / "manifest.json"

# The seven self-service topics, and the three languages, that must each be
# fully covered (Requirements 5.2–5.5).
EXPECTED_TOPICS = {
    "reservas",
    "viajero-frecuente",
    "check-in",
    "equipaje",
    "faq-general",
    "aeropuertos",
    "maleta-perdida",
}
EXPECTED_LANGS = {"es", "pt", "en"}
EXPECTED_FILE_COUNT = len(EXPECTED_TOPICS) * len(EXPECTED_LANGS)  # 21


@pytest.fixture(scope="module")
def template() -> Template:
    """Synthesize a fresh KnowledgeBaseStack once and expose its template."""
    app = cdk.App()
    stack = KnowledgeBaseStack(app, "CX-AIRLINE-KB")
    return Template.from_stack(stack)


@pytest.fixture(scope="module")
def manifest() -> dict:
    """Load the KB manifest once for the module."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Requirement 5.1 — EXTERNAL Wisdom KB + assistant association
# --------------------------------------------------------------------------- #

def test_single_external_knowledge_base(template: Template):
    kbs = template.find_resources("AWS::Wisdom::KnowledgeBase")
    assert len(kbs) == 1, f"expected exactly one Wisdom KB, found {len(kbs)}"
    (kb,) = kbs.values()
    assert kb["Properties"].get("KnowledgeBaseType") == "EXTERNAL", (
        "the knowledge base must be of type EXTERNAL"
    )


def test_single_knowledge_base_assistant_association(template: Template):
    assocs = template.find_resources("AWS::Wisdom::AssistantAssociation")
    assert len(assocs) == 1, (
        f"expected exactly one assistant association, found {len(assocs)}"
    )
    (assoc,) = assocs.values()
    props = assoc["Properties"]
    assert props.get("AssociationType") == "KNOWLEDGE_BASE", (
        "the assistant association must be of type KNOWLEDGE_BASE"
    )
    assert props.get("AssistantId") == config.ASSISTANT_ID, (
        "the association must bind to the configured assistant id"
    )


# --------------------------------------------------------------------------- #
# Requirements 5.1, 10.2 — the KB carries the industry=airline resource tag
# --------------------------------------------------------------------------- #

def test_knowledge_base_tags_include_industry_airline(template: Template):
    kbs = template.find_resources("AWS::Wisdom::KnowledgeBase")
    (kb,) = kbs.values()
    tags = kb["Properties"].get("Tags", []) or []
    tag_pairs = {(t["Key"], t["Value"]) for t in tags}
    assert ("industry", "airline") in tag_pairs, (
        f"KB Tags must include industry=airline; found {sorted(tag_pairs)}"
    )


# --------------------------------------------------------------------------- #
# Requirement 5.5 — seven topics × es/pt/en, exactly one file each (21 total)
# --------------------------------------------------------------------------- #

def test_each_topic_has_exactly_one_file_per_language():
    for lang in sorted(EXPECTED_LANGS):
        lang_dir = ENTRIES_DIR / lang
        assert lang_dir.is_dir(), f"missing language directory {lang_dir}"
        txt_files = sorted(p.name for p in lang_dir.glob("*.txt"))
        expected = sorted(f"{topic}.txt" for topic in EXPECTED_TOPICS)
        assert txt_files == expected, (
            f"language {lang!r} topic coverage mismatch: "
            f"expected {expected}, found {txt_files}"
        )


def test_total_file_count_is_twenty_one():
    all_txt = list(ENTRIES_DIR.glob("*/*.txt"))
    assert len(all_txt) == EXPECTED_FILE_COUNT, (
        f"expected {EXPECTED_FILE_COUNT} KB files, found {len(all_txt)}"
    )


# --------------------------------------------------------------------------- #
# Requirement 10.2 — manifest declares the base tag industry=airline
# --------------------------------------------------------------------------- #

def test_manifest_declares_industry_airline_resource_tag(manifest: dict):
    assert manifest.get("resourceTags") == {"industry": "airline"}, (
        f"manifest resourceTags must equal {{'industry': 'airline'}}; "
        f"found {manifest.get('resourceTags')!r}"
    )


# --------------------------------------------------------------------------- #
# Requirement 5.9 — one-to-one correspondence between manifest entries & files
# --------------------------------------------------------------------------- #

def test_manifest_has_twenty_one_entries(manifest: dict):
    entries = manifest.get("entries", [])
    assert len(entries) == EXPECTED_FILE_COUNT, (
        f"expected {EXPECTED_FILE_COUNT} manifest entries, found {len(entries)}"
    )


def test_manifest_entries_have_required_nonempty_fields(manifest: dict):
    for entry in manifest["entries"]:
        for field in ("title", "file", "contentType", "tags"):
            assert entry.get(field), (
                f"manifest entry {entry.get('name')!r} has empty/missing {field!r}"
            )


def test_manifest_entries_map_one_to_one_to_files(manifest: dict):
    # Every manifest entry points at an on-disk file (no dangling entry) ...
    manifest_files = set()
    for entry in manifest["entries"]:
        rel = entry["file"]
        manifest_files.add(rel)
        assert (KB_ROOT / rel).is_file(), (
            f"manifest entry {entry.get('name')!r} references missing file {rel}"
        )

    # ... and every on-disk file is referenced by exactly one manifest entry
    # (no omitted document). Compare the file-path sets both ways.
    on_disk = {
        f"entries/{p.parent.name}/{p.name}"
        for p in ENTRIES_DIR.glob("*/*.txt")
    }
    assert manifest_files == on_disk, (
        "manifest ⇄ file mismatch: "
        f"only-in-manifest={sorted(manifest_files - on_disk)}, "
        f"only-on-disk={sorted(on_disk - manifest_files)}"
    )
    # one-to-one implies equal counts (guards a duplicate manifest 'file')
    assert len(manifest_files) == EXPECTED_FILE_COUNT
    assert len(manifest["entries"]) == len(manifest_files), (
        "duplicate 'file' paths in manifest entries"
    )
