# study-gcp-feature-store-offline

不動産物件のサンプル特徴量を題材に、**BigQuery × Vertex AI Feature Store (Offline) の責務分離**を実機で理解する学習用プロジェクト。

---

## 学習ゴール

| レイヤー | 責務 |
|---|---|
| BigQuery | 特徴量の物理保存・SQL 検証・batch read |
| Feature Store (Feature Group / Feature) | BQ View と Feature ID の registry / metadata 管理 |
| Python batch | Feature Store REST API で BQ View・Feature ID を解決し BigQuery offline read |

**Feature Store Online / Online Store / Feature View / sync / fetchFeatureValues は採用しない。** オンライン serving は既存 Redis が担う。

---

## ステータス

**実装済み・GCP 動作検証完了 (2026-06-02)**

確認済み:
- Feature Store REST API で Feature Group を GET → BigQuery source URI を解決
- Feature Store REST API で Feature を LIST → SELECT column を動的生成
- BigQuery offline read → 5 物件 × emb_a / emb_b の特徴量取得
- GCS JSONL 出力 (`offline-batch/20260602/emb_a|b/result.jsonl`)

---

## アーキテクチャ

```
feature_emb_a.csv / feature_emb_b.csv
        ↓
  Python batch (seed-csv / load-bq)
        ↓
  BigQuery: feature_mart.property_features_daily
    (partition: event_date / clustering: property_id, embedding_source)
        ↓
  BQ View emb_a ─── Feature Group fg_property_emb_a ── Feature × 7
  BQ View emb_b ─── Feature Group fg_property_emb_b ── Feature × 7
        ↓
  Python batch (batch-read-offline / Cloud Run Job)
    Feature Store REST API → BQ source URI + Feature ID 取得
    BigQuery offline read
        ↓
  stdout (Cloud Logging) + GCS JSONL
```

---

## クイックスタート

```bash
# 1. Terraform 初期化
make tf-init

# 2. インフラ一括デプロイ (AR → Docker build/push → Terraform apply)
make deploy

# 3. Cloud Run Jobs を順番に実行
make seed-csv      # CSV 生成 (image 同梱の初期データを再生成)
make load-bq       # BigQuery ロード
make register-fs   # BQ View + Feature Group / Feature 登録
make batch-read    # Feature Store → BQ offline read → stdout + GCS

# 4. 検証
make verify-bq     # embedding_source 別件数確認
make verify-gcs    # GCS JSONL 確認

# 5. 撤去
make destroy
```

---

## 仕様・実装・運用

| ドキュメント | 内容 |
|---|---|
| [docs/01_Feature-store入門.md](docs/01_Feature-store入門.md) | Feature Store Offline / BigQuery 連携の入門 |
| [docs/02_仕様書.md](docs/02_仕様書.md) | 方針・スキーマ・コマンド仕様 |
| [docs/03_実装カタログ.md](docs/03_実装カタログ.md) | Terraform リソース・Python 実装・設計判断 |
| [docs/04_重要コード説明.md](docs/04_重要コード説明.md) | 重要コードとメソッド関係図 |
| [docs/05_運用.md](docs/05_運用.md) | デプロイ・実行・検証・撤去手順 |
| [CLAUDE.md](CLAUDE.md) | Claude Code 向け作業ガイド |
