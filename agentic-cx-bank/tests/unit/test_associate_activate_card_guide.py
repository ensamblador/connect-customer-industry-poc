"""
tests/unit/test_associate_activate_card_guide.py — mock-based unit tests for the
post-deploy guide-association script (``knowledge_bases/associate_activate_card_guide.py``).

The script binds the ``Activar tarjeta`` guide contact flow to its
``activar-tarjeta`` Q in Connect knowledge-base content via an
``AMAZON_CONNECT_GUIDE`` content association. It is pure orchestration over two
boto3 clients (``qconnect`` and ``connect``), so every test here stubs those
clients with in-memory fakes (objects exposing the needed methods / paginators)
— no real AWS is ever contacted.

Coverage maps to Requirement 11 acceptance criteria:

  * flow-name resolution via ``connect:ListContactFlows`` — found -> ARN,
    not-found -> error / no changes                                (11.4, 11.5)
  * case-insensitive substring content matching                    (11.2)
  * exactly-one-match required — zero -> error, >1 -> error,
    exactly one -> proceed                                         (11.3, 11.1)
  * idempotent ``_associate`` branches — already-points-at-flow ->
    'exists' (no mutation); points-elsewhere -> delete+create ->
    'replaced'; absent -> create -> 'created'                      (11.6, 11.7, 11.1)
  * ``--dry-run`` reports would-create / would-replace / exists and
    invokes NO create or delete operation                          (11.8)

Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8
"""

from __future__ import annotations

import pytest

from knowledge_bases import associate_activate_card_guide as script

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
# _resolve_flow_arn — Requirements 11.4, 11.5
# --------------------------------------------------------------------------- #
def test_resolve_flow_arn_explicit_short_circuits():
    # An explicit --flow-arn wins without calling the connect client at all.
    fake = FakeConnect(flow_pages=[])
    got = script._resolve_flow_arn(fake, "i-1", "Activar tarjeta", FLOW_ARN)
    assert got == FLOW_ARN
    assert fake.calls == [], "explicit ARN must not trigger a ListContactFlows call"


def test_resolve_flow_arn_found_by_name():
    pages = [
        {"ContactFlowSummaryList": [{"Name": "Otro flujo", "Arn": OTHER_ARN}]},
        {"ContactFlowSummaryList": [{"Name": "Activar tarjeta", "Arn": FLOW_ARN}]},
    ]
    fake = FakeConnect(flow_pages=pages)
    got = script._resolve_flow_arn(fake, "i-1", "Activar tarjeta", None)
    assert got == FLOW_ARN


def test_resolve_flow_arn_not_found_errors_no_changes():
    pages = [{"ContactFlowSummaryList": [{"Name": "Otro flujo", "Arn": OTHER_ARN}]}]
    fake = FakeConnect(flow_pages=pages)
    with pytest.raises(SystemExit):
        script._resolve_flow_arn(fake, "i-1", "Activar tarjeta", None)


def test_resolve_flow_arn_no_instance_errors():
    fake = FakeConnect(flow_pages=[])
    with pytest.raises(SystemExit):
        script._resolve_flow_arn(fake, "", "Activar tarjeta", None)


# --------------------------------------------------------------------------- #
# _list_card_guide_contents — Requirement 11.2 (case-insensitive substring)
# --------------------------------------------------------------------------- #
def test_list_contents_matches_case_insensitive_substring_on_title_or_name():
    pages = [
        {
            "contentSummaries": [
                {"contentId": "c1", "title": "Guia ACTIVAR-TARJETA es", "name": "x"},
                {"contentId": "c2", "title": "Comisiones", "name": "comisiones"},
                {"contentId": "c3", "title": "", "name": "activar-tarjeta-pt"},
            ]
        }
    ]
    qc = FakeQConnect(content_pages=pages)
    out = script._list_card_guide_contents(qc, "kb-1", "activar-tarjeta")
    ids = {item["contentId"] for item in out}
    assert ids == {"c1", "c3"}, "match on title OR name, case-insensitive"


def test_list_contents_no_match_returns_empty():
    pages = [{"contentSummaries": [{"contentId": "c2", "title": "Comisiones"}]}]
    qc = FakeQConnect(content_pages=pages)
    assert script._list_card_guide_contents(qc, "kb-1", "activar-tarjeta") == []


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
# _associate — idempotent branches — Requirements 11.1, 11.6, 11.7
# --------------------------------------------------------------------------- #
def test_associate_exists_leaves_unchanged():
    # Existing GUIDE association already points at the target flow.
    assoc_pages = [{"contentAssociationSummaries": [_guide_summary("a1", FLOW_ARN)]}]
    qc = FakeQConnect(assoc_pages=assoc_pages)
    status = script._associate(qc, "kb-1", "c1", FLOW_ARN, dry_run=False)
    assert status == "exists"
    assert qc.created == [] and qc.deleted == [], "no mutation when already correct"


