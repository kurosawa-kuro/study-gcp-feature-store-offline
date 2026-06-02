"""app.data.load_bq — BQ ロード SQL の構造を検証する。"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.data import load_bq
from tests.conftest import FakeBQClient


def _write_emb_a(tmp_path: Path) -> Path:
    path = tmp_path / "feature_emb_a.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(load_bq.EMB_A_COLS)
        w.writerow(["2026-06-02", "2026-06-02T00:00:00+09:00", "p001", "emb_a", 85000, 7, 12, 32.5, 0.12, 0.03, 0.72])
    return path


def _write_emb_b(tmp_path: Path) -> Path:
    path = tmp_path / "feature_emb_b.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(load_bq.EMB_B_COLS)
        w.writerow(["2026-06-02", "2026-06-02T00:00:00+09:00", "p001", "emb_b", 85000, 7, 12, 32.5, 0.01, 0.65, 0.40])
    return path


def test_run_requires_project_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROJECT_ID", raising=False)
    monkeypatch.setattr("app.config.PROJECT_ID", "")
    with pytest.raises(SystemExit, match="PROJECT_ID"):
        load_bq.run()


def test_run_delete_then_insert_emb_a_and_emb_b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_emb_a(tmp_path)
    _write_emb_b(tmp_path)

    fake = FakeBQClient()
    monkeypatch.setattr("app.data.load_bq.bigquery.Client", lambda *a, **k: fake)
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr(load_bq, "_data_dir", lambda: tmp_path)

    load_bq.run()

    # DELETE 1 回 + emb_a INSERT + emb_b INSERT = 3 クエリ
    assert len(fake.queries) == 3
    delete_sql, insert_a, insert_b = fake.queries

    assert "DELETE FROM" in delete_sql
    assert 'CURRENT_DATE("Asia/Tokyo")' in delete_sql

    assert "INSERT INTO" in insert_a
    assert "emb_a_ctr" in insert_a
    assert "emb_b_inquiry_rate" not in insert_a  # emb_b 列は入らない

    assert "INSERT INTO" in insert_b
    assert "emb_b_inquiry_rate" in insert_b
    assert "emb_a_ctr" not in insert_b  # emb_a 列は入らない


def test_run_error_when_csv_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeBQClient()
    monkeypatch.setattr("app.data.load_bq.bigquery.Client", lambda *a, **k: fake)
    monkeypatch.setattr("app.config.PROJECT_ID", "proj")
    monkeypatch.setattr(load_bq, "_data_dir", lambda: tmp_path)

    with pytest.raises(SystemExit, match="feature_emb_a.csv"):
        load_bq.run()


def test_insert_sql_uses_project_fqn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_emb_a(tmp_path)
    _write_emb_b(tmp_path)

    fake = FakeBQClient()
    monkeypatch.setattr("app.data.load_bq.bigquery.Client", lambda *a, **k: fake)
    monkeypatch.setattr("app.config.PROJECT_ID", "myproject")
    monkeypatch.setattr(load_bq, "_data_dir", lambda: tmp_path)

    load_bq.run()

    for sql in fake.queries:
        assert "myproject.feature_mart.property_features_daily" in sql
