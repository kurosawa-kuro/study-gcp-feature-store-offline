"""batch-read-offline — BigQuery から特徴量を取得し stdout + GCS JSONL に書き出す。

Feature Store の Feature Group / Feature として管理された BigQuery 特徴量を
Cloud Run Job として downstream batch で取得・確認する。

出力:
  - stdout: [offline-feature][emb_a/emb_b] property_id=... ... (Cloud Logging が受信)
  - GCS:    gs://{GCS_BUCKET}/offline-batch/{YYYYMMDD}/emb_{a|b}/result.jsonl
            (Cloud Logging が見づらい場合の代替参照用)
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from google.cloud import bigquery, storage

import app.config as cfg

_EMB_A_COLS = [
    "property_id",
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "emb_a_ctr",
    "emb_a_fav_rate",
    "emb_a_semantic_score",
]

_EMB_B_COLS = [
    "property_id",
    "rent",
    "walk_min",
    "age_years",
    "area_m2",
    "emb_b_inquiry_rate",
    "emb_b_collab_score",
    "emb_b_engagement",
]

_SQL_EMB_A = """\
SELECT
  property_id,
  rent,
  walk_min,
  age_years,
  area_m2,
  emb_a_ctr,
  emb_a_fav_rate,
  emb_a_semantic_score
FROM `{project}.{dataset}.{table}`
WHERE event_date = CURRENT_DATE("Asia/Tokyo")
  AND embedding_source = 'emb_a'
ORDER BY property_id
"""

_SQL_EMB_B = """\
SELECT
  property_id,
  rent,
  walk_min,
  age_years,
  area_m2,
  emb_b_inquiry_rate,
  emb_b_collab_score,
  emb_b_engagement
FROM `{project}.{dataset}.{table}`
WHERE event_date = CURRENT_DATE("Asia/Tokyo")
  AND embedding_source = 'emb_b'
ORDER BY property_id
"""


def _fetch(client: bigquery.Client, sql: str, cols: list[str]) -> list[dict[str, Any]]:
    return [{c: row[c] for c in cols} for row in client.query(sql).result()]


def _log_rows(rows: list[dict[str, Any]], source: str) -> None:
    for row in rows:
        parts = " ".join(f"{k}={v}" for k, v in row.items())
        print(f"[offline-feature][{source}] {parts}")


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _upload_gcs(
    project_id: str,
    bucket_name: str,
    local_path: Path,
    blob_name: str,
) -> None:
    bucket = storage.Client(project=project_id).bucket(bucket_name)
    bucket.blob(blob_name).upload_from_filename(str(local_path))
    print(f"==> uploaded gs://{bucket_name}/{blob_name}")


def run() -> None:
    project_id = cfg.PROJECT_ID
    if not project_id:
        project_id = os.environ.get("PROJECT_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")

    bucket_name = cfg.GCS_BUCKET
    if not bucket_name:
        bucket_name = os.environ.get("GCS_BUCKET", "")
    if not bucket_name:
        raise SystemExit("[error] GCS_BUCKET is empty")

    today = date.today().strftime("%Y%m%d")
    bq_client = bigquery.Client(project=project_id)

    tmpl_args = dict(project=project_id, dataset=cfg.DATASET, table=cfg.TABLE)

    for source, sql_tmpl, cols in [
        ("emb_a", _SQL_EMB_A, _EMB_A_COLS),
        ("emb_b", _SQL_EMB_B, _EMB_B_COLS),
    ]:
        sql = sql_tmpl.format(**tmpl_args)
        rows = _fetch(bq_client, sql, cols)

        if not rows:
            print(f"[warn] {source}: 0 rows (load-bq を先に実行したか確認)")
            continue

        print(f"==> {source}: {len(rows)} rows")
        _log_rows(rows, source)

        local_path = Path(f"/tmp/result_{source}_{today}.jsonl")
        _write_jsonl(rows, local_path)

        blob_name = f"{cfg.GCS_PREFIX}/{today}/{source}/result.jsonl"
        _upload_gcs(project_id, bucket_name, local_path, blob_name)

    print("==> batch-read-offline complete")
