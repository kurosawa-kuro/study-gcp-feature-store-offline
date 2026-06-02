"""load-bq — feature_emb_a.csv / feature_emb_b.csv を BigQuery にロードする。

冪等性: 当日分を DELETE してから INSERT するため、再実行しても重複しない。
テーブルは Terraform が作成済みの前提。
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

from google.cloud import bigquery

import app.config as cfg

_TABLE_FQN_TMPL = "`{project}.{dataset}.{table}`"

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


def _data_dir() -> Path:
    # src/app/data/load_bq.py → .parent×3 = src/ → data/
    # Docker /app/app/data/load_bq.py → .parent×3 = /app/ → data/
    candidate = Path(__file__).resolve().parents[2] / "data"
    if candidate.is_dir():
        return candidate
    return Path("data")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _val(v: str) -> str:
    """文字列値を SQL リテラルに変換する。空文字は NULL。"""
    v = v.strip()
    if v == "":
        return "NULL"
    try:
        float(v)
        return v
    except ValueError:
        return f"'{v}'"


def _insert(
    client: bigquery.Client, table: str, cols: list[str], rows: list[dict[str, str]]
) -> None:
    col_list = ", ".join(cols)
    value_rows = ",\n      ".join(f"({', '.join(_val(row[c]) for c in cols)})" for row in rows)
    sql = f"INSERT INTO {table}\n      ({col_list})\n    VALUES\n      {value_rows}"
    client.query(sql).result()
    print(f"==> inserted {len(rows)} rows ({cols[3]} source: {rows[0]['embedding_source']})")


def run() -> None:
    project_id = cfg.PROJECT_ID
    if not project_id:
        project_id = os.environ.get("PROJECT_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")

    client = bigquery.Client(project=project_id)
    table = _TABLE_FQN_TMPL.format(project=project_id, dataset=cfg.DATASET, table=cfg.TABLE)
    data_dir = _data_dir()

    print(f"==> delete today's rows from {cfg.DATASET}.{cfg.TABLE}")
    client.query(f'DELETE FROM {table} WHERE event_date = CURRENT_DATE("Asia/Tokyo")').result()

    path_a = data_dir / "feature_emb_a.csv"
    if not path_a.exists():
        raise SystemExit(f"[error] {path_a} が見つかりません (先に seed-csv を実行してください)")
    rows_a = _read_csv(path_a)
    _insert(client, table, EMB_A_COLS, rows_a)

    path_b = data_dir / "feature_emb_b.csv"
    if not path_b.exists():
        raise SystemExit(f"[error] {path_b} が見つかりません (先に seed-csv を実行してください)")
    rows_b = _read_csv(path_b)
    _insert(client, table, EMB_B_COLS, rows_b)

    print(f"==> load-bq complete: {len(rows_a) + len(rows_b)} rows total")
