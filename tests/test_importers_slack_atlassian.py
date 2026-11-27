"""Slack, Jira and Confluence importers. No network.

Jira and Confluence run unmodified against httpx.MockTransport. Slack runs
against a fake WebClient, since slack_sdk talks to Slack over its own client.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from slack_sdk.errors import SlackApiError

from vigil.importers.confluence import ConfluenceImporter, _confluence_storage_to_markdown
from vigil.importers.confluence import _slug as confluence_slug
from vigil.importers.jira import JiraImporter, _adf_to_text, _html_to_markdown
from vigil.importers.slack import SlackImporter


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


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---\n")[1])


def _write_state(root: Path, state: dict) -> None:
    path = root / ".vigil-sync" / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(state))


# ---------------------------------------------------------------- Jira


@pytest.fixture
def jira_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JIRA_BASE_URL", "https://acme-corp.atlassian.net")
    monkeypatch.setenv("JIRA_PROJECTS", "OPS, PLAT")
    monkeypatch.setenv("ATLASSIAN_EMAIL", "alice.dev@acme-corp.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "test-token")


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("JIRA_BASE_URL", "JIRA_BASE_URL"),
        ("JIRA_PROJECTS", "JIRA_PROJECTS"),
        ("ATLASSIAN_EMAIL", "ATLASSIAN_EMAIL"),
        ("ATLASSIAN_API_TOKEN", "ATLASSIAN_API_TOKEN"),
    ],
)
def test_jira_requires_each_env_var(
    jira_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing: str, message: str
) -> None:
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError, match=message):
        JiraImporter(tmp_path)


def _jira_issue(key: str, updated: str, **fields: Any) -> dict:
    return {
        "key": key,
        "fields": {"summary": f"Summary of {key}", "updated": updated, **fields},
        "renderedFields": fields.pop("_rendered", {}),
    }


def test_jira_jql_filters_by_project_and_watermark_and_sorts_ascending(
    jira_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_state(tmp_path, {"jira": {"watermark": "2026-05-01T10:30:45.000+0000"}})
    seen = _route(lambda req: httpx.Response(200, json={"issues": []}), monkeypatch)
    JiraImporter(tmp_path).run()

    jql = seen[0].url.params["jql"]
    assert jql == 'project IN (OPS,PLAT) AND updated > "2026-05-01 10:30" ORDER BY updated ASC'


def test_jira_unparseable_watermark_drops_the_updated_clause(
    jira_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_state(tmp_path, {"jira": {"watermark": "garbage"}})
    seen = _route(lambda req: httpx.Response(200, json={"issues": []}), monkeypatch)
    JiraImporter(tmp_path).run()

    assert seen[0].url.params["jql"] == "project IN (OPS,PLAT) ORDER BY updated ASC"


def test_jira_follows_next_page_token_until_it_is_absent(
    jira_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.params.get("nextPageToken") == "p2":
            return httpx.Response(200, json={"issues": [_jira_issue("OPS-2", "2026-05-02T00:00:00.000+0000")]})
        return httpx.Response(
            200,
            json={"issues": [_jira_issue("OPS-1", "2026-05-01T00:00:00.000+0000")], "nextPageToken": "p2"},
        )

    seen = _route(handler, monkeypatch)
    result = JiraImporter(tmp_path).run()

    assert len(seen) == 2
    assert result.written == 2
    assert result.new_watermark == "2026-05-02T00:00:00.000+0000"


def test_jira_http_error_ends_the_run_without_raising_or_moving_the_watermark(
    jira_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_state(tmp_path, {"jira": {"watermark": "2026-05-01T00:00:00.000+0000"}})
    _route(lambda req: httpx.Response(401, text="unauthorized"), monkeypatch)
    result = JiraImporter(tmp_path).run()

    assert (result.written, result.errors) == (0, 0)
    assert result.new_watermark == "2026-05-01T00:00:00.000+0000"


def test_jira_render_writes_frontmatter_description_and_comments(
    jira_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    adf = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Restarted db01"}]}],
    }
    issue = {
        "key": "OPS-7",
        "fields": {
            "summary": "Disk full",
            "updated": "2026-05-03T00:00:00.000+0000",
            "created": "2026-05-01T00:00:00.000+0000",
            "reporter": {"displayName": "Alice Dev"},
            "assignee": None,
            "status": {"name": "Done"},
            "priority": {"name": "High"},
            "issuetype": {"name": "Incident"},
            "labels": ["storage"],
            "comment": {
                "comments": [
                    {"author": {"displayName": "Bob Ops"}, "created": "t1", "body": adf},
                    {"created": "t2", "body": "plain text body"},
                ]
            },
        },
        "renderedFields": {"description": "<p>Volume <strong>full</strong>.</p>"},
    }
    _route(lambda req: httpx.Response(200, json={"issues": [issue]}), monkeypatch)
    JiraImporter(tmp_path).run()

    path = tmp_path / "archive" / "jira" / "OPS" / "OPS-7.md"
    fm = _frontmatter(path)
    assert fm["source_id"] == "OPS-7"
    assert fm["source_url"] == "https://acme-corp.atlassian.net/browse/OPS-7"
    assert fm["author"] == "Alice Dev"
    assert fm["labels"] == ["storage"]
    assert fm["extra"]["jira_status"] == "Done"
    assert fm["extra"]["jira_assignee"] == ""  # an unassigned issue has assignee null

    text = path.read_text()
    assert "## Description\nVolume **full**." in text
    assert "### Bob Ops — t1\nRestarted db01" in text
    assert "### unknown — t2\nplain text body" in text


def test_jira_render_keeps_only_the_first_30_comments(jira_env: None, tmp_path: Path) -> None:
    comments = [{"author": {"displayName": f"u{i}"}, "created": str(i), "body": "x"} for i in range(35)]
    issue = {"key": "OPS-1", "fields": {"summary": "s", "comment": {"comments": comments}}}
    _, _, body = JiraImporter(tmp_path).render(issue)

    assert body.count("### ") == 30
    assert "### u29 " in body
    assert "### u30 " not in body


def test_jira_render_without_summary_or_description_still_renders(jira_env: None, tmp_path: Path) -> None:
    rel, fm, body = JiraImporter(tmp_path).render({"key": "PLAT-9", "fields": {}})
    assert rel == "PLAT/PLAT-9.md"
    assert fm["title"] == "untitled"
    assert body == "# PLAT-9 — untitled"


def test_html_to_markdown_converts_common_tags() -> None:
    html = (
        "<h2>Impact</h2><p>See <a href=\"https://x.example/a\">the doc</a> &amp; <code>kubectl get</code></p>"
        "<ul><li>one</li><li><em>two</em></li></ul><pre>a &lt; b\n<b>c</b></pre>"
    )
    out = _html_to_markdown(html)
    assert "## Impact" in out
    assert "[the doc](https://x.example/a) & `kubectl get`" in out
    assert "- one\n- *two*" in out
    assert "```\na < b\nc\n```" in out


def test_html_to_markdown_collapses_blank_runs() -> None:
    assert _html_to_markdown("<p>a</p><p></p><p></p><p>b</p>") == "a\n\nb"


def test_adf_to_text_walks_nested_content_and_ends_blocks_with_a_newline() -> None:
    adf = {
        "type": "doc",
        "content": [
            {"type": "heading", "content": [{"type": "text", "text": "Title"}]},
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}]},
            ]},
        ],
    }
    assert _adf_to_text(adf).splitlines()[0] == "Title"
    assert "a" in _adf_to_text(adf)
    assert _adf_to_text({"type": "doc"}) == ""


# ---------------------------------------------------------------- Confluence


@pytest.fixture
def cf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFLUENCE_BASE_URL", "https://acme-corp.atlassian.net/wiki")
    monkeypatch.setenv("CONFLUENCE_SPACES", "OPS,SRE")
    monkeypatch.setenv("ATLASSIAN_EMAIL", "alice.dev@acme-corp.com")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "test-token")


@pytest.mark.parametrize("missing", ["CONFLUENCE_BASE_URL", "CONFLUENCE_SPACES", "ATLASSIAN_EMAIL"])
def test_confluence_requires_each_env_var(
    cf_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, missing: str
) -> None:
    monkeypatch.delenv(missing)
    with pytest.raises(ValueError, match=missing):
        ConfluenceImporter(tmp_path)


def _page(page_id: str, title: str, when: str, storage: str = "<p>body</p>") -> dict:
    return {
        "id": page_id,
        "title": title,
        "space": {"key": "OPS"},
        "version": {"when": when, "number": 3, "by": {"displayName": "Alice Dev"}},
        "body": {"storage": {"value": storage}},
        "_links": {"webui": f"/spaces/OPS/pages/{page_id}"},
    }


def test_confluence_cql_filters_by_space_and_watermark(
    cf_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_state(tmp_path, {"confluence": {"watermark": "2026-05-01T10:30:00.000Z"}})
    seen = _route(lambda req: httpx.Response(200, json={"results": []}), monkeypatch)
    ConfluenceImporter(tmp_path).run()

    assert seen[0].url.params["cql"] == (
        'space IN ("OPS","SRE") AND type = page AND lastmodified > "2026/05/01 10:30" '
        "ORDER BY lastmodified ASC"
    )


def test_confluence_pages_by_start_offset_and_stops_on_a_short_page(
    cf_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        start = int(req.url.params["start"])
        n = 25 if start == 0 else 2
        return httpx.Response(
            200,
            json={"results": [_page(f"{start + i}", f"t{start + i}", "2026-05-01T00:00:00.000Z") for i in range(n)]},
        )

    seen = _route(handler, monkeypatch)
    result = ConfluenceImporter(tmp_path).run()

    assert [r.url.params["start"] for r in seen] == ["0", "25"]
    assert result.written == 27


def test_confluence_http_error_ends_the_run_quietly(
    cf_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _route(lambda req: httpx.Response(500, text="boom"), monkeypatch)
    result = ConfluenceImporter(tmp_path).run()
    assert (result.written, result.errors, result.new_watermark) == (0, 0, None)


def test_confluence_run_writes_page_with_frontmatter_and_watermark(
    cf_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pages = [
        _page("11", "DB Failover: Runbook", "2026-05-02T00:00:00.000Z", "<h1>Steps</h1><p>Promote the replica.</p>"),
        _page("12", "Older", "2026-05-01T00:00:00.000Z"),
    ]
    _route(lambda req: httpx.Response(200, json={"results": pages}), monkeypatch)
    result = ConfluenceImporter(tmp_path).run()

    path = tmp_path / "archive" / "confluence" / "OPS" / "11-db-failover-runbook.md"
    fm = _frontmatter(path)
    assert fm["source_id"] == "11"
    assert fm["source_url"] == "https://acme-corp.atlassian.net/wiki/spaces/OPS/pages/11"
    assert fm["author"] == "Alice Dev"
    assert fm["extra"] == {"confluence_space": "OPS", "confluence_version": 3}
    assert "# Steps\nPromote the replica." in path.read_text()
    assert result.new_watermark == "2026-05-02T00:00:00.000Z"


def test_confluence_render_tolerates_a_page_with_no_space_body_or_links(cf_env: None, tmp_path: Path) -> None:
    rel, fm, body = ConfluenceImporter(tmp_path).render({"id": "5"})
    assert rel == "unknown/5-untitled.md"
    assert fm["author"] == ""
    assert body.startswith("# untitled")


def test_confluence_slug_keeps_hangul_and_never_returns_empty() -> None:
    assert confluence_slug("장애 대응 Runbook!") == "장애-대응-runbook"
    assert confluence_slug("!!!") == "untitled"
    assert len(confluence_slug("a" * 200)) == 60


def test_confluence_storage_drops_macros_it_does_not_know_and_converts_attribute_images() -> None:
    storage = (
        '<ac:structured-macro ac:name="toc"></ac:structured-macro>'
        '<p>see <ac:image ri:filename="graph.png"/></p>'
    )
    assert _confluence_storage_to_markdown(storage) == "see ![image](graph.png)"


# Known data loss, filed in the backlog. Each test states what the module's own
# docstring promises; strict xfail turns into a failure once the importer is fixed,
# which is the cue to drop the marker.
@pytest.mark.xfail(strict=True, reason="CDATA body of a code macro is stripped as a tag")
def test_confluence_code_macro_keeps_its_code() -> None:
    storage = (
        '<ac:structured-macro ac:name="code"><ac:plain-text-body>'
        "<![CDATA[kubectl get pods]]></ac:plain-text-body></ac:structured-macro>"
    )
    assert "kubectl get pods" in _confluence_storage_to_markdown(storage)


@pytest.mark.xfail(strict=True, reason="info/note panels are removed together with their text")
def test_confluence_panel_macro_keeps_its_text() -> None:
    storage = (
        '<ac:structured-macro ac:name="info"><ac:rich-text-body><p>note</p>'
        "</ac:rich-text-body></ac:structured-macro>"
    )
    assert "note" in _confluence_storage_to_markdown(storage)


@pytest.mark.xfail(strict=True, reason="images in the real storage form (ri:attachment child) are dropped")
def test_confluence_image_with_attachment_child_is_kept() -> None:
    storage = '<ac:image><ri:attachment ri:filename="graph.png"/></ac:image>'
    assert "graph.png" in _confluence_storage_to_markdown(storage)


def test_confluence_storage_of_nothing_is_empty() -> None:
    assert _confluence_storage_to_markdown("") == ""


# ---------------------------------------------------------------- Slack


def _ts(day: str, hhmm: str) -> str:
    return str(datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=UTC).timestamp())


LONG = "disk usage on db01 crossed ninety percent"  # >= 30 chars


class FakeSlack:
    """Stands in for slack_sdk.WebClient. Class attributes are set per test."""

    channels: list[dict] = []
    history: dict[str, list[list[dict]]] = {}  # channel id -> pages
    history_error: set[str] = set()
    list_error = False
    users: dict[str, dict] = {}
    history_calls: list[dict] = []
    user_calls: list[str] = []

    def __init__(self, token: str) -> None:
        self.token = token

    def conversations_list(self, **_: Any) -> list[dict]:
        if FakeSlack.list_error:
            raise SlackApiError("nope", {"error": "invalid_auth"})
        return [{"channels": FakeSlack.channels}]

    def conversations_history(self, **kw: Any) -> dict:
        FakeSlack.history_calls.append(kw)
        ch = kw["channel"]
        if ch in FakeSlack.history_error:
            raise SlackApiError("nope", {"error": "not_in_channel"})
        pages = FakeSlack.history[ch]
        index = int(kw["cursor"] or 0)
        nxt = str(index + 1) if index + 1 < len(pages) else ""
        return {"messages": pages[index], "response_metadata": {"next_cursor": nxt}}

    def users_info(self, user: str) -> dict:
        FakeSlack.user_calls.append(user)
        if user not in FakeSlack.users:
            raise SlackApiError("nope", {"error": "user_not_found"})
        return {"user": FakeSlack.users[user]}


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch) -> type[FakeSlack]:
    import slack_sdk

    monkeypatch.setattr(slack_sdk, "WebClient", FakeSlack)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.delenv("SLACK_IMPORT_CHANNELS", raising=False)
    FakeSlack.channels = [
        {"id": "C1", "name": "incidents", "is_member": True},
        {"id": "C2", "name": "random", "is_member": False},
        {"id": "C3", "name": "deploys", "is_member": True},
    ]
    FakeSlack.history = {"C1": [[]], "C3": [[]]}
    FakeSlack.history_error = set()
    FakeSlack.list_error = False
    FakeSlack.users = {"U1": {"real_name": "Alice Dev", "name": "alice"}, "U2": {"name": "bob"}}
    FakeSlack.history_calls = []
    FakeSlack.user_calls = []
    return FakeSlack


def test_slack_requires_a_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
        SlackImporter(tmp_path)


def test_slack_groups_messages_by_channel_and_day_and_drops_noise(
    slack: type[FakeSlack], tmp_path: Path
) -> None:
    slack.history["C1"] = [[
        {"ts": _ts("2026-05-02", "09:05"), "user": "U2", "text": LONG + " again"},
        {"ts": _ts("2026-05-02", "09:00"), "user": "U1", "text": LONG},
        {"ts": _ts("2026-05-02", "09:10"), "user": "U1", "text": "ok"},  # under 30 chars
        {"ts": _ts("2026-05-02", "09:11"), "user": "U1", "text": LONG, "subtype": "channel_join"},
        {"ts": _ts("2026-05-02", "09:12"), "user": "U1", "text": LONG + " (broadcast)", "subtype": "thread_broadcast"},
        {"ts": _ts("2026-05-03", "08:00"), "user": "U1", "text": LONG + " next day"},
    ]]
    result = SlackImporter(tmp_path).run()

    base = tmp_path / "archive" / "slack" / "incidents" / "2026" / "05"
    assert (result.written, result.errors) == (2, 0)
    day = (base / "02-messages.md").read_text()
    assert day.index("09:00 · Alice Dev") < day.index("09:05 · bob")  # sorted by time, name resolved
    assert "(broadcast)" in day
    assert "channel_join" not in day and "· Alice Dev**: ok" not in day
    assert (base / "03-messages.md").exists()
    assert not (tmp_path / "archive" / "slack" / "random").exists()  # bot is not a member


def test_slack_channel_filter_accepts_hash_prefix_and_spaces(
    slack: type[FakeSlack], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SLACK_IMPORT_CHANNELS", " #deploys , ")
    slack.history["C3"] = [[{"ts": _ts("2026-05-02", "09:00"), "user": "U1", "text": LONG}]]
    SlackImporter(tmp_path).run()

    assert {c["channel"] for c in slack.history_calls} == {"C3"}


def test_slack_looks_up_each_user_once(slack: type[FakeSlack], tmp_path: Path) -> None:
    slack.history["C1"] = [[
        {"ts": _ts("2026-05-02", f"09:0{i}"), "user": "U1", "text": LONG} for i in range(3)
    ]]
    SlackImporter(tmp_path).run()
    assert slack.user_calls == ["U1"]


def test_slack_falls_back_to_username_then_user_id(slack: type[FakeSlack], tmp_path: Path) -> None:
    slack.history["C1"] = [[
        {"ts": _ts("2026-05-02", "09:00"), "user": "U2", "text": LONG},
        {"ts": _ts("2026-05-02", "09:01"), "user": "U9", "text": LONG},
    ]]
    SlackImporter(tmp_path).run()

    text = (tmp_path / "archive/slack/incidents/2026/05/02-messages.md").read_text()
    assert "· bob**" in text  # no real_name, so the handle
    assert "· U9**" in text  # lookup failed, so the id


def test_slack_follows_the_history_cursor(slack: type[FakeSlack], tmp_path: Path) -> None:
    slack.history["C1"] = [
        [{"ts": _ts("2026-05-02", "09:00"), "user": "U1", "text": LONG}],
        [{"ts": _ts("2026-05-02", "09:30"), "user": "U1", "text": LONG + " page two"}],
    ]
    SlackImporter(tmp_path).run()

    assert [c["cursor"] for c in slack.history_calls if c["channel"] == "C1"] == [None, "1"]
    assert "page two" in (tmp_path / "archive/slack/incidents/2026/05/02-messages.md").read_text()


def test_slack_history_error_skips_that_channel_only(slack: type[FakeSlack], tmp_path: Path) -> None:
    slack.history_error = {"C1"}
    slack.history["C3"] = [[{"ts": _ts("2026-05-02", "09:00"), "user": "U1", "text": LONG}]]
    result = SlackImporter(tmp_path).run()

    assert result.written == 1
    assert (tmp_path / "archive/slack/deploys/2026/05/02-messages.md").exists()


def test_slack_channel_list_error_yields_nothing(slack: type[FakeSlack], tmp_path: Path) -> None:
    slack.list_error = True
    result = SlackImporter(tmp_path).run()
    assert (result.written, result.errors, slack.history_calls) == (0, 0, [])


def test_slack_stored_watermark_becomes_the_history_start(slack: type[FakeSlack], tmp_path: Path) -> None:
    _write_state(tmp_path, {"slack": {"watermark": "2026-05-01T12:00:00+00:00"}})
    SlackImporter(tmp_path).run()

    oldest = float(slack.history_calls[0]["oldest"])
    assert oldest == datetime(2026, 5, 1, 12, tzinfo=UTC).timestamp()


def test_slack_without_a_watermark_walks_back_history_days(
    slack: type[FakeSlack], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SLACK_HISTORY_DAYS", "7")
    SlackImporter(tmp_path).run()

    age_days = (datetime.now(UTC).timestamp() - float(slack.history_calls[0]["oldest"])) / 86400
    assert 6.99 < age_days < 7.01


def test_slack_watermark_is_the_last_message_time_of_the_rollup(
    slack: type[FakeSlack], tmp_path: Path
) -> None:
    slack.history["C1"] = [[
        {"ts": _ts("2026-05-02", "09:00"), "user": "U1", "text": LONG},
        {"ts": _ts("2026-05-02", "17:45"), "user": "U1", "text": LONG + " later"},
    ]]
    result = SlackImporter(tmp_path).run()
    assert result.new_watermark == "2026-05-02T17:45:00+00:00"


def test_slack_render_indents_multiline_messages_under_their_bullet(tmp_path: Path) -> None:
    rollup = {
        "channel": "incidents",
        "channel_id": "C1",
        "date": "2026-05-02",
        "last_ts": _ts("2026-05-02", "09:00"),
        "messages": [{"ts": _ts("2026-05-02", "09:00"), "_author": "Alice Dev", "text": "line one\nline two"}],
    }
    rel, fm, body = _slack_importer(tmp_path).render(rollup)

    assert rel == "incidents/2026/05/02-messages.md"
    assert fm["source_id"] == "slack/incidents/2026-05-02"
    assert fm["extra"]["slack_channel_id"] == "C1"
    assert "- **09:00 · Alice Dev**: line one\n  line two" in body


def test_slack_watermark_of_a_rollup_without_a_timestamp_is_empty(tmp_path: Path) -> None:
    imp = _slack_importer(tmp_path)
    assert imp.watermark({}) == ""
    assert imp.watermark({"last_ts": "not-a-number"}) == ""


def _slack_importer(root: Path) -> SlackImporter:
    import os

    os.environ["SLACK_BOT_TOKEN"] = "xoxb-test"
    try:
        return SlackImporter(root)
    finally:
        del os.environ["SLACK_BOT_TOKEN"]
