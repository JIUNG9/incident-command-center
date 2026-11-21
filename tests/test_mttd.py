"""MTTD layers: watchlist parsing, SigNoz reconcile, similarity ranking.

The network is replaced with httpx.MockTransport, so the request shapes the
code builds are asserted and the code under test runs unmodified.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from vigil.mttd.rule_layer import RuleLayer
from vigil.mttd.similarity_layer import SimilarityLayer

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> Callable[[Handler], list[httpx.Request]]:
    """Route every httpx.Client in the code under test through `handler`."""
    real_client = httpx.Client

    def install(handler: Handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        def factory(*args: Any, **kwargs: Any) -> httpx.Client:
            kwargs["transport"] = httpx.MockTransport(recording)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", factory)
        return seen

    return install


# --- rule layer: load_rules ------------------------------------------------


def test_load_rules_applies_defaults_and_maps_for_to_duration(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(
        "- alert: HighCPU\n  expr: cpu > 0.9\n  for: 10m\n  severity: critical\n"
        "  owner: '@sre'\n  runbooks: [rb/cpu.md]\n  description: cpu\n"
        "- alert: Minimal\n  expr: up == 0\n",
        encoding="utf-8",
    )
    full, minimal = RuleLayer(tmp_path).load_rules()
    assert (full.name, full.duration, full.severity, full.owner) == (
        "HighCPU", "10m", "critical", "@sre",
    )
    assert full.runbooks == ["rb/cpu.md"]
    assert (minimal.duration, minimal.severity, minimal.owner) == ("5m", "medium", "@oncall")
    assert minimal.runbooks == [] and minimal.description == ""


def test_load_rules_skips_invalid_yaml_and_keeps_the_good_files(tmp_path: Path) -> None:
    (tmp_path / "a_bad.yaml").write_text("- alert: [unclosed\n", encoding="utf-8")
    (tmp_path / "b_good.yaml").write_text("- alert: Ok\n  expr: x\n", encoding="utf-8")
    (tmp_path / "c_empty.yaml").write_text("", encoding="utf-8")
    (tmp_path / "ignored.yml").write_text("- alert: WrongExtension\n", encoding="utf-8")
    assert [r.name for r in RuleLayer(tmp_path).load_rules()] == ["Ok"]


def test_load_rules_missing_directory_is_empty(tmp_path: Path) -> None:
    assert RuleLayer(tmp_path / "nope").load_rules() == []


def test_load_rules_reads_files_in_name_order(tmp_path: Path) -> None:
    (tmp_path / "z.yaml").write_text("- alert: Z\n", encoding="utf-8")
    (tmp_path / "a.yaml").write_text("- alert: A\n", encoding="utf-8")
    assert [r.name for r in RuleLayer(tmp_path).load_rules()] == ["A", "Z"]


# --- rule layer: sync_to_signoz --------------------------------------------


def _rules(tmp_path: Path, *names: str) -> list:
    body = "".join(f"- alert: {n}\n  expr: e_{n}\n  runbooks: [a, b]\n" for n in names)
    (tmp_path / "w.yaml").write_text(body, encoding="utf-8")
    return RuleLayer(tmp_path).load_rules()


def test_sync_without_credentials_makes_no_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.delenv("SIGNOZ_API_URL", raising=False)
    monkeypatch.delenv("SIGNOZ_API_TOKEN", raising=False)
    seen = fake_http(lambda r: httpx.Response(500))
    out = RuleLayer(tmp_path).sync_to_signoz(_rules(tmp_path, "A"))
    assert out == {"added": 0, "updated": 0, "removed": 0, "skipped": True}
    assert seen == []


def test_sync_adds_updates_and_removes_only_rules_it_owns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.setenv("SIGNOZ_API_URL", "http://signoz.test")
    monkeypatch.setenv("SIGNOZ_API_TOKEN", "t0ken")
    existing = {"data": {"rules": [
        {"alert": "Keep", "id": "1", "source": "vigil"},
        {"alert": "StaleOurs", "id": "2", "source": "vigil"},
        {"alert": "StaleTheirs", "id": "3", "source": "someone-else"},
    ]}}

    def handler(r: httpx.Request) -> httpx.Response:
        if r.method == "GET":
            return httpx.Response(200, json=existing)
        return httpx.Response(204 if r.method == "DELETE" else 200)

    seen = fake_http(handler)
    out = RuleLayer(tmp_path).sync_to_signoz(_rules(tmp_path, "Keep", "New"))

    assert out == {"added": 1, "updated": 1, "removed": 1, "skipped": False}
    calls = {(r.method, r.url.path) for r in seen}
    assert ("POST", "/api/v1/rules") in calls
    assert ("PUT", "/api/v1/rules/1") in calls
    assert ("DELETE", "/api/v1/rules/2") in calls
    assert ("DELETE", "/api/v1/rules/3") not in calls  # not ours: never deleted
    assert all(r.headers["authorization"] == "Bearer t0ken" for r in seen)

    posted = json.loads(next(r for r in seen if r.method == "POST").content)
    assert posted["alert"] == "New" and posted["for"] == "5m"
    assert posted["labels"] == {"severity": "medium", "owner": "@oncall"}
    assert posted["annotations"]["runbooks"] == "a, b"


def test_sync_does_not_count_a_rejected_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.setenv("SIGNOZ_API_URL", "http://signoz.test")
    monkeypatch.setenv("SIGNOZ_API_TOKEN", "t")

    def handler(r: httpx.Request) -> httpx.Response:
        if r.method == "GET":
            return httpx.Response(200, json={"data": {"rules": []}})
        return httpx.Response(400)

    fake_http(handler)
    out = RuleLayer(tmp_path).sync_to_signoz(_rules(tmp_path, "New"))
    assert out["added"] == 0


def test_sync_raises_when_listing_rules_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.setenv("SIGNOZ_API_URL", "http://signoz.test")
    monkeypatch.setenv("SIGNOZ_API_TOKEN", "t")
    fake_http(lambda r: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        RuleLayer(tmp_path).sync_to_signoz(_rules(tmp_path, "A"))


# --- similarity layer ------------------------------------------------------


def _hit(path: str, score: float, text: str = "") -> dict:
    return {"score": score, "payload": {"path": path, "text": text}}


def _similarity_http(hits: list[dict], fake_http) -> list[httpx.Request]:
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/api/embeddings":
            return httpx.Response(200, json={"embedding": [0.1, 0.2]})
        return httpx.Response(200, json={"result": hits})

    return fake_http(handler)


def test_find_similar_dedupes_by_document_and_applies_floor_and_top_k(
    monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.delenv("MTTD_INCIDENT_PROJECTS", raising=False)
    hits = [
        _hit("archive/jira/INFRA/INFRA-1.md", 0.91, "# INFRA-1 — RDS CPU\nbody"),
        _hit("archive/jira/INFRA/INFRA-1.md", 0.90),  # second chunk of the same doc
        _hit("archive/jira/INCD/INCD-2.md", 0.75),
        _hit("archive/jira/INFRA/INFRA-3.md", 0.59),  # under the 0.6 floor
        _hit("archive/jira/INFRA/INFRA-4.md", 0.58),
    ]
    _similarity_http(hits, fake_http)
    out = SimilarityLayer().find_similar("rds cpu high", top_k=3)
    assert [(i.key, i.score) for i in out] == [("INFRA-1", 0.91), ("INCD-2", 0.75)]
    assert out[0].title == "RDS CPU"
    assert out[1].title == "INCD-2"  # no heading in the chunk: falls back to the key

    capped = SimilarityLayer().find_similar("rds cpu high", top_k=1)
    assert [i.key for i in capped] == ["INFRA-1"]


def test_find_similar_floor_is_a_parameter(monkeypatch: pytest.MonkeyPatch, fake_http) -> None:
    _similarity_http([_hit("archive/jira/INFRA/INFRA-3.md", 0.59)], fake_http)
    assert SimilarityLayer().find_similar("x", score_floor=0.5)[0].key == "INFRA-3"
    assert SimilarityLayer().find_similar("x", score_floor=0.6) == []


def test_find_similar_scopes_the_search_to_incident_projects(
    monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.setenv("MTTD_INCIDENT_PROJECTS", " OPS , SEC ,")
    seen = _similarity_http([], fake_http)
    SimilarityLayer().find_similar("x", top_k=2)

    embed, search = seen
    assert json.loads(embed.content)["prompt"] == "x"
    body = json.loads(search.content)
    assert body["vector"] == [0.1, 0.2]
    assert body["limit"] == 6  # over-fetch 3x, then dedupe
    assert [c["match"]["text"] for c in body["filter"]["should"]] == [
        "archive/jira/OPS/",
        "archive/jira/SEC/",
    ]


def test_find_similar_without_projects_sends_no_filter(
    monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    monkeypatch.setenv("MTTD_INCIDENT_PROJECTS", "")
    seen = _similarity_http([], fake_http)
    SimilarityLayer().find_similar("x")
    assert "filter" not in json.loads(seen[1].content)


def test_find_similar_title_only_taken_from_a_heading_with_a_dash(
    monkeypatch: pytest.MonkeyPatch, fake_http
) -> None:
    text = "intro\n# no dash here\n# INFRA-9 — Pool exhaustion — api\nrest"
    _similarity_http([_hit("archive/jira/INFRA/INFRA-9.md", 0.8, text)], fake_http)
    assert SimilarityLayer().find_similar("x")[0].title == "Pool exhaustion — api"
