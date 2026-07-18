"""
tests/unit/test_associate_guide.py — mock-based unit tests for the shared
post-deploy guide-association script (``knowledge_bases/associate_guide.py``).

The script binds THIS project's step-by-step guide contact flow to its guide
Q in Connect knowledge-base article(s) via ``AMAZON_CONNECT_GUIDE`` content
associations. It is pure orchestration over two boto3 clients (``qconnect`` and
``connect``), so every test here stubs those clients with in-memory fakes — no
real AWS is ever contacted.

Coverage:
  * config resolution — the flow name / match resolve from whichever guide
    constant this project's config.py defines;
  * flow-name resolution via ``connect:ListContactFlows`` — found -> ARN,
    not-found -> error / no changes;
  * case-insensitive substring content matching;
  * ALL matching content items are associated (one guide article per language),
    idempotently;
  * idempotent ``_associate`` branches — already-points-at-flow -> 'exists'
    (no mutation); points-elsewhere -> delete+create -> 'replaced'; absent ->
    create -> 'created';
  * ``--dry-run`` reports would-create / would-replace / exists and invokes NO
    create or delete operation.
"""

from __future__ import annotations

import pytest

from knowledge_bases import associate_guide as script

GUIDE = script.GUIDE  # "AMAZON_CONNECT_GUIDE"


# --------------------------------------------------------------------------- #
# Fakes — minimal in-memory stand-ins for the boto3 qconnect / connect clients.
# --------------------------------------------------------------------------- #
class _FakePaginator:
    """Mimics a boto3 paginator: ``paginate(**kwargs)`` yields preset pages."""

    def __init__(self, pages):
        self._pages = pages

    def paginate(self, **_kwargs):
        yield from self._pages


class FakeConnect:
    """Stub for the ``connect`` client — only ``list_contact_flows`` paginator."""

    def __init__(self, flow_pages):
        self._flow_pages = flow_pages
        self.calls = []

    def get_paginator(self, name):
        assert name == "list_contact_flows", name
        self.calls.append(name)
        return _FakePaginator(self._flow_pages)


class FakeQConnect:
    """Stub for the ``qconnect`` client.

    * ``list_contents`` paginator yields ``content_pages``.
    * ``list_content_associations`` yields ``assoc_pages`` (a list of response
      dicts), honoring ``nextToken`` chaining.
    * ``create_content_association`` / ``delete_content_association`` record
      their calls and (for create) echo back the requested flowId so the
      script's post-create verification passes.
    """

    def __init__(self, content_pages=None, assoc_pages=None):
        self._content_pages = content_pages or []
        self._assoc_pages = assoc_pages or [{"contentAssociationSummaries": []}]
        self.created = []
        self.deleted = []

    # --- content listing ---------------------------------------------------
    def get_paginator(self, name):
        assert name == "list_contents", name
        return _FakePaginator(self._content_pages)

    # --- existing-association listing (manual pagination in the script) -----
    def list_content_associations(self, **kwargs):
        token = kwargs.get("nextToken")
        idx = int(token) if token is not None else 0
        return self._assoc_pages[idx]

    # --- mutations ----------------------------------------------------------
    def create_content_association(self, **kwargs):
        self.created.append(kwargs)
        flow_id = kwargs["association"]["amazonConnectGuideAssociation"]["flowId"]
        return {
            "contentAssociation": {
                "contentAssociationId": "new-assoc-id",
                "associationData": {
                    "amazonConnectGuideAssociation": {"flowId": flow_id}
                },
            }
        }

    def delete_content_association(self, **kwargs):
        self.deleted.append(kwargs)


def _guide_summary(assoc_id: str, flow_id: str) -> dict:
    """Build an AMAZON_CONNECT_GUIDE association summary as the API returns it."""
    return {
        "associationType": GUIDE,
        "contentAssociationId": assoc_id,
        "associationData": {"amazonConnectGuideAssociation": {"flowId": flow_id}},
    }


FLOW_ARN = "arn:aws:connect:us-east-1:111122223333:instance/i-1/contact-flow/cf-1"
OTHER_ARN = "arn:aws:connect:us-east-1:111122223333:instance/i-1/contact-flow/cf-2"


# --------------------------------------------------------------------------- #
# Config resolution — the shared script reads THIS project's guide constants.
# --------------------------------------------------------------------------- #
def test_config_resolution_returns_nonempty_flow_and_match():
    assert script.guide_flow_name(), "a guide flow name must resolve from config"
    assert script.guide_content_match(), "a guide content match must resolve from config"


