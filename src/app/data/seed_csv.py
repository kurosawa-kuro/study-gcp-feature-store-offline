"""seed-csv — feature_emb_a.csv / feature_emb_b.csv を data/ に生成する。

固定 5 物件のサンプルデータを embedding_source 別ファイルに書き出す。
BigQuery ロード (load-bq) の入力ファイルとなる。
"""

from __future__ import annotations

import csv
from pathlib import Path

EMB_A_COLS = [
    "event_date",
    "feature_timestamp",
    "property_id",
    "embedding_source",
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "emb_a_ctr",
    "emb_a_fav_rate",
    "emb_a_semantic_score",
]

EMB_B_COLS = [
    "event_date",
    "feature_timestamp",
    "property_id",
    "embedding_source",
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "emb_b_inquiry_rate",
    "emb_b_collab_score",
    "emb_b_engagement",
]

_DATE = "2026-06-02"
_TS = "2026-06-02T00:00:00+09:00"

# (property_id, rent, walk_min, age_years, area_m2)
_COMMON: list[tuple[str, int, int, int, float]] = [
    ("p001", 85000, 7, 12, 32.5),
    ("p002", 92000, 5, 8, 28.1),
    ("p003", 110000, 3, 5, 40.2),
    ("p004", 78000, 10, 18, 24.8),
    ("p005", 135000, 6, 3, 55.0),
]

# emb_a 固有スコア (emb_a_ctr, emb_a_fav_rate, emb_a_semantic_score)
_EMB_A_SCORES: list[tuple[float, float, float]] = [
    (0.1200, 0.0300, 0.72),
    (0.1400, 0.0400, 0.68),
    (0.1600, 0.0500, 0.81),
    (0.0900, 0.0200, 0.61),
    (0.1800, 0.0600, 0.88),
]

# emb_b 固有スコア (emb_b_inquiry_rate, emb_b_collab_score, emb_b_engagement)
_EMB_B_SCORES: list[tuple[float, float, float]] = [
    (0.0100, 0.65, 0.40),
    (0.0150, 0.70, 0.45),
    (0.0200, 0.78, 0.55),
    (0.0080, 0.52, 0.30),
    (0.0250, 0.85, 0.62),
]


def _data_dir() -> Path:
    # src/app/data/seed_csv.py → .parent×3 = src/ → data/
    # Docker /app/app/data/seed_csv.py → .parent×3 = /app/ → data/
    candidate = Path(__file__).resolve().parents[2] / "data"
    if candidate.is_dir():
        return candidate
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def run() -> None:
    data_dir = _data_dir()

    path_a = data_dir / "feature_emb_a.csv"
    with path_a.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(EMB_A_COLS)
        for (pid, rent, wm, ay, am), (ctr, fav, sem) in zip(_COMMON, _EMB_A_SCORES):
            w.writerow([_DATE, _TS, pid, "emb_a", rent, wm, ay, am, ctr, fav, sem])
    print(f"==> wrote {len(_COMMON)} rows to {path_a}")

    path_b = data_dir / "feature_emb_b.csv"
    with path_b.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(EMB_B_COLS)
        for (pid, rent, wm, ay, am), (inq, col, eng) in zip(_COMMON, _EMB_B_SCORES):
            w.writerow([_DATE, _TS, pid, "emb_b", rent, wm, ay, am, inq, col, eng])
    print(f"==> wrote {len(_COMMON)} rows to {path_b}")

    print("==> seed-csv complete")
