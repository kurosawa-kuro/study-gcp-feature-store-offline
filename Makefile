# study-gcp-feature-store-offline — BigQuery + Feature Store Offline 学習用
#
# 標準フロー:
#   make tf-init
#   make deploy         # AR apply → build-push → terraform apply
#   make seed-csv       # Cloud Run job: feature_emb_{a,b}.csv 生成
#   make load-bq        # Cloud Run job: BigQuery ロード
#   make register-fs    # Cloud Run job: BQ View + Feature Group / Feature 登録
#   make batch-read     # Cloud Run job: offline batch 取得 → stdout + GCS JSONL
#   make verify-bq      # bq query で BQ テーブル確認
#   make verify-gcs     # GCS の result.jsonl を確認
#   make destroy        # 全リソース撤去

PROJECT_ID ?= mlops-dev-a
REGION     ?= asia-northeast1
AR_REPO    ?= feature-store-offline
IMAGE_TAG  ?= latest
IMAGE      := $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(AR_REPO)/feature-store-offline-job:$(IMAGE_TAG)

TF_DIR := infra/terraform
TF     := terraform -chdir=$(TF_DIR)
TF_VARS := -var=project_id=$(PROJECT_ID) -var=region=$(REGION) -var=image=$(IMAGE)

.PHONY: help
help: ## このヘルプを表示
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- Terraform ----
.PHONY: tf-init
tf-init: ## terraform init
	$(TF) init

.PHONY: tf-validate
tf-validate: ## terraform fmt -check + validate (offline)
	$(TF) fmt -check -recursive
	$(TF) validate

.PHONY: tf-apply-ar
tf-apply-ar: ## Artifact Registry repo だけ先に apply (image push の前提)
	$(TF) apply $(TF_VARS) -target=google_artifact_registry_repository.repo -auto-approve

.PHONY: tf-apply
tf-apply: ## 全リソースを apply
	$(TF) apply $(TF_VARS) -auto-approve

# ---- Container ----
.PHONY: build-push
build-push: ## job image を AR へ build & push
	gcloud auth configure-docker $(REGION)-docker.pkg.dev --quiet
	docker buildx build --platform linux/amd64 -f infra/Dockerfile -t $(IMAGE) --push .

# ---- 一括デプロイ (image 存在順序を担保) ----
.PHONY: deploy
deploy: tf-apply-ar build-push tf-apply ## AR apply → build-push → 残り apply

# ---- Cloud Run jobs 実行 ----
.PHONY: seed-csv
seed-csv: ## seed-csv job 実行 (feature_emb_{a,b}.csv 生成)
	gcloud run jobs execute seed-csv --project=$(PROJECT_ID) --region=$(REGION) --wait

.PHONY: load-bq
load-bq: ## load-bq job 実行 (BigQuery へロード)
	gcloud run jobs execute load-bq --project=$(PROJECT_ID) --region=$(REGION) --wait

.PHONY: register-fs
register-fs: ## register-fs job 実行 (BQ View + Feature Group / Feature 登録)
	gcloud run jobs execute register-fs --project=$(PROJECT_ID) --region=$(REGION) --wait

.PHONY: batch-read
batch-read: ## batch-read job 実行 (offline batch 取得 → stdout + GCS JSONL)
	gcloud run jobs execute batch-read --project=$(PROJECT_ID) --region=$(REGION) --wait

# ---- 検証 ----
.PHONY: verify-bq
verify-bq: ## BQ テーブルで embedding_source 別行数確認
	bq query --project_id=$(PROJECT_ID) --nouse_legacy_sql \
		'SELECT embedding_source, COUNT(*) AS cnt FROM `$(PROJECT_ID).feature_mart.property_features_daily` GROUP BY 1 ORDER BY 1'

.PHONY: verify-gcs
verify-gcs: ## GCS の result.jsonl を確認
	@BUCKET=$(PROJECT_ID)-feature-offline-$(REGION); \
	gcloud storage ls gs://$$BUCKET/offline-batch/ 2>/dev/null || echo "[info] GCS に出力なし (batch-read を先に実行)"; \
	for path in $$(gcloud storage ls "gs://$$BUCKET/offline-batch/**/*.jsonl" 2>/dev/null); do \
		echo "==> $$path"; \
		gcloud storage cat $$path | head -3; \
	done

# ---- ローカル検証 (GCP に触れない) ----
.PHONY: check
check: ## ruff + terraform validate (GCP 不要)
	uv run ruff check src/app
	uv run ruff format --check src/app
	$(TF) fmt -check -recursive
	$(TF) validate

# ---- teardown ----
.PHONY: destroy
destroy: ## 全リソース撤去
	$(TF) destroy $(TF_VARS) -auto-approve
