"""プロジェクト共通設定。環境変数 + デフォルト値を一箇所で管理する。"""

from __future__ import annotations

import os

PROJECT_ID = os.environ.get("PROJECT_ID", "")
REGION = os.environ.get("REGION", "asia-northeast1")

DATASET = "feature_mart"
TABLE = "property_features_daily"
VIEW_EMB_A = "v_property_features_emb_a"
VIEW_EMB_B = "v_property_features_emb_b"

FG_EMB_A = "fg-property-emb-a"
FG_EMB_B = "fg-property-emb-b"

GCS_BUCKET = os.environ.get("GCS_BUCKET", "")
GCS_PREFIX = "offline-batch"
