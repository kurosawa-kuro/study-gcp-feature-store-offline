"""app.data.seed_csv — CSV 生成の内容を検証する。"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from app.data import seed_csv


def test_run_creates_two_csvs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_csv, "_data_dir", lambda: tmp_path)
    seed_csv.run()
    assert (tmp_path / "feature_emb_a.csv").exists()
    assert (tmp_path / "feature_emb_b.csv").exists()


def test_emb_a_csv_schema_and_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_csv, "_data_dir", lambda: tmp_path)
    seed_csv.run()

    rows = list(csv.DictReader((tmp_path / "feature_emb_a.csv").open(encoding="utf-8")))
    assert len(rows) == 5
    assert rows[0]["embedding_source"] == "emb_a"
    assert set(rows[0].keys()) == set(seed_csv.EMB_A_COLS)
    # emb_b 列は含まない
    assert "emb_b_inquiry_rate" not in rows[0]
    # property_id が p001〜p005
    pids = [r["property_id"] for r in rows]
    assert pids == ["p001", "p002", "p003", "p004", "p005"]


def test_emb_b_csv_schema_and_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_csv, "_data_dir", lambda: tmp_path)
    seed_csv.run()

    rows = list(csv.DictReader((tmp_path / "feature_emb_b.csv").open(encoding="utf-8")))
    assert len(rows) == 5
    assert rows[0]["embedding_source"] == "emb_b"
    assert set(rows[0].keys()) == set(seed_csv.EMB_B_COLS)
    # emb_a 列は含まない
    assert "emb_a_ctr" not in rows[0]


def test_common_features_consistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_csv, "_data_dir", lambda: tmp_path)
    seed_csv.run()

    rows_a = {r["property_id"]: r for r in csv.DictReader((tmp_path / "feature_emb_a.csv").open())}
    rows_b = {r["property_id"]: r for r in csv.DictReader((tmp_path / "feature_emb_b.csv").open())}

    for pid in ("p001", "p002", "p003", "p004", "p005"):
        for col in ("rent", "walk_min", "age_years", "area_m2"):
            assert rows_a[pid][col] == rows_b[pid][col], f"{pid}.{col} mismatch"
