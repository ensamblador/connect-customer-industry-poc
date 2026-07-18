"""
tests/unit/test_no_telco_leakage.py — repo-wide no-telco-leakage guard.

Final validation that the banking re-theme left no telecommunications token
anywhere a customer-facing banking artifact, configuration value, or
synthesized resource name could carry it. A single ``telco`` substring (in any
letter casing) in shipping source is a leak.

The guard has three independent parts:

  1. Shipping-asset file scan (Requirements 2.1, 2.3, 12.6) — walk the SHIPPING
     source tree of ``agentic-cx-bank/`` (Python, JSON, YAML, txt, md, js, html,
     css, config) and assert no case-insensitive ``telco`` substring appears in
     any file. Banking data, Lambda handlers, OpenAPI, KB documents, flow/view
     JSON, prompt YAML, the website source, and the README are all in scope.

  2. Config banking-value scan (Requirements 2.1, 2.3) — import ``config`` and
     assert every configured banking value (resource names, table names, view /
     flow / bot / agent identifiers, paths, tags) is free of any ``telco``
     substring.

  3. Synthesized-template scan (Requirements 2.1, 2.3) — synthesize each of the
     six in-scope ``CX-BANCO-*`` stacks and assert no ``telco`` substring
     survives in the rendered CloudFormation (resource names, properties, tags).

Scope / exclusions:
  * ``tests/`` is excluded — the template/structure-preservation suites
    (``test_support_template.py``, ``test_agents_template.py``,
    ``test_flows_template.py``, this file, …) legitimately reference the telco
    source project (``../agentic-cx-telco/…``) and the literal ``telco`` for
    content-only structure-preservation diffs. Those are test-harness
    references, not banking-asset leakage.
  * Build / vendored / cache directories are pruned: ``.venv/``,
    ``node_modules/``, ``cdk.out/``, ``dist/`` (website build output),
    ``__pycache__/``, ``.git/``, ``.pytest_cache/``.
  * ``config.py`` carries no telco token and is scanned like any other shipping
    file — every resource name is industry-prefixed, so a sibling collision is
    structurally impossible and no name-mirroring guard is needed.
  * The only allowed cross-project dependency is the external ``/flows/init/es``
    module reference resolved from SSM — it carries no telco token, so in effect
    zero telco tokens remain anywhere in the banking project source.

Validates: Requirements 2.1, 2.3, 12.6
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest
import aws_cdk as cdk
from aws_cdk.assertions import Template

import config
from agentic_cx_bank.mcp_stack import McpStack
from agentic_cx_bank.knowledge_base_stack import KnowledgeBaseStack
from agentic_cx_bank.connect_support_stack import ConnectSupportStack
from agentic_cx_bank.ai_agents_stack import AiAgentsStack
from agentic_cx_bank.contact_flows_stack import ContactFlowsStack
from agentic_cx_bank.website_stack import WebsiteStack

# The forbidden token — matched case-insensitively, so it also catches
# ``TELCO`` and ``Telco``.
TELCO = "telco"

# tests/unit/<this file> -> parents[2] == agentic-cx-bank/.
BANK_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Shipping-asset scope
# --------------------------------------------------------------------------- #

# Top-level shipping files (NOT tests/).
SHIPPING_FILES = ["app.py", "config.py", "README.md", "cdk.json"]

# Shipping source directories. ``tests`` is deliberately absent.
SHIPPING_DIRS = [
    "agentic_cx_bank",
    "lambdas",
    "apis",
    "agent_core",
    "databases",
    "knowledge_bases",
    "connect",
    "connect_ai_agents",
    "flows",
    "views",
    "webhosting",
    "shared",
    "website",  # website build output (dist/) + node_modules/ are pruned below
]

# Directory names pruned anywhere in the walk (build output / caches / vendored).
EXCLUDED_DIR_NAMES = {
    ".venv",
    "node_modules",
    "cdk.out",
    "dist",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    ".idea",
    ".vscode",
}

# Binary asset extensions with no meaningful text to scan (images / fonts / …).
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".zip", ".gz", ".tar", ".mp4", ".mp3", ".mov", ".wav",
    ".pyc",
}

def _is_pruned(path: Path) -> bool:
    """True if any path component is an excluded directory name."""
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def _iter_shipping_files() -> Iterator[Path]:
    """Yield every in-scope shipping source file, pruning build/cache dirs."""
    seen: set[Path] = set()

    for name in SHIPPING_FILES:
        f = BANK_ROOT / name
        if f.is_file() and f not in seen:
            seen.add(f)
            yield f

    for dirname in SHIPPING_DIRS:
        root = BANK_ROOT / dirname
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if _is_pruned(path):
                continue
            if path.suffix.lower() in SKIP_EXTENSIONS:
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _telco_line_numbers(text: str) -> list[int]:
    """1-based line numbers on which the telco token appears (case-insensitive)."""
    return [
        i + 1
        for i, line in enumerate(text.splitlines())
        if TELCO in line.lower()
    ]


# --------------------------------------------------------------------------- #
# Part 1 — shipping-asset file scan (Requirements 2.1, 2.3, 12.6)
# --------------------------------------------------------------------------- #

def test_shipping_scope_actually_scans_files():
    """Sanity guard: the walk must find a non-trivial set of files, otherwise a
    scope regression could make the leakage scan silently vacuous."""
    files = list(_iter_shipping_files())
    assert len(files) >= 20, (
        f"expected the shipping scan to cover many files, found only {len(files)} "
        "— the scope may have regressed"
    )
    # A few representative artifacts that must be in scope.
    covered = {p.relative_to(BANK_ROOT).as_posix() for p in files}
    assert "app.py" in covered
    assert "README.md" in covered
    assert any(p.startswith("flows/") for p in covered)
    assert any(p.startswith("views/") for p in covered)
    assert any(p.startswith("knowledge_bases/bank/") for p in covered)


def test_no_telco_token_in_shipping_assets():
    """No banking asset (data, code, OpenAPI, KB docs, flow/view JSON, prompt
    YAML, website source, README) may contain a telco substring."""
    offenders: list[str] = []
    for path in _iter_shipping_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # Undeclared-binary or unreadable file — nothing textual to leak.
            continue
        if TELCO in text.lower():
            rel = path.relative_to(BANK_ROOT).as_posix()
            offenders.append(f"{rel} (lines {_telco_line_numbers(text)})")

    assert not offenders, (
        "telco token leaked into banking shipping assets:\n  "
        + "\n  ".join(sorted(offenders))
    )


# --------------------------------------------------------------------------- #
# Part 2 — config banking-value scan (Requirements 2.1, 2.3)
# --------------------------------------------------------------------------- #

def _strings_in(value) -> Iterator[str]:
    """Recursively yield every string contained in a config value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, val in value.items():
            yield from _strings_in(key)
            yield from _strings_in(val)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _strings_in(item)


