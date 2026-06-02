"""register-fs — BQ View 作成 + Feature Group / Feature 登録。

処理順:
  1. BQ View v_property_features_emb_a / _emb_b を CREATE OR REPLACE
  2. Feature Group fg-property-emb-a / fg-property-emb-b を Vertex AI REST で作成
  3. 各 Feature Group に Feature × 7 を登録

Feature Group と Feature の作成は LRO (Long-Running Operation) が返るため、
DONE になるまで polling する。既存リソースへの再実行は 409 を warn+skip して冪等に動く。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from google.cloud import bigquery

import app.config as cfg
from app.common.auth import access_token

_FEATURES_EMB_A = [
    {"id": "rent", "desc": "Monthly rent (共通特徴量)"},
    {"id": "walk_min", "desc": "Walking minutes to nearest station (共通特徴量)"},
    {"id": "age_years", "desc": "Property age in years (共通特徴量)"},
    {"id": "area_m2", "desc": "Floor area in square meters (共通特徴量)"},
    {"id": "emb_a_ctr", "desc": "CTR predicted by text-attribute embedding model"},
    {"id": "emb_a_fav_rate", "desc": "Favorite rate from text-attribute embedding"},
    {"id": "emb_a_semantic_score", "desc": "Semantic similarity score (emb_a specific)"},
]

_FEATURES_EMB_B = [
    {"id": "rent", "desc": "Monthly rent (共通特徴量)"},
    {"id": "walk_min", "desc": "Walking minutes to nearest station (共通特徴量)"},
    {"id": "age_years", "desc": "Property age in years (共通特徴量)"},
    {"id": "area_m2", "desc": "Floor area in square meters (共通特徴量)"},
    {"id": "emb_b_inquiry_rate", "desc": "Inquiry rate from behavioral-log embedding"},
    {"id": "emb_b_collab_score", "desc": "Collaborative filtering score (emb_b specific)"},
    {"id": "emb_b_engagement", "desc": "Engagement score from behavioral-log embedding"},
]


# ---------------------------------------------------------------------------
# BQ View
# ---------------------------------------------------------------------------

_VIEW_EMB_A_SQL = """\
SELECT
  event_date,
  feature_timestamp,
  property_id,
  rent,
  walk_min,
  age_years,
  area_m2,
  emb_a_ctr,
  emb_a_fav_rate,
  emb_a_semantic_score
FROM `{project}.{dataset}.{table}`
WHERE embedding_source = 'emb_a'
"""

_VIEW_EMB_B_SQL = """\
SELECT
  event_date,
  feature_timestamp,
  property_id,
  rent,
  walk_min,
  age_years,
  area_m2,
  emb_b_inquiry_rate,
  emb_b_collab_score,
  emb_b_engagement
FROM `{project}.{dataset}.{table}`
WHERE embedding_source = 'emb_b'
"""


def _create_views(client: bigquery.Client, project_id: str) -> None:
    for view_id, sql_tmpl in [
        (cfg.VIEW_EMB_A, _VIEW_EMB_A_SQL),
        (cfg.VIEW_EMB_B, _VIEW_EMB_B_SQL),
    ]:
        sql = sql_tmpl.format(project=project_id, dataset=cfg.DATASET, table=cfg.TABLE)
        view_ref = f"{project_id}.{cfg.DATASET}.{view_id}"
        table = bigquery.Table(view_ref)
        table.view_query = sql
        client.create_table(table, exists_ok=True)
        print(f"==> BQ View 作成/更新: {view_id}")


# ---------------------------------------------------------------------------
# Vertex AI REST helpers
# ---------------------------------------------------------------------------


def _request(
    url: str,
    *,
    method: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.loads(resp.read().decode() or "{}")


def _poll_lro(operation_name: str, token: str, region: str, timeout: int = 300) -> None:
    """LRO が DONE になるまで polling する。"""
    url = f"https://{region}-aiplatform.googleapis.com/v1/{operation_name}"
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = _request(url, method="GET", token=token)
        if result.get("done"):
            if "error" in result:
                raise RuntimeError(f"LRO failed: {result['error']}")
            return
        time.sleep(5)
    raise TimeoutError(f"LRO timed out after {timeout}s: {operation_name}")


def _create_feature_group(
    project_id: str, region: str, token: str, fg_id: str, view_id: str
) -> None:
    base = f"https://{region}-aiplatform.googleapis.com/v1"
    url = f"{base}/projects/{project_id}/locations/{region}/featureGroups?featureGroupId={fg_id}"
    payload = {
        "bigQuery": {
            "bigQuerySource": {"inputUri": f"bq://{project_id}.{cfg.DATASET}.{view_id}"},
            "entityIdColumns": ["property_id"],
        }
    }
    try:
        op = _request(url, method="POST", token=token, payload=payload)
        print(f"==> Feature Group 作成中: {fg_id} (LRO: {op.get('name', '')})")
        _poll_lro(op["name"], token, region)
        print(f"==> Feature Group 完了: {fg_id}")
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            print(f"==> Feature Group 既存 (skip): {fg_id}")
        else:
            raise


def _create_feature(
    project_id: str, region: str, token: str, fg_id: str, feature_id: str, desc: str
) -> None:
    base = f"https://{region}-aiplatform.googleapis.com/v1"
    url = (
        f"{base}/projects/{project_id}/locations/{region}"
        f"/featureGroups/{fg_id}/features?featureId={feature_id}"
    )
    try:
        op = _request(url, method="POST", token=token, payload={"description": desc})
        _poll_lro(op["name"], token, region)
        print(f"    Feature 登録完了: {fg_id}/{feature_id}")
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            print(f"    Feature 既存 (skip): {fg_id}/{feature_id}")
        else:
            raise


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def run() -> None:
    project_id = cfg.PROJECT_ID
    if not project_id:
        project_id = os.environ.get("PROJECT_ID", "")
    if not project_id:
        raise SystemExit("[error] PROJECT_ID is empty")

    region = cfg.REGION

    print("==> Step 1: BQ View 作成")
    bq_client = bigquery.Client(project=project_id)
    _create_views(bq_client, project_id)

    print("==> Step 2: Feature Group / Feature 登録")
    token = access_token()

    for fg_id, view_id, features in [
        (cfg.FG_EMB_A, cfg.VIEW_EMB_A, _FEATURES_EMB_A),
        (cfg.FG_EMB_B, cfg.VIEW_EMB_B, _FEATURES_EMB_B),
    ]:
        _create_feature_group(project_id, region, token, fg_id, view_id)
        print(f"==> Feature 登録: {fg_id} ({len(features)} 個)")
        for f in features:
            # Feature 作成後にトークンが期限切れの場合を想定して毎回更新
            token = access_token()
            _create_feature(project_id, region, token, fg_id, f["id"], f["desc"])

    print("==> register-fs complete")
