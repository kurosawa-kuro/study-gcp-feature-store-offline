"""app.batch.read_offline — BQ 取得 / stdout ログ / GCS JSONL 書き出しを検証する。"""

from __future__ import annotations

import json

import pytest

from app.batch import read_offline
from tests.conftest import FakeBucket, FakeBQClient, FakeStorageClient

_ROWS_A = [
    {"property_id": "p001", "rent": 85000, "walk_min": 7, "age_years": 12, "area_m2": 32.5,
     "emb_a_ctr": 0.12, "emb_a_fav_rate": 0.03, "emb_a_semantic_score": 0.72},
]
_ROWS_B = [
    {"property_id": "p001", "rent": 85000, "walk_min": 7, "age_years": 12, "area_m2": 32.5,
     "emb_b_inquiry_rate": 0.01, "emb_b_collab_score": 0.65, "emb_b_engagement": 0.40},
]


class _FakeRow(dict):
    """BQ row の dict アクセスを模倣する。"""
    def __getitem__(self, key: str):
        return super().__getitem__(key)


def _make_fake_bq(rows_a, rows_b):
    call_count = [0]

    class _Client:
        def __init__(self, *a, **k):
            self.queries = []

        def query(self, sql, *a, **k):
            self.queries.append(sql)
            call_count[0] += 1
            rows = rows_a if call_count[0] == 1 else rows_b

            class _Job:
                def result(self_):
                    return [_FakeRow(r) for r in rows]

            return _Job()

    return _Client


def test_run_requires_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "")
    monkeypatch.delenv("PROJECT_ID", raising=False)
    with pytest.raises(SystemExit, match="PROJECT_ID"):
        read_offline.run()


def test_run_requires_gcs_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr("app.config.GCS_BUCKET", "")
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(SystemExit, match="GCS_BUCKET"):
        read_offline.run()


def test_run_uploads_jsonl_for_both_sources(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.bigquery.Client", _make_fake_bq(_ROWS_A, _ROWS_B))

    bucket = FakeBucket("bkt")
    monkeypatch.setattr(
        "app.batch.read_offline.storage.Client",
        lambda *a, **k: FakeStorageClient(bucket=bucket),
    )
    # /tmp を tmp_path に差し替え
    monkeypatch.setattr("app.batch.read_offline.Path", lambda p: tmp_path / p.lstrip("/"))

    read_offline.run()

    keys = list(bucket.objects.keys())
    assert any("emb_a" in k for k in keys)
    assert any("emb_b" in k for k in keys)


def test_run_stdout_log_format(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.bigquery.Client", _make_fake_bq(_ROWS_A, _ROWS_B))

    bucket = FakeBucket("bkt")
    monkeypatch.setattr(
        "app.batch.read_offline.storage.Client",
        lambda *a, **k: FakeStorageClient(bucket=bucket),
    )
    monkeypatch.setattr("app.batch.read_offline.Path", lambda p: tmp_path / p.lstrip("/"))

    read_offline.run()

    out = capsys.readouterr().out
    assert "[offline-feature][emb_a]" in out
    assert "[offline-feature][emb_b]" in out
    assert "property_id=p001" in out


def test_run_jsonl_content_is_valid(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.bigquery.Client", _make_fake_bq(_ROWS_A, _ROWS_B))

    bucket = FakeBucket("bkt")
    monkeypatch.setattr(
        "app.batch.read_offline.storage.Client",
        lambda *a, **k: FakeStorageClient(bucket=bucket),
    )
    monkeypatch.setattr("app.batch.read_offline.Path", lambda p: tmp_path / p.lstrip("/"))

    read_offline.run()

    blob_a = next(v for k, v in bucket.objects.items() if "emb_a" in k)
    record = json.loads(blob_a.splitlines()[0])
    assert record["property_id"] == "p001"
    assert "emb_a_ctr" in record
    assert "emb_b_inquiry_rate" not in record


def test_run_warns_on_empty_rows(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.bigquery.Client", _make_fake_bq([], []))
    monkeypatch.setattr(
        "app.batch.read_offline.storage.Client",
        lambda *a, **k: FakeStorageClient(),
    )
    monkeypatch.setattr("app.batch.read_offline.Path", lambda p: tmp_path / p.lstrip("/"))

    read_offline.run()

    out = capsys.readouterr().out
    assert "[warn]" in out


def test_bq_sql_filters_by_embedding_source(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queries: list[str] = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        def query(self, sql, *a, **k):
            queries.append(sql)

            class _Job:
                def result(self_):
                    return []

            return _Job()

    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr("app.config.GCS_BUCKET", "bkt")
    monkeypatch.setattr("app.batch.read_offline.bigquery.Client", _Client)
    monkeypatch.setattr(
        "app.batch.read_offline.storage.Client",
        lambda *a, **k: FakeStorageClient(),
    )
    monkeypatch.setattr("app.batch.read_offline.Path", lambda p: tmp_path / p.lstrip("/"))

    read_offline.run()

    assert len(queries) == 2
    assert "embedding_source = 'emb_a'" in queries[0]
    assert "embedding_source = 'emb_b'" in queries[1]
