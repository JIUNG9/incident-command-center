"""Importers: redaction, the shared run loop (watermark, idempotence, errors) and GitHub.

No network. The GitHub importer runs unmodified against httpx.MockTransport;
the run loop is driven by a small in-memory subclass of ImporterBase.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from vigil.importers.base import ImporterBase
from vigil.importers.github import GitHubImporter, _slug
from vigil.importers.redact import redact

# ---------------------------------------------------------------- redact

FAKE_GH = "ghp_" + "a1B2c3D4e5" * 4
FAKE_SLACK = "xoxb-" + "1234567890-abcdefghij"


@pytest.mark.parametrize(
    ("raw", "marker"),
    [
        ("key AKIAABCDEFGHIJKLMNOP here", "[REDACTED-AWS-ACCESS-KEY]"),
        ("sts ASIAABCDEFGHIJKLMNOP here", "[REDACTED-AWS-STS-KEY]"),
        ("account 123456789012 owns it", "[REDACTED-AWS-ACCOUNT]"),
        (f"token {FAKE_SLACK}", "[REDACTED-SLACK-BOT]"),
        (f"pat {FAKE_GH}", "[REDACTED-GITHUB-PAT]"),
        ("ATATT3" + "x" * 20, "[REDACTED-ATLASSIAN]"),
        ("Authorization: Bearer abc.def-123", "[REDACTED-BEARER]"),
        ("https://x.example/hook?token=s3cr3t&a=1", "[REDACTED-URL-PARAM]"),
    ],
)
def test_redact_replaces_each_secret_shape(raw: str, marker: str) -> None:
    out = redact(raw)
    assert marker in out
    for secret in (
        "AKIAABCDEFGHIJKLMNOP",
        "ASIAABCDEFGHIJKLMNOP",
        "123456789012",
        FAKE_SLACK,
        FAKE_GH,
        "s3cr3t",
        "abc.def-123",
    ):
        assert secret not in out


def test_redact_keeps_url_param_name_and_other_params() -> None:
    out = redact("https://x.example/hook?token=s3cr3t&a=1")
    assert out == "https://x.example/hook?token=[REDACTED-URL-PARAM]&a=1"


def test_redact_leaves_longer_digit_runs_alone() -> None:
    """A 13-digit number (an epoch in ms) is not an account id."""
    assert redact("ts=1700000000000") == "ts=1700000000000"
    assert redact("id-123456789012") == "id-123456789012"


def test_redact_is_idempotent() -> None:
    once = redact(f"a 123456789012 b {FAKE_GH} c AKIAABCDEFGHIJKLMNOP")
    assert redact(once) == once


def test_redact_private_ips_only_when_asked() -> None:
    text = "db at 10.1.2.3 and 8.8.8.8"
    assert redact(text) == text
    assert redact(text, scrub_private_ips=True) == "db at [REDACTED-IP] and 8.8.8.8"


def test_redact_custom_patterns_run_after_builtin_ones() -> None:
    out = redact("ticket ACME-42", custom_patterns=[(re.compile(r"ACME-\d+"), "[T]")])
    assert out == "ticket [T]"


def test_redact_empty_text_passes_through() -> None:
    assert redact("") == ""


# ---------------------------------------------------------------- run loop


class StubImporter(ImporterBase):
    """Yields the dicts it was given; render raises on items marked bad."""

    source_name = "stub"
    CHECKPOINT_EVERY = 2

    def __init__(self, brain_root: Path, items: list[dict], **kw: Any) -> None:
        super().__init__(brain_root, **kw)
        self.items = items
        self.seen_since: list[Any] = []

    def iterate(self, since: Any) -> Iterator[dict]:
        self.seen_since.append(since)
        yield from self.items

    def render(self, item: dict) -> tuple[str, dict, str]:
        if item.get("bad"):
            raise ValueError("cannot render")
        return f"{item['id']}.md", {"source": "stub", "source_id": item["id"]}, item["body"]

    def watermark(self, item: dict) -> Any:
        return item.get("wm")


def _item(i: int, wm: str, body: str = "hello") -> dict:
    return {"id": f"i{i}", "wm": wm, "body": body}


def _state(root: Path) -> dict:
    return json.loads((root / ".vigil-sync" / "state.json").read_text())


def test_run_writes_files_with_frontmatter_and_redacted_body(tmp_path: Path) -> None:
    imp = StubImporter(tmp_path, [_item(1, "2026-01-01", f"key AKIAABCDEFGHIJKLMNOP {FAKE_GH}")])
    result = imp.run()

    text = (tmp_path / "archive" / "stub" / "i1.md").read_text()
    _, fm, body = text.split("---\n", 2)
    assert yaml.safe_load(fm) == {"source": "stub", "source_id": "i1"}
    assert "AKIAABCDEFGHIJKLMNOP" not in body
    assert FAKE_GH not in body
    assert (result.written, result.skipped, result.errors) == (1, 0, 0)


def test_run_persists_the_max_watermark_not_the_last_one(tmp_path: Path) -> None:
    items = [_item(1, "2026-03-01"), _item(2, "2026-05-01"), _item(3, "2026-02-01")]
    result = StubImporter(tmp_path, items).run()

    assert result.new_watermark == "2026-05-01"
    assert _state(tmp_path)["stub"]["watermark"] == "2026-05-01"


def test_second_run_receives_the_stored_watermark(tmp_path: Path) -> None:
    StubImporter(tmp_path, [_item(1, "2026-04-01")]).run()
    second = StubImporter(tmp_path, [])
    second.run()
    assert second.seen_since == ["2026-04-01"]


def test_unchanged_items_are_skipped_on_rerun(tmp_path: Path) -> None:
    items = [_item(1, "2026-04-01")]
    StubImporter(tmp_path, items).run()
    again = StubImporter(tmp_path, items).run()
    assert (again.written, again.skipped) == (0, 1)


def test_changed_body_is_rewritten(tmp_path: Path) -> None:
    StubImporter(tmp_path, [_item(1, "2026-04-01", "old")]).run()
    again = StubImporter(tmp_path, [_item(1, "2026-04-02", "new")]).run()
    assert again.written == 1
    assert "new" in (tmp_path / "archive" / "stub" / "i1.md").read_text()


def test_dry_run_writes_no_file_and_no_state(tmp_path: Path) -> None:
    result = StubImporter(tmp_path, [_item(1, "2026-04-01")], dry_run=True).run()

    assert result.written == 1  # counted as "would write"
    assert not (tmp_path / "archive").exists()
    assert not (tmp_path / ".vigil-sync").exists()


def test_render_error_is_counted_and_does_not_stop_the_run(tmp_path: Path) -> None:
    items = [
        _item(1, "2026-01-01"),
        {"id": "bad", "bad": True, "wm": "2099-01-01"},
        _item(3, "2026-02-01"),
    ]
    result = StubImporter(tmp_path, items).run()

    assert (result.written, result.errors) == (2, 1)
    # The failed item must not advance the watermark, or it would never be retried.
    assert result.new_watermark == "2026-02-01"


def test_checkpoint_saves_state_before_the_run_ends(tmp_path: Path) -> None:
    """A run killed mid-way keeps its progress (CHECKPOINT_EVERY=2 here)."""

    class Dies(StubImporter):
        def iterate(self, since: Any) -> Iterator[dict]:
            yield _item(1, "2026-01-01")
            yield _item(2, "2026-01-02")
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        Dies(tmp_path, []).run()

    saved = _state(tmp_path)["stub"]
    assert saved["watermark"] == "2026-01-02"
    assert saved["last_checkpoint_count"] == 2


def test_corrupt_state_file_starts_a_full_import(tmp_path: Path) -> None:
    state = tmp_path / ".vigil-sync" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text("{not json")

    imp = StubImporter(tmp_path, [_item(1, "2026-01-01")])
    imp.run()

    assert imp.seen_since == [None]
    assert _state(tmp_path)["stub"]["watermark"] == "2026-01-01"


def test_state_of_other_sources_is_kept(tmp_path: Path) -> None:
    state = tmp_path / ".vigil-sync" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"jira": {"watermark": "J1"}}))

    StubImporter(tmp_path, [_item(1, "2026-01-01")]).run()

    saved = _state(tmp_path)
    assert saved["jira"] == {"watermark": "J1"}
    assert saved["stub"]["watermark"] == "2026-01-01"


# ---------------------------------------------------------------- GitHub


@pytest.fixture
def gh_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_PAT", "test-token")
    monkeypatch.setenv("GITHUB_ORG", "acme-corp")
    monkeypatch.setenv("GITHUB_REPOS", "app")


def _route(
    handler: Callable[[httpx.Request], httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> list[httpx.Request]:
    real = httpx.Client
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(recording)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return seen


def _issue(
    num: int, title: str, *, pr: bool = False, updated: str = "2026-05-01T00:00:00Z"
) -> dict:
    out: dict[str, Any] = {
        "number": num,
        "title": title,
        "state": "open",
        "html_url": f"https://github.com/acme-corp/app/issues/{num}",
        "comments_url": f"https://api.github.com/repos/acme-corp/app/issues/{num}/comments",
        "updated_at": updated,
        "created_at": "2026-04-01T00:00:00Z",
        "user": {"login": "alice.dev"},
        "labels": [{"name": "incident"}, {"color": "ffffff"}],
        "body": "Disk full on db01",
    }
    if pr:
        out["pull_request"] = {"url": "x"}
    return out


def test_github_requires_token_and_org(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GITHUB_PAT", raising=False)
    monkeypatch.setenv("GITHUB_ORG", "acme-corp")
    with pytest.raises(ValueError, match="GITHUB_PAT"):
        GitHubImporter(tmp_path)

    monkeypatch.setenv("GITHUB_PAT", "t")
    monkeypatch.delenv("GITHUB_ORG")
    with pytest.raises(ValueError, match="GITHUB_ORG"):
        GitHubImporter(tmp_path)


def test_slug_is_lowercase_ascii_and_never_empty() -> None:
    assert _slug("Disk FULL: db01 / prod!") == "disk-full-db01-prod"
    assert _slug("한글") == "untitled"
    assert len(_slug("a" * 200)) == 60


def test_github_run_writes_readme_issue_and_pr(
    gh_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    readme = base64.b64encode(f"# app\nkey {FAKE_GH}".encode()).decode()

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/readme"):
            return httpx.Response(
                200,
                json={
                    "name": "README.md",
                    "sha": "abc",
                    "content": readme,
                    "html_url": "https://github.com/acme-corp/app",
                },
            )
        if path.endswith("/issues"):
            if req.url.params["state"] == "closed":
                return httpx.Response(200, json=[])
            return httpx.Response(
                200, json=[_issue(7, "Disk full"), _issue(8, "Fix disk alert", pr=True)]
            )
        if path.endswith("/comments"):
            return httpx.Response(
                200,
                json=[
                    {
                        "user": {"login": "bob.ops"},
                        "created_at": "t1",
                        "body": "Expanded the volume",
                    }
                ],
            )
        return httpx.Response(404)

    _route(handler, monkeypatch)
    result = GitHubImporter(tmp_path).run()

    base = tmp_path / "archive" / "github" / "acme-corp" / "app"
    assert (result.written, result.errors) == (3, 0)
    assert (base / "README.md").exists()
    assert (base / "issues" / "7-disk-full.md").exists()
    assert (base / "pull_requests" / "8-fix-disk-alert.md").exists()

    assert FAKE_GH not in (base / "README.md").read_text()
    issue = (base / "issues" / "7-disk-full.md").read_text()
    fm = yaml.safe_load(issue.split("---\n")[1])
    assert fm["source_id"] == "acme-corp/app#7"
    assert fm["labels"] == ["incident"]  # a label dict without "name" is dropped
    assert fm["author"] == "alice.dev"
    assert "### bob.ops — t1" in issue
    assert "Expanded the volume" in issue
    assert result.new_watermark == "2026-05-01T00:00:00Z"


def test_github_passes_the_watermark_as_since(
    gh_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / ".vigil-sync" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"github": {"watermark": "2026-05-01T00:00:00Z"}}))

    def handler(req: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json=[])
            if req.url.path.endswith("/issues")
            else httpx.Response(404)
        )

    seen = _route(handler, monkeypatch)
    GitHubImporter(tmp_path).run()

    issue_calls = [r for r in seen if r.url.path.endswith("/issues")]
    assert {r.url.params["state"] for r in issue_calls} == {"open", "closed"}
    assert all(r.url.params["since"] == "2026-05-01T00:00:00+00:00" for r in issue_calls)


def test_github_unparseable_watermark_falls_back_to_a_full_scan(
    gh_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = tmp_path / ".vigil-sync" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"github": {"watermark": "garbage"}}))

    def handler(req: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json=[])
            if req.url.path.endswith("/issues")
            else httpx.Response(404)
        )

    seen = _route(handler, monkeypatch)
    GitHubImporter(tmp_path).run()

    assert all("since" not in r.url.params for r in seen if r.url.path.endswith("/issues"))


def test_github_issues_disabled_repo_is_not_an_error(
    gh_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(410) if req.url.path.endswith("/issues") else httpx.Response(404)

    _route(handler, monkeypatch)
    result = GitHubImporter(tmp_path).run()
    assert (result.written, result.errors) == (0, 0)


def test_github_pages_until_a_short_page(
    gh_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/issues") and req.url.params["state"] == "open":
            page = int(req.url.params["page"])
            n = 100 if page == 1 else 1
            return httpx.Response(
                200, json=[_issue(page * 1000 + i, f"t{page}-{i}") for i in range(n)]
            )
        if req.url.path.endswith("/issues"):
            return httpx.Response(200, json=[])
        if req.url.path.endswith("/comments"):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    _route(handler, monkeypatch)
    result = GitHubImporter(tmp_path).run()
    assert result.written == 101


def test_github_discovers_repos_when_none_listed(
    gh_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GITHUB_REPOS")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/orgs/acme-corp/repos":
            return httpx.Response(
                200,
                json=[{"name": "alpha"}, {"name": "beta"}] if req.url.params["page"] == "1" else [],
            )
        return httpx.Response(404)

    seen = _route(handler, monkeypatch)
    GitHubImporter(tmp_path).run()

    crawled = {r.url.path.split("/")[3] for r in seen if r.url.path.startswith("/repos/")}
    assert crawled == {"alpha", "beta"}
