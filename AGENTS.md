# AGENTS.md

このファイルは、このリポジトリで作業するエージェント向けの作業メモです。詳細な背景や仕様は [CLAUDE.md](CLAUDE.md) と [docs/02_仕様書.md](docs/02_仕様書.md) を参照してください。

## プロジェクト概要

不動産物件のサンプルデータを題材に、BigQuery に蓄積した特徴量を Vertex AI Feature Store の Feature Group / Feature として登録し、Python batch からオフライン特徴量として取得・検証する学習用プロジェクトです。

主目的は次の責務分離を実機で理解することです。

- BigQuery: 特徴量データの実体、加工、履歴保持
- Vertex AI Feature Store: 特徴量の管理、メタデータ、参照レイヤー
- Python batch: CSV 生成、BigQuery ロード、Feature Store 登録、Offline batch 取得

Feature Store の利用範囲は Offline のみです。Online Store / Feature View / sync / online serving はスコープ外です。

## 現状

**実装済み・GCP 動作検証完了 (2026-06-02 / mlops-dev-a)**。

確認済み事項:
- Feature Group ID はアンダースコア必須: `fg_property_emb_a` / `fg_property_emb_b`
- Cloud Run jobs 全 4 件成功 (seed-csv / load-bq / register-fs / batch-read)
- batch-read-offline: Feature Store REST API で BQ source + Feature ID を解決し BigQuery offline read

## 実際の構成

```text
src/
  app/
    main.py
    config.py
    common/auth.py
    data/seed_csv.py / load_bq.py
    feature_store/register.py
    batch/read_offline.py
  data/
    feature_emb_a.csv / feature_emb_b.csv
infra/terraform/main.tf / providers.tf / variables.tf / outputs.tf
infra/Dockerfile
tests/
  conftest.py / test_*.py (36 tests)
docs/
Makefile / pyproject.toml
```

## 主要コマンド

```bash
python -m app.main seed-csv
python -m app.main load-bq
python -m app.main register-fs
python -m app.main batch-read-offline
```

```bash
make tf-init
make check        # ruff + terraform fmt -check + validate (GCP 不要)
make deploy       # AR apply → build-push → terraform apply
make seed-csv / load-bq / register-fs / batch-read
make verify-bq / verify-gcs
make destroy
```

## 実装方針

- Python は 3.12 以上を前提にします。
- `pyproject.toml` の Ruff 設定に合わせ、line length は 100、lint は `E`, `F`, `I`, `UP` を基準にします。
- BigQuery テーブル `feature_mart.property_features_daily` を特徴量の実体として扱います。
- `property_id` は Entity ID、`embedding_source` は `emb_a` / `emb_b` のリネージュ列として扱います。
- Feature Group は `fg_property_emb_a` と `fg_property_emb_b` の 2 系統に分けます。
- BigQuery View を Feature Group の source として使い、各 Feature Group には共通特徴量 4 個と系統固有特徴量 3 個を登録します。
- Feature Store 関連の CLI 確認は、`gcloud ai feature-*` に依存せず REST API で確認する想定です。

## 採用しないもの

このプロジェクトでは次を実装しないでください。

- Feature View
- Feature View sync
- Feature Online Store
- `fetchFeatureValues` を使う online 取得
- Redis 連携
- リアルタイム serving
- 推論 Endpoint
- Cloud Composer / Dataform / Vector Search / KServe / Elasticsearch
- skew monitoring

目的は BigQuery 上の特徴量を Feature Store で管理し、offline batch で利用する流れに限定することです。

## 作業規約

- ドキュメント、コミットメッセージ、PR タイトル、ユーザー向け応答は日本語を canonical とします。
- コード内 identifier は英語で統一します。
- `/home/ubuntu/repos` 配下には複数の学習用プロジェクトがあります。同名ファイルがあり得るため、作業前に必ずパスを確認してください。
- このリポジトリ直下が git repository です。`/home/ubuntu/repos` 全体を git repository として扱わないでください。
- 既存の未コミット変更はユーザー作業の可能性があるため、明示依頼なしに revert しないでください。
- GCP や Terraform を操作する変更は、可能な限り plan / dry-run / check を先に行い、実リソース変更の有無を明確にしてください。

## 参照先

- [CLAUDE.md](CLAUDE.md): プロジェクト背景、詳細なデータフロー、コマンド、スコープ
- [docs/02_仕様書.md](docs/02_仕様書.md): 仕様
- [docs/03_実装カタログ.md](docs/03_実装カタログ.md): 実装候補・カタログ
- [docs/05_運用.md](docs/05_運用.md): 運用手順
