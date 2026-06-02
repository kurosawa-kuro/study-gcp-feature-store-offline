# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクトの目的

不動産物件のサンプルデータを題材に、**BigQuery に蓄積した特徴量を Vertex AI Feature Store (Feature Group / Feature) に登録し、Python batch からオフライン特徴量として取得・検証する**学習用プロジェクト。詳細仕様は [docs/02_仕様書.md](docs/02_仕様書.md) を参照。

学習対象は「BigQuery = 特徴量データの実体・加工場所」「Feature Store = 特徴量の管理・メタデータ・参照レイヤー」という責務分離を実機で理解すること。**Feature Store の利用範囲は Offline のみ**。Online Store / Feature View / sync は本プロジェクトのスコープ外。

## 現状

**実装済み・GCP 動作検証完了 (2026-06-02)**。仕様は [docs/02_仕様書.md](docs/02_仕様書.md)、運用は [docs/05_運用.md](docs/05_運用.md)。

## アーキテクチャ (データフロー)

```
feature_emb_a.csv / feature_emb_b.csv
    ↓
Python batch (seed-csv / load-bq)
    ↓
BigQuery
  feature_mart.property_features_daily  (embedding_source 列でリネージュ管理)
    ├─ v_property_features_emb_a (BQ View)
    └─ v_property_features_emb_b (BQ View)
    ↓
Vertex AI Feature Store
  ├─ Feature Group  fg_property_emb_a  … emb_a 固有スコア + 共通特徴量
  │    └─ Feature × 7  rent / walk_min / age_years / area_m2 / emb_a_ctr / emb_a_fav_rate / emb_a_semantic_score
  └─ Feature Group  fg_property_emb_b  … emb_b 固有スコア + 共通特徴量
       └─ Feature × 7  rent / walk_min / age_years / area_m2 / emb_b_inquiry_rate / emb_b_collab_score / emb_b_engagement
    ↓
Python batch (batch-read-offline / Cloud Run Job)
    Feature Store REST API で Feature Group / Feature を取得し BQ View・Feature ID を解決
    BigQuery offline read (動的 SELECT)
    ↓
stdout ログ (Cloud Logging) + GCS JSONL (property_id ごとの特徴量取得結果)
```

**採用スキーマ** (`feature_mart.property_features_daily`): `event_date` (DATE/partition), `feature_timestamp` (TIMESTAMP), `property_id` (STRING / **Entity ID** / clustering key 1), `embedding_source` (STRING / `'emb_a'`or`'emb_b'` / clustering key 2 / **lineage 列**), `rent` (INT64), `walk_min` (INT64), `age_years` (INT64), `area_m2` (FLOAT64), `emb_a_ctr` (FLOAT64), `emb_a_fav_rate` (FLOAT64), `emb_a_semantic_score` (FLOAT64), `emb_b_inquiry_rate` (FLOAT64), `emb_b_collab_score` (FLOAT64), `emb_b_engagement` (FLOAT64)。Feature Group は emb_a/emb_b の BQ View 別に 2 つ登録し、各 Feature は 7 個。入力は `feature_emb_a.csv` / `feature_emb_b.csv` の 2 ファイル。

## 構成

実際のファイル構成:

```
src/
  app/
    main.py               # エントリポイント / dispatch table
    config.py
    common/
      auth.py             # ADC access token 取得
    data/
      seed_csv.py         # feature_emb_a.csv / feature_emb_b.csv 生成
      load_bq.py          # CSV → BigQuery ロード
    feature_store/
      register.py         # BQ View + Feature Group / Feature 登録
    batch/
      read_offline.py     # Feature Store REST API → BigQuery offline read → ログ出力
  data/
    feature_emb_a.csv
    feature_emb_b.csv
infra/
  terraform/
    main.tf               # 全リソース (BQ / Feature Store / SA / GCS / Cloud Run)
    providers.tf
    variables.tf
    outputs.tf
  Dockerfile
docs/
  01_Feature-store入門.md
  02_仕様書.md
  03_実装カタログ.md
  04_重要コード説明.md
  05_運用.md
tests/
  conftest.py
  test_main.py / test_seed_csv.py / test_load_bq.py / test_register.py / test_read_offline.py
Makefile
pyproject.toml
```

## コマンド

```bash
# Python batch (Cloud Run Jobs またはローカル実行)
python -m app.main seed-csv            # feature_emb_a.csv / feature_emb_b.csv を作成
python -m app.main load-bq             # CSV を BigQuery へロード
python -m app.main register-fs         # BQ View + Feature Group / Feature を登録
python -m app.main batch-read-offline  # Feature Store REST API → BigQuery offline read → ログ出力

# Makefile ターゲット
make tf-init        # terraform init
make check          # ruff + terraform fmt -check + validate (GCP に触れない)
make deploy         # AR apply → image build/push → terraform apply
make seed-csv       # Cloud Run job: CSV 生成
make load-bq        # Cloud Run job: BigQuery ロード
make register-fs    # Cloud Run job: Feature Group / Feature 登録 (Terraform 済みは 409 skip)
make batch-read     # Cloud Run job: Feature Store → BigQuery offline read → stdout + GCS
make verify-bq      # embedding_source 別行数確認
make verify-gcs     # GCS JSONL 確認
make destroy        # 全リソース撤去
```

## 意図的に採用しないもの

```text
Feature View
Feature View sync
Feature Online Store
fetchFeatureValues (Online)
Redis 連携
リアルタイム serving
推論 Endpoint
Cloud Composer / Dataform / Vector Search / KServe / Elasticsearch
skew monitoring
```

理由: 既存システムではオンライン低レイテンシ配信を Redis が担っており、Feature Store Online を追加しても責務重複・障害点増加・運用コスト増となるため。今回の導入価値は**BigQuery 上の特徴量を Feature Store で管理しオフライン batch 利用できること**に限定する。

## 検証ステップ

①BigQuery 側 (dataset/table/投入/SQL) → ②Feature Store 側 (Feature Group / Feature 登録) → ③CLI 検証 (`bq` + Vertex AI REST) → ④GCP UI 検証 (コンソールでメタデータ確認)。

> gcloud SDK 563.x には `gcloud ai feature-*` が無いため Feature Store の CLI 確認は REST API を直接呼ぶ想定。

## ワークスペース規約 (継承)

このリポジトリは `/home/ubuntu/repos` multi-project workspace 配下。ルートの [/home/ubuntu/repos/CLAUDE.md](../CLAUDE.md) も参照。特に:

- **ドキュメント・コミットメッセージ・PR タイトルは日本語が canonical**。コード内 identifier は英語、ユーザーへの応答は日本語。
- `gcloud *` / `bq *` / `terraform *` 等は workspace の `.claude/settings.json` allowlist に登録済みで、この project でもそのまま使える。
- 実装が増えたら他 project ([study-gcp-search-mlops-gke/](../study-gcp-search-mlops-gke/) 等) の Feature Store 実装を参照可能。同名ファイルが複数 project に存在しうるので path を必ず確認する。

git: この project 直下で `git init` 済み想定 (`/home/ubuntu/repos` 自体は git repo ではない)。
