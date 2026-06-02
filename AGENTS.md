# AGENTS.md

このファイルは、このリポジトリで作業するエージェント向けの作業メモです。詳細な背景や仕様は [CLAUDE.md](CLAUDE.md) と [docs/01_仕様書.md](docs/01_仕様書.md) を参照してください。

## プロジェクト概要

不動産物件のサンプルデータを題材に、BigQuery に蓄積した特徴量を Vertex AI Feature Store の Feature Group / Feature として登録し、Python batch からオフライン特徴量として取得・検証する学習用プロジェクトです。

主目的は次の責務分離を実機で理解することです。

- BigQuery: 特徴量データの実体、加工、履歴保持
- Vertex AI Feature Store: 特徴量の管理、メタデータ、参照レイヤー
- Python batch: CSV 生成、BigQuery ロード、Feature Store 登録、Offline batch 取得

Feature Store の利用範囲は Offline のみです。Online Store / Feature View / sync / online serving はスコープ外です。

## 現状

2026-06-02 時点では仕様策定済み・実装前です。README.md と Makefile はまだ空に近い状態のため、実装時はドキュメントの仕様を canonical として扱ってください。

## 想定構成

仕様上の予定構成は次の通りです。新規ファイルを追加する場合は、まずこの構成に寄せてください。

```text
app/
  main.py
  config.py
  data/
    seed_csv.py
    load_bq.py
  feature_store/
    register.py
  batch/
    read_offline.py
infra/
  terraform/
    bigquery.tf
    feature_store.tf
    iam.tf
  Dockerfile
data/
  feature.csv
docs/
  01_仕様書.md
  02_実装カタログ.md
  03_運用.md
Makefile
```

## 主要コマンド

実装後に想定している Python batch コマンドです。

```bash
python -m app.main seed-csv
python -m app.main load-bq
python -m app.main register-fs
python -m app.main batch-read-offline
```

Makefile ターゲットは次を想定しています。

```bash
make tf-init
make check
make deploy
make seed-csv
make load-bq
make register-fs
make batch-read
make destroy
```

`make check` は、GCP リソースへ変更を加えない検証として `ruff`、`terraform fmt -check`、`terraform validate` を行う想定です。

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
- [docs/01_仕様書.md](docs/01_仕様書.md): 仕様
- [docs/02_実装カタログ.md](docs/02_実装カタログ.md): 実装候補・カタログ
- [docs/03_運用.md](docs/03_運用.md): 運用手順
