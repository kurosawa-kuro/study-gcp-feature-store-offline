"""app.batch.read_offline — Feature Store REST API 経由での特徴量取得を検証する。

フロー:
  Feature Group GET → BQ source URI 取得
  Feature LIST       → Feature ID 一覧取得
  SELECT 動的生成    → BigQuery 実行
  stdout + GCS JSONL 出力
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from app.batch import read_offline
from tests.conftest import FakeBucket, FakeStorageClient

# ---------------------------------------------------------------------------
# テスト用定数
# ---------------------------------------------------------------------------

_PROJECT = "proj"
_REGION = "asia-northeast1"
_FG_EMB_A = "fg_property_emb_a"
_FG_EMB_B = "fg_property_emb_b"

_FG_A_RESPONSE = {
    "name": f"projects/{_PROJECT}/locations/{_REGION}/featureGroups/{_FG_EMB_A}",
    "bigQuery": {
        "bigQuerySource": {"inputUri": f"bq://{_PROJECT}.feature_mart.v_property_features_emb_a"},
        "entityIdColumns": ["property_id"],
    },
}
_FG_B_RESPONSE = {
    "name": f"projects/{_PROJECT}/locations/{_REGION}/featureGroups/{_FG_EMB_B}",
    "bigQuery": {
        "bigQuerySource": {"inputUri": f"bq://{_PROJECT}.feature_mart.v_property_features_emb_b"},
        "entityIdColumns": ["property_id"],
    },
}

_FEATURES_A = [
    "rent", "walk_min", "age_years", "area_m2",
    "emb_a_ctr", "emb_a_fav_rate", "emb_a_semantic_score",
]
_FEATURES_B = [
    "rent", "walk_min", "age_years", "area_m2",
    "emb_b_inquiry_rate", "emb_b_collab_score", "emb_b_engagement",
]

_FEATURE_LIST_A = {
    "features": [
        {"name": f"projects/{_PROJECT}/locations/{_REGION}/featureGroups/{_FG_EMB_A}/features/{f}"}
        for f in _FEATURES_A
    ]
}
_FEATURE_LIST_B = {
    "features": [
        {"name": f"projects/{_PROJECT}/locations/{_REGION}/featureGroups/{_FG_EMB_B}/features/{f}"}
        for f in _FEATURES_B
    ]
}

_ROWS_A = [
    {"property_id": "p001", "rent": 85000, "walk_min": 7, "age_years": 12, "area_m2": 32.5,
     "emb_a_ctr": 0.12, "emb_a_fav_rate": 0.03, "emb_a_semantic_score": 0.72},
]
_ROWS_B = [
    {"property_id": "p001", "rent": 85000, "walk_min": 7, "age_years": 12, "area_m2": 32.5,
     "emb_b_inquiry_rate": 0.01, "emb_b_collab_score": 0.65, "emb_b_engagement": 0.40},
]


# ---------------------------------------------------------------------------
# ヘルパー: Feature Store REST API のモック
# ---------------------------------------------------------------------------

def _make_fake_request(fg_a=_FG_A_RESPONSE, fg_b=_FG_B_RESPONSE,
                        features_a=_FEATURE_LIST_A, features_b=_FEATURE_LIST_B):
    """_request() を差し替える。URL パターンで応答を分岐する。"""
    def fake_request(url, *, token):
        if f"/featureGroups/{_FG_EMB_A}/features" in url:
            return features_a
        if f"/featureGroups/{_FG_EMB_B}/features" in url:
            return features_b
        if f"/featureGroups/{_FG_EMB_A}" in url:
            return fg_a
        if f"/featureGroups/{_FG_EMB_B}" in url:
            return fg_b
        raise AssertionError(f"unexpected URL: {url}")
    return fake_request


# ---------------------------------------------------------------------------
# ヘルパー: BigQuery クライアントのモック
# ---------------------------------------------------------------------------

class _FakeRow(dict):
    def __getitem__(self, key):
        return super().__getitem__(key)


def _make_fake_bq(rows_a, rows_b):
    call_count = [0]

    class _Client:
        def __init__(self, *a, **k):
            self.queries: list[str] = []

        def query(self, sql, *a, **k):
            self.queries.append(sql)
            call_count[0] += 1
            rows = rows_a if call_count[0] == 1 else rows_b

            class _Job:
                def result(self_):
                    return [_FakeRow(r) for r in rows]

            return _Job()

    return _Client


# ---------------------------------------------------------------------------
# unit tests: ヘルパー関数
# ---------------------------------------------------------------------------

def test_bq_ref_strips_prefix():
    assert read_offline._bq_ref("bq://proj.dataset.view") == "proj.dataset.view"


def test_build_sql_uses_feature_ids():
    sql = read_offline._build_sql(
        "proj.ds.view",
        entity_id_cols=["property_id"],
        feature_ids=["rent", "walk_min"],
    )
    assert "SELECT property_id, rent, walk_min" in sql
    assert "FROM `proj.ds.view`" in sql
    assert 'CURRENT_DATE("Asia/Tokyo")' in sql


def test_build_sql_no_hardcoded_columns():
    sql = read_offline._build_sql("proj.ds.view", ["eid"], ["feat_x", "feat_y"])
    assert "emb_a_ctr" not in sql
    assert "emb_b_inquiry_rate" not in sql
    assert "feat_x" in sql
    assert "feat_y" in sql


# ---------------------------------------------------------------------------
# unit tests: Feature Store REST ヘルパー
# ---------------------------------------------------------------------------

def test_get_feature_group_raises_on_404(monkeypatch: pytest.MonkeyPatch):
    def fake_request(url, *, token):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(read_offline, "_request", fake_request)
    with pytest.raises(SystemExit, match="Feature Group が見つかりません"):
        read_offline._get_feature_group("proj", "region", "tok", "missing-fg")


def test_list_features_raises_on_empty(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(read_offline, "_request", lambda url, *, token: {"features": []})
    with pytest.raises(SystemExit, match="features が登録されていません"):
        read_offline._list_features("proj", "region", "tok", "fg-empty")


def test_list_features_returns_ids(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(read_offline, "_request", lambda url, *, token: _FEATURE_LIST_A)
    ids = read_offline._list_features("proj", _REGION, "tok", _FG_EMB_A)
    assert ids == _FEATURES_A


# ---------------------------------------------------------------------------
# integration tests: run()
# ---------------------------------------------------------------------------

def test_run_requires_project_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.config.PROJECT_ID", "")
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="PROJECT_ID"):
        read_offline.run()


def test_run_requires_gcs_bucket(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.config.PROJECT_ID", _PROJECT)
    monkeypatch.setattr("app.config.GCS_BUCKET", "")
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(SystemExit, match="GCS_BUCKET"):
        read_offline.run()


def _patch_run(monkeypatch, tmp_path, rows_a=_ROWS_A, rows_b=_ROWS_B,
               features_a=_FEATURE_LIST_A, features_b=_FEATURE_LIST_B,
               fg_a=_FG_A_RESPONSE, fg_b=_FG_B_RESPONSE):
    """run() に必要な全モックをまとめて適用する。"""
    monkeypatch.setattr("app.config.PROJECT_ID", _PROJECT)
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.access_token", lambda: "fake-token")
    monkeypatch.setattr(
        "app.batch.read_offline._request",
        _make_fake_request(fg_a, fg_b, features_a, features_b),
    )
    monkeypatch.setattr(
        "app.batch.read_offline.bigquery.Client",
        _make_fake_bq(rows_a, rows_b),
    )
    bucket = FakeBucket("bkt")
    monkeypatch.setattr(
        "app.batch.read_offline.storage.Client",
        lambda *a, **k: FakeStorageClient(bucket=bucket),
    )
    monkeypatch.setattr("app.batch.read_offline.Path", lambda p: tmp_path / p.lstrip("/"))
    return bucket


def test_run_fetches_feature_group_for_each_source(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Feature Group を emb_a / emb_b それぞれ GET していること。"""
    called_urls: list[str] = []
    original = _make_fake_request()

    def tracking_request(url, *, token):
        called_urls.append(url)
        return original(url, token=token)

    _patch_run(monkeypatch, tmp_path)
    monkeypatch.setattr("app.batch.read_offline._request", tracking_request)

    read_offline.run()

    fg_gets = [u for u in called_urls if "/featureGroups/" in u]
    assert any(_FG_EMB_A in u for u in fg_gets)
    assert any(_FG_EMB_B in u for u in fg_gets)