def test_config_banking_values_have_no_telco():
    """Every configured banking value — resource names, table names, view/flow/
    bot/agent identifiers, paths, tags — is free of a telco substring."""
    offenders: list[str] = []
    for name in dir(config):
        if name.startswith("_"):
            continue
        value = getattr(config, name)
        # ``_strings_in`` only descends str/dict/list/tuple/set values, so
        # imported modules (e.g. the ``os`` import) and scalars yield nothing.
        for s in _strings_in(value):
            if TELCO in s.lower():
                offenders.append(f"config.{name} -> {s!r}")

    assert not offenders, (
        "telco token found in configured banking values:\n  "
        + "\n  ".join(sorted(offenders))
    )


# --------------------------------------------------------------------------- #
# Part 3 — synthesized-template scan (Requirements 2.1, 2.3)
# --------------------------------------------------------------------------- #

STACK_FACTORIES = {
    "CX-BANCO-MCP": McpStack,
    "CX-BANCO-KB": KnowledgeBaseStack,
    "CX-BANCO-CONNECT-SUPPORT": ConnectSupportStack,
    "CX-BANCO-AGENTS": AiAgentsStack,
    "CX-BANCO-FLOWS": ContactFlowsStack,
    "CX-BANCO-WEBSITE": WebsiteStack,
}


@pytest.mark.parametrize("stack_name", sorted(STACK_FACTORIES))
def test_no_telco_token_in_synthesized_template(stack_name: str):
    """No telco substring survives in any in-scope synthesized template
    (resource names, properties, tags)."""
    app = cdk.App()
    stack = STACK_FACTORIES[stack_name](app, stack_name)
    rendered = json.dumps(Template.from_stack(stack).to_json())
    assert TELCO not in rendered.lower(), (
        f"found a 'telco' substring in the synthesized {stack_name} template"
    )