# --------------------------------------------------------------------------- #
# _resolve_flow_arn
# --------------------------------------------------------------------------- #
def test_resolve_flow_arn_explicit_short_circuits():
    fake = FakeConnect(flow_pages=[])
    got = script._resolve_flow_arn(fake, "i-1", "Guide flow", FLOW_ARN)
    assert got == FLOW_ARN
    assert fake.calls == [], "explicit ARN must not trigger a ListContactFlows call"


def test_resolve_flow_arn_found_by_name():
    pages = [
        {"ContactFlowSummaryList": [{"Name": "Otro flujo", "Arn": OTHER_ARN}]},
        {"ContactFlowSummaryList": [{"Name": "Guide flow", "Arn": FLOW_ARN}]},
    ]
    fake = FakeConnect(flow_pages=pages)
    got = script._resolve_flow_arn(fake, "i-1", "Guide flow", None)
    assert got == FLOW_ARN


def test_resolve_flow_arn_not_found_errors_no_changes():
    pages = [{"ContactFlowSummaryList": [{"Name": "Otro flujo", "Arn": OTHER_ARN}]}]
    fake = FakeConnect(flow_pages=pages)
    with pytest.raises(SystemExit):
        script._resolve_flow_arn(fake, "i-1", "Guide flow", None)


def test_resolve_flow_arn_no_instance_errors():
    fake = FakeConnect(flow_pages=[])
    with pytest.raises(SystemExit):
        script._resolve_flow_arn(fake, "", "Guide flow", None)


# --------------------------------------------------------------------------- #
# _list_guide_contents — case-insensitive substring on title OR name
# --------------------------------------------------------------------------- #
def test_list_contents_matches_case_insensitive_substring_on_title_or_name():
    pages = [
        {
            "contentSummaries": [
                {"contentId": "c1", "title": "Guia GUIDE es", "name": "x"},
                {"contentId": "c2", "title": "Otro", "name": "otro"},
                {"contentId": "c3", "title": "", "name": "guide-pt"},
            ]
        }
    ]
    qc = FakeQConnect(content_pages=pages)
    out = script._list_guide_contents(qc, "kb-1", "guide")
    ids = {item["contentId"] for item in out}
    assert ids == {"c1", "c3"}, "match on title OR name, case-insensitive"


def test_list_contents_no_match_returns_empty():
    pages = [{"contentSummaries": [{"contentId": "c2", "title": "Otro"}]}]
    qc = FakeQConnect(content_pages=pages)
    assert script._list_guide_contents(qc, "kb-1", "guide") == []


# --------------------------------------------------------------------------- #
# _guide_flow_id — pure helper
# --------------------------------------------------------------------------- #
def test_guide_flow_id_extracts_flow_id():
    assert script._guide_flow_id(_guide_summary("a", FLOW_ARN)) == FLOW_ARN


def test_guide_flow_id_none_safe():
    assert script._guide_flow_id(None) is None
    assert script._guide_flow_id({}) is None


# --------------------------------------------------------------------------- #
# _existing_guide_association — paginates until a GUIDE summary is found
# --------------------------------------------------------------------------- #
def test_existing_guide_association_found_across_pages():
    assoc_pages = [
        {"contentAssociationSummaries": [{"associationType": "OTHER"}], "nextToken": "1"},
        {"contentAssociationSummaries": [_guide_summary("a1", FLOW_ARN)]},
    ]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    found = script._existing_guide_association(qc, "kb-1", "c1")
    assert found is not None
    assert found["contentAssociationId"] == "a1"


def test_existing_guide_association_absent_returns_none():
    assoc_pages = [{"contentAssociationSummaries": [{"associationType": "OTHER"}]}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    assert script._existing_guide_association(qc, "kb-1", "c1") is None


# --------------------------------------------------------------------------- #
# _associate — idempotent branches
# --------------------------------------------------------------------------- #
def test_associate_exists_leaves_unchanged():
    assoc_pages = [{"contentAssociationSummaries": [_guide_summary("a1", FLOW_ARN)]}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=False)
    assert status == "exists"
    assert qc.created == [] and qc.deleted == [], "no mutation when already correct"


def test_associate_replaces_when_pointing_elsewhere():
    assoc_pages = [{"contentAssociationSummaries": [_guide_summary("a1", OTHER_ARN)]}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=False)
    assert status == "replaced"
    assert len(qc.deleted) == 1
    assert qc.deleted[0]["contentAssociationId"] == "a1"
    assert len(qc.created) == 1
    assert (
        qc.created[0]["association"]["amazonConnectGuideAssociation"]["flowId"]
        == FLOW_ARN
    )


def test_associate_creates_when_absent():
    assoc_pages = [{"contentAssociationSummaries": []}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=False)
    assert status == "created"
    assert qc.deleted == []
    assert len(qc.created) == 1
    assert qc.created[0]["associationType"] == GUIDE


# --------------------------------------------------------------------------- #
# _associate dry-run — no mutating calls
# --------------------------------------------------------------------------- #
def test_associate_dry_run_would_create_makes_no_calls():
    qc = FakeQConnect(assoc_pages=[{"contentAssociationSummaries": []}])
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=True)
    assert status == "would-create"
    assert qc.created == [] and qc.deleted == []