def test_run_lists_features_for_each_group(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Feature 一覧を emb_a / emb_b それぞれ LIST していること。"""
    called_urls: list[str] = []
    original = _make_fake_request()

    def tracking_request(url, *, token):
        called_urls.append(url)
        return original(url, token=token)

    _patch_run(monkeypatch, tmp_path)
    monkeypatch.setattr("app.batch.read_offline._request", tracking_request)

    read_offline.run()

    feature_lists = [u for u in called_urls if "/features" in u and "featureGroups" in u]
    assert any(_FG_EMB_A in u for u in feature_lists)
    assert any(_FG_EMB_B in u for u in feature_lists)


def test_run_sql_uses_dynamic_columns(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """SQL が Feature Store から取得した Feature ID で動的生成されること (直書きなし)。"""
    captured_queries: list[str] = []
    original_bq = _make_fake_bq(_ROWS_A, _ROWS_B)

    class _TrackingClient(original_bq):  # type: ignore[misc]
        def query(self, sql, *a, **k):
            captured_queries.append(sql)
            return super().query(sql, *a, **k)

    _patch_run(monkeypatch, tmp_path)
    monkeypatch.setattr("app.batch.read_offline.bigquery.Client", _TrackingClient)

    read_offline.run()

    assert len(captured_queries) == 2
    sql_a, sql_b = captured_queries
    # emb_a: Feature Store から取得した列を使う
    assert "emb_a_ctr" in sql_a
    assert "emb_a_fav_rate" in sql_a
    assert "emb_b_inquiry_rate" not in sql_a
    # emb_b: 同様
    assert "emb_b_inquiry_rate" in sql_b
    assert "emb_a_ctr" not in sql_b
    # BQ source URI が Feature Store から解決されていること
    assert "v_property_features_emb_a" in sql_a
    assert "v_property_features_emb_b" in sql_b


def test_run_uploads_jsonl_for_both_sources(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    bucket = _patch_run(monkeypatch, tmp_path)
    read_offline.run()

    keys = list(bucket.objects.keys())
    assert any("emb_a" in k for k in keys)
    assert any("emb_b" in k for k in keys)


def test_run_stdout_log_format(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _patch_run(monkeypatch, tmp_path)
    read_offline.run()

    out = capsys.readouterr().out
    assert "[offline-feature][emb_a]" in out
    assert "[offline-feature][emb_b]" in out
    assert "property_id=p001" in out


def test_run_jsonl_content_is_valid(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    bucket = _patch_run(monkeypatch, tmp_path)
    read_offline.run()

    blob_a = next(v for k, v in bucket.objects.items() if "emb_a" in k)
    record = json.loads(blob_a.splitlines()[0])
    assert record["property_id"] == "p001"
    assert "emb_a_ctr" in record
    assert "emb_b_inquiry_rate" not in record


def test_run_warns_on_empty_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _patch_run(monkeypatch, tmp_path, rows_a=[], rows_b=[])
    read_offline.run()

    out = capsys.readouterr().out
    assert "[warn]" in out


def test_run_fails_when_feature_group_missing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Feature Group が存在しない場合は SystemExit でバッチを失敗させる。"""
    monkeypatch.setattr("app.config.PROJECT_ID", _PROJECT)
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.access_token", lambda: "fake-token")

    def fake_request(url, *, token):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr("app.batch.read_offline._request", fake_request)

    with pytest.raises(SystemExit, match="Feature Group が見つかりません"):
        read_offline.run()


def test_run_fails_when_features_empty(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Feature が未登録の場合は SystemExit でバッチを失敗させる。"""
    empty_features = {"features": []}
    _patch_run(monkeypatch, tmp_path, features_a=empty_features)

    with pytest.raises(SystemExit, match="features が登録されていません"):
        read_offline.run()