def test_associate_replaces_when_pointing_elsewhere():
    # Existing association points at a DIFFERENT flow -> delete + recreate.
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
# _associate dry-run — Requirement 11.8 (no mutating calls)
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
# main() — end-to-end with a stubbed boto3 Session. Requirements 11.1, 11.3, 11.8
# --------------------------------------------------------------------------- #
class FakeSession:
    """Returns preset fake clients keyed by service name from ``client(...)``."""

    def __init__(self, clients):
        self._clients = clients

    def client(self, name, region_name=None):
        return self._clients[name]


def _run_main(monkeypatch, qc, argv):
    """Invoke script.main() with boto3.Session and sys.argv stubbed.

    A fake ``ssm`` and ``connect`` client are supplied but the test argv passes
    --kb-id and --flow-arn so neither lookup client is exercised (isolating the
    content-match + associate logic under test)."""
    session = FakeSession(
        {"qconnect": qc, "connect": FakeConnect([]), "ssm": object()}
    )
    monkeypatch.setattr(script.boto3, "Session", lambda *a, **k: session)
    monkeypatch.setattr(script.sys, "argv", ["prog", *argv])
    return script.main()


def _one_match_pages():
    return [{"contentSummaries": [{"contentId": "c1", "title": "activar-tarjeta es"}]}]


def test_main_exactly_one_match_creates(monkeypatch, capsys):
    qc = FakeQConnect(
        content_pages=_one_match_pages(),
        assoc_pages=[{"contentAssociationSummaries": []}],
    )
    rc = _run_main(
        monkeypatch, qc,
        ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "activar-tarjeta"],
    )
    assert rc == 0
    assert len(qc.created) == 1, "exactly one match must proceed to create"
    out = capsys.readouterr().out
    assert "created" in out


def test_main_zero_matches_errors_no_changes(monkeypatch):
    qc = FakeQConnect(
        content_pages=[{"contentSummaries": [{"contentId": "cX", "title": "otro"}]}],
    )
    with pytest.raises(SystemExit):
        _run_main(
            monkeypatch, qc,
            ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "activar-tarjeta"],
        )
    assert qc.created == [] and qc.deleted == []


def test_main_multiple_matches_errors_no_changes(monkeypatch):
    pages = [
        {
            "contentSummaries": [
                {"contentId": "c1", "title": "activar-tarjeta es"},
                {"contentId": "c2", "title": "activar-tarjeta pt"},
            ]
        }
    ]
    qc = FakeQConnect(content_pages=pages)
    with pytest.raises(SystemExit):
        _run_main(
            monkeypatch, qc,
            ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "activar-tarjeta"],
        )
    assert qc.created == [] and qc.deleted == []


def test_main_dry_run_makes_no_mutating_calls(monkeypatch, capsys):
    qc = FakeQConnect(
        content_pages=_one_match_pages(),
        assoc_pages=[{"contentAssociationSummaries": []}],
    )
    rc = _run_main(
        monkeypatch, qc,
        ["--kb-id", "kb-1", "--flow-arn", FLOW_ARN, "--match", "activar-tarjeta",
         "--dry-run"],
    )
    assert rc == 0
    assert qc.created == [] and qc.deleted == [], "dry-run must not mutate"
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "would-create" in out


def test_main_flow_not_found_errors_no_changes(monkeypatch):
    # No --flow-arn: force resolution via a connect client whose flow list is
    # empty, so the flow name cannot be resolved -> SystemExit, no mutation.
    qc = FakeQConnect(content_pages=_one_match_pages())
    session = FakeSession(
        {"qconnect": qc, "connect": FakeConnect([]), "ssm": object()}
    )
    monkeypatch.setattr(script.boto3, "Session", lambda *a, **k: session)
    monkeypatch.setattr(
        script.sys, "argv",
        ["prog", "--kb-id", "kb-1", "--instance-id", "i-1",
         "--flow-name", "Activar tarjeta", "--match", "activar-tarjeta"],
    )
    with pytest.raises(SystemExit):
        script.main()
    assert qc.created == [] and qc.deleted == []