def test_associate_dry_run_would_replace_makes_no_calls():
    assoc_pages = [{"contentAssociationSummaries": [_guide_summary("a1", OTHER_ARN)]}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=True)
    assert status == "would-replace"
    assert qc.created == [] and qc.deleted == []


def test_associate_dry_run_exists_makes_no_calls():
    assoc_pages = [{"contentAssociationSummaries": [_guide_summary("a1", FLOW_ARN)]}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=True)
    assert status == "exists"
    assert qc.created == [] and qc.deleted == []


# --------------------------------------------------------------------------- #
# main() — end-to-end with a stubbed boto3 Session.
# --------------------------------------------------------------------------- #
class FakeSession:
    """Returns preset fake clients keyed by service name from ``client(...)``."""

    def __init__(self, clients):
        self._clients = clients

    def client(self, name, region_name=None):
        return self._clients[name]


def _run_main(monkeypatch, qc, argv):
    """Invoke script.main() with boto3.Session and sys.argv stubbed."""
    session = FakeSession(
        {"qconnect": qc, "connect": FakeConnect([]), "ssm": object()}
    )
    monkeypatch.setattr(script.boto3, "Session", lambda *a, **k: session)
    monkeypatch.setattr(script.sys, "argv", ["prog", *argv])
    return script.main()


def _one_match_pages():
    return [{"contentSummaries": [{"contentId": "c1", "title": "guide es"}]}]


def test_main_one_match_creates(monkeypatch, capsys):
    qc = FakeQConnect(
        content_pages=_one_match_pages(),
        assoc_pages=[{"contentAssociationSummaries": []}],
    )
    rc = _run_main(
        monkeypatch, qc,
        ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "guide"],
    )
    assert rc == 0
    assert len(qc.created) == 1
    out = capsys.readouterr().out
    assert "created" in out


def test_main_multiple_matches_associates_all(monkeypatch, capsys):
    # The guide article exists once per language: ALL matches must be associated.
    pages = [
        {
            "contentSummaries": [
                {"contentId": "c1", "title": "guide es"},
                {"contentId": "c2", "title": "guide pt"},
                {"contentId": "c3", "title": "guide en"},
            ]
        }
    ]
    qc = FakeQConnect(
        content_pages=pages, assoc_pages=[{"contentAssociationSummaries": []}]
    )
    rc = _run_main(
        monkeypatch, qc,
        ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "guide"],
    )
    assert rc == 0
    assert len(qc.created) == 3, "every language copy of the guide must be associated"
    out = capsys.readouterr().out
    assert "3 guide content item(s)" in out


def test_main_zero_matches_errors_no_changes(monkeypatch):
    qc = FakeQConnect(
        content_pages=[{"contentSummaries": [{"contentId": "cX", "title": "otro"}]}],
    )
    with pytest.raises(SystemExit):
        _run_main(
            monkeypatch, qc,
            ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "guide"],
        )
    assert qc.created == [] and qc.deleted == []


def test_main_dry_run_makes_no_mutating_calls(monkeypatch, capsys):
    qc = FakeQConnect(
        content_pages=_one_match_pages(),
        assoc_pages=[{"contentAssociationSummaries": []}],
    )
    rc = _run_main(
        monkeypatch, qc,
        ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "guide", "--dry-run"],
    )
    assert rc == 0
    assert qc.created == [] and qc.deleted == [], "dry-run must not mutate"
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "would-create" in out


def test_main_flow_not_found_errors_no_changes(monkeypatch):
    qc = FakeQConnect(content_pages=_one_match_pages())
    session = FakeSession(
        {"qconnect": qc, "connect": FakeConnect([]), "ssm": object()}
    )
    monkeypatch.setattr(script.boto3, "Session", lambda *a, **k: session)
    monkeypatch.setattr(
        script.sys, "argv",
        ["prog", "--kb-id", "kb-1", "--instance-id", "i-1",
         "--flow-name", "Guide flow", "--match", "guide"],
    )
    with pytest.raises(SystemExit):
        script.main()
    assert qc.created == [] and qc.deleted == []
