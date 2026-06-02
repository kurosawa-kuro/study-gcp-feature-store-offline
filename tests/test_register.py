"""app.feature_store.register — BQ View 作成 / Feature Group REST 呼び出しを検証する。"""

from __future__ import annotations

import urllib.error
from typing import Any

import pytest

from app.feature_store import register
from tests.conftest import FakeBQClient


# ---------------------------------------------------------------------------
# BQ View
# ---------------------------------------------------------------------------


def test_create_views_calls_create_table_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBQClient()
    monkeypatch.setattr("app.feature_store.register.bigquery.Client", lambda *a, **k: fake)
    monkeypatch.setattr("app.feature_store.register.bigquery.Table", lambda ref: _FakeTable(ref))

    register._create_views(fake, "proj")

    assert len(fake.created_tables) == 2
    views = [t.ref for t in fake.created_tables]
    assert any("emb_a" in v for v in views)
    assert any("emb_b" in v for v in views)


def test_emb_a_view_query_filters_source(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBQClient()
    monkeypatch.setattr("app.feature_store.register.bigquery.Table", lambda ref: _FakeTable(ref))

    register._create_views(fake, "proj")

    table_a = next(t for t in fake.created_tables if "emb_a" in t.ref)
    assert "embedding_source = 'emb_a'" in table_a.view_query
    assert "emb_a_ctr" in table_a.view_query
    assert "emb_b_inquiry_rate" not in table_a.view_query


def test_emb_b_view_query_filters_source(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeBQClient()
    monkeypatch.setattr("app.feature_store.register.bigquery.Table", lambda ref: _FakeTable(ref))

    register._create_views(fake, "proj")

    table_b = next(t for t in fake.created_tables if "emb_b" in t.ref)
    assert "embedding_source = 'emb_b'" in table_b.view_query
    assert "emb_b_inquiry_rate" in table_b.view_query
    assert "emb_a_ctr" not in table_b.view_query


# ---------------------------------------------------------------------------
# Feature Group REST
# ---------------------------------------------------------------------------


def test_create_feature_group_posts_correct_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, Any]] = []

    def fake_request(url, *, method, token, payload=None):
        captured.append({"url": url, "method": method, "payload": payload})
        return {"name": "projects/p/locations/r/operations/123"}

    monkeypatch.setattr(register, "_request", fake_request)
    monkeypatch.setattr(register, "_poll_lro", lambda *a, **k: None)

    register._create_feature_group("proj", "asia-northeast1", "tok", "fg-test", "v_test")

    assert len(captured) == 1
    req = captured[0]
    assert "featureGroups?featureGroupId=fg-test" in req["url"]
    assert req["payload"]["bigQuery"]["bigQuerySource"]["inputUri"] == "bq://proj.feature_mart.v_test"
    assert req["payload"]["bigQuery"]["entityIdColumns"] == ["property_id"]


def test_create_feature_group_skips_409(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url, *, method, token, payload=None):
        raise urllib.error.HTTPError(url, 409, "Conflict", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(register, "_request", fake_request)

    # 409 は例外にならず正常終了する
    register._create_feature_group("proj", "r", "tok", "fg-test", "v_test")


def test_create_feature_group_raises_non_409(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_request(url, *, method, token, payload=None):
        raise urllib.error.HTTPError(url, 500, "ISE", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(register, "_request", fake_request)

    with pytest.raises(urllib.error.HTTPError):
        register._create_feature_group("proj", "r", "tok", "fg-test", "v_test")


def test_run_requires_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "")
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="PROJECT_ID"):
        register.run()


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------


class _FakeTable:
    def __init__(self, ref: str) -> None:
        self.ref = ref
        self.view_query: str = ""
