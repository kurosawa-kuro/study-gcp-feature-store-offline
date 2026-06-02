"""batch-read-offline — Feature Store REST API で Feature Group / Feature 定義を取得し
BigQuery offline source から特徴量を読み取る。

フロー:
  1. Feature Group GET  → BigQuery source URI + entity_id_columns を取得
  2. Feature LIST       → Feature ID 一覧を取得
  3. SELECT 文を動的生成  → column 直書きなし
  4. BigQuery クエリ実行 → 結果を stdout + GCS JSONL へ出力

Feature Group が存在しない場合はバッチ全体を失敗させる。
Feature View / Online Store / sync / fetchFeatureValues は一切使用しない。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from google.cloud import bigquery, storage

import app.config as cfg
from app.common.auth import access_token

# ---------------------------------------------------------------------------
# Feature Store REST helpers
# ---------------------------------------------------------------------------


def _request(url: str, *, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read().decode() or "{}")


def _get_feature_group(project: str, region: str, token: str, fg_id: str) -> dict[str, Any]:
    url = (
        f"https://{region}-aiplatform.googleapis.com/v1"
        f"/projects/{project}/locations/{region}/featureGroups/{fg_id}"
    )
    try:
        return _request(url, token=token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(
                f"[error] Feature Group が見つかりません: {fg_id}"
                " (register-fs を先に実行してください)"
            ) from exc
        raise


def _list_features(project: str, region: str, token: str, fg_id: str) -> list[str]:
    url = (
        f"https://{region}-aiplatform.googleapis.com/v1"
        f"/projects/{project}/locations/{region}/featureGroups/{fg_id}/features"
    )
    try:
        resp = _request(url, token=token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(f"[error] Feature Group が見つかりません: {fg_id}") from exc
        raise
    features = resp.get("features", [])
    if not features:
        raise SystemExit(
            f"[error] Feature Group {fg_id}: features が登録されていません"
            " (register-fs を先に実行してください)"
        )
    return [f["name"].split("/")[-1] for f in features]


def _bq_ref(input_uri: str) -> str:
    """'bq://project.dataset.view' → 'project.dataset.view'"""
    return input_uri.removeprefix("bq://")


def _build_sql(bq_ref: str, entity_id_cols: list[str], feature_ids: list[str]) -> str:
    cols = ", ".join(entity_id_cols + feature_ids)
    return (
        f"SELECT {cols}\n"
        f"FROM `{bq_ref}`\n"
        f'WHERE event_date = CURRENT_DATE("Asia/Tokyo")\n'
        f"ORDER BY property_id"
    )


# ---------------------------------------------------------------------------
# BQ / GCS helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


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

    region = cfg.REGION
    today = date.today().strftime("%Y%m%d")
    token = access_token()
    bq_client = bigquery.Client(project=project_id)

    for source, fg_id in [
        ("emb_a", cfg.FG_EMB_A),
        ("emb_b", cfg.FG_EMB_B),
    ]:
        print(f"==> [{source}] Feature Group: {fg_id}")

        # Step 1: Feature Group から BigQuery source URI を取得
        fg = _get_feature_group(project_id, region, token, fg_id)
        bq_source_uri = fg["bigQuery"]["bigQuerySource"]["inputUri"]
        entity_id_cols = fg["bigQuery"].get("entityIdColumns", ["property_id"])
        print(f"==> [{source}] BQ source: {bq_source_uri}")

        # Step 2: Feature 一覧を取得
        feature_ids = _list_features(project_id, region, token, fg_id)
        print(f"==> [{source}] Features ({len(feature_ids)}): {feature_ids}")

        # Step 3: SELECT 文を動的生成して BigQuery クエリ実行
        bq_ref = _bq_ref(bq_source_uri)
        all_cols = entity_id_cols + feature_ids
        sql = _build_sql(bq_ref, entity_id_cols, feature_ids)
        rows = _fetch(bq_client, sql, all_cols)

        if not rows:
            print(f"[warn] {source}: 0 rows (load-bq を先に実行したか確認)")
            continue

        print(f"==> {source}: {len(rows)} rows")
        _log_rows(rows, source)

        local_path = Path(f"/tmp/result_{source}_{today}.jsonl")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        _write_jsonl(rows, local_path)

        blob_name = f"{cfg.GCS_PREFIX}/{today}/{source}/result.jsonl"
        _upload_gcs(project_id, bucket_name, local_path, blob_name)

    print("==> batch-read-offline complete")
