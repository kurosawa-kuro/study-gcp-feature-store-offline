# =========================================================================
# study-gcp-feature-store-offline — BigQuery + Feature Store Offline 学習用
#   emb_a / emb_b 二系統リネージュ対応
#   Online Store / Feature View / sync は作成しない
# =========================================================================

locals {
  # Feature Group fg-property-emb-a に登録する特徴量
  features_emb_a = [
    { name = "rent", description = "Monthly rent (共通特徴量)" },
    { name = "walk_min", description = "Walking minutes to nearest station (共通特徴量)" },
    { name = "age_years", description = "Property age in years (共通特徴量)" },
    { name = "area_m2", description = "Floor area in square meters (共通特徴量)" },
    { name = "emb_a_ctr", description = "CTR predicted by text-attribute embedding model" },
    { name = "emb_a_fav_rate", description = "Favorite rate from text-attribute embedding" },
    { name = "emb_a_semantic_score", description = "Semantic similarity score (emb_a specific)" },
  ]

  # Feature Group fg-property-emb-b に登録する特徴量
  features_emb_b = [
    { name = "rent", description = "Monthly rent (共通特徴量)" },
    { name = "walk_min", description = "Walking minutes to nearest station (共通特徴量)" },
    { name = "age_years", description = "Property age in years (共通特徴量)" },
    { name = "area_m2", description = "Floor area in square meters (共通特徴量)" },
    { name = "emb_b_inquiry_rate", description = "Inquiry rate from behavioral-log embedding" },
    { name = "emb_b_collab_score", description = "Collaborative filtering score (emb_b specific)" },
    { name = "emb_b_engagement", description = "Engagement score from behavioral-log embedding" },
  ]
}

# ---- 必要 API ----
resource "google_project_service" "apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# =========================================================================
# BigQuery — 特徴量の実体・加工場所
# =========================================================================
resource "google_bigquery_dataset" "feature_mart" {
  dataset_id  = var.feature_mart_dataset_id
  location    = var.region
  description = "不動産物件の特徴量マート (emb_a/emb_b リネージュ管理)"
  depends_on  = [google_project_service.apis]
}

resource "google_bigquery_table" "property_features_daily" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "property_features_daily"
  deletion_protection = var.enable_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "event_date"
  }
  clustering = ["property_id", "embedding_source"]

  schema = jsonencode([
    { name = "event_date", type = "DATE", mode = "REQUIRED" },
    { name = "feature_timestamp", type = "TIMESTAMP", mode = "NULLABLE", description = "Feature Group BigQuery source の feature-time 列" },
    { name = "property_id", type = "STRING", mode = "REQUIRED", description = "Entity ID" },
    { name = "embedding_source", type = "STRING", mode = "REQUIRED", description = "リネージュ列: 'emb_a' or 'emb_b'" },
    { name = "rent", type = "INT64", mode = "NULLABLE", description = "共通特徴量: 月額賃料" },
    { name = "walk_min", type = "INT64", mode = "NULLABLE", description = "共通特徴量: 最寄駅徒歩分数" },
    { name = "age_years", type = "INT64", mode = "NULLABLE", description = "共通特徴量: 築年数" },
    { name = "area_m2", type = "FLOAT64", mode = "NULLABLE", description = "共通特徴量: 床面積(m²)" },
    { name = "emb_a_ctr", type = "FLOAT64", mode = "NULLABLE", description = "emb_a 動的スコア: テキスト属性モデルCTR" },
    { name = "emb_a_fav_rate", type = "FLOAT64", mode = "NULLABLE", description = "emb_a 動的スコア: テキスト属性お気に入り率" },
    { name = "emb_a_semantic_score", type = "FLOAT64", mode = "NULLABLE", description = "emb_a 固有: セマンティック類似スコア" },
    { name = "emb_b_inquiry_rate", type = "FLOAT64", mode = "NULLABLE", description = "emb_b 動的スコア: 行動ログ問い合わせ率" },
    { name = "emb_b_collab_score", type = "FLOAT64", mode = "NULLABLE", description = "emb_b 動的スコア: 協調フィルタリングスコア" },
    { name = "emb_b_engagement", type = "FLOAT64", mode = "NULLABLE", description = "emb_b 固有: エンゲージメントスコア" },
  ])
}

# BQ View — emb_a ソース (Feature Group fg-property-emb-a の BigQuery source)
resource "google_bigquery_table" "v_property_features_emb_a" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "v_property_features_emb_a"
  deletion_protection = false
  depends_on          = [google_bigquery_table.property_features_daily]

  view {
    use_legacy_sql = false
    query          = <<-SQL
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
      FROM `${var.project_id}.${var.feature_mart_dataset_id}.property_features_daily`
      WHERE embedding_source = 'emb_a'
    SQL
  }
}

# BQ View — emb_b ソース (Feature Group fg-property-emb-b の BigQuery source)
resource "google_bigquery_table" "v_property_features_emb_b" {
  dataset_id          = google_bigquery_dataset.feature_mart.dataset_id
  table_id            = "v_property_features_emb_b"
  deletion_protection = false
  depends_on          = [google_bigquery_table.property_features_daily]

  view {
    use_legacy_sql = false
    query          = <<-SQL
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
      FROM `${var.project_id}.${var.feature_mart_dataset_id}.property_features_daily`
      WHERE embedding_source = 'emb_b'
    SQL
  }
}

# =========================================================================
# Vertex AI Feature Group — emb_a
# =========================================================================
resource "google_vertex_ai_feature_group" "emb_a" {
  provider = google-beta

  name        = "fg_property_emb_a"
  region      = var.region
  description = "テキスト属性埋め込み由来スコア + 共通特徴量 (BQ View emb_a 参照)"

  big_query {
    big_query_source {
      input_uri = "bq://${var.project_id}.${var.feature_mart_dataset_id}.v_property_features_emb_a"
    }
    entity_id_columns = ["property_id"]
  }
  depends_on = [google_bigquery_table.v_property_features_emb_a]
}

resource "google_vertex_ai_feature_group_feature" "emb_a" {
  for_each = { for f in local.features_emb_a : f.name => f }
  provider = google-beta

  name          = each.value.name
  region        = var.region
  feature_group = google_vertex_ai_feature_group.emb_a.name
  description   = each.value.description
}

# =========================================================================
# Vertex AI Feature Group — emb_b
# =========================================================================
resource "google_vertex_ai_feature_group" "emb_b" {
  provider = google-beta

  name        = "fg_property_emb_b"
  region      = var.region
  description = "行動ログ埋め込み由来スコア + 共通特徴量 (BQ View emb_b 参照)"

  big_query {
    big_query_source {
      input_uri = "bq://${var.project_id}.${var.feature_mart_dataset_id}.v_property_features_emb_b"
    }
    entity_id_columns = ["property_id"]
  }
  depends_on = [google_bigquery_table.v_property_features_emb_b]
}

resource "google_vertex_ai_feature_group_feature" "emb_b" {
  for_each = { for f in local.features_emb_b : f.name => f }
  provider = google-beta

  name          = each.value.name
  region        = var.region
  feature_group = google_vertex_ai_feature_group.emb_b.name
  description   = each.value.description
}

# =========================================================================
# Artifact Registry — Cloud Run job イメージ置き場
# =========================================================================
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.ar_repo_id
  format        = "DOCKER"
  description   = "Feature Store Offline 学習用 Cloud Run job イメージ"
  depends_on    = [google_project_service.apis]
}

# =========================================================================
# Service Account + IAM
# =========================================================================
resource "google_service_account" "job_sa" {
  account_id   = "feature-store-offline-job"
  display_name = "Feature Store Offline 学習用 Cloud Run job 実行 SA"
}

resource "google_project_iam_member" "job_sa_roles" {
  for_each = toset([
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/aiplatform.user",
    "roles/storage.objectAdmin",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.job_sa.email}"
}

# =========================================================================
# GCS bucket — batch-read-offline の JSONL 出力先
# =========================================================================
resource "google_storage_bucket" "offline_batch" {
  name                        = "${var.project_id}-feature-offline-${var.region}"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  depends_on                  = [google_project_service.apis]

  lifecycle_rule {
    condition { age = 14 }
    action { type = "Delete" }
  }
}

# =========================================================================
# Cloud Run jobs — seed-csv / load-bq / register-fs / batch-read
# =========================================================================
locals {
  job_common_env = [
    { name = "PROJECT_ID", value = var.project_id },
    { name = "REGION", value = var.region },
  ]
}

resource "google_cloud_run_v2_job" "seed_csv" {
  name                = "seed-csv"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.job_sa.email
      max_retries     = 1
      timeout         = "300s"
      containers {
        image = var.image
        args  = ["seed-csv"]
        dynamic "env" {
          for_each = local.job_common_env
          content {
            name  = env.value.name
            value = env.value.value
          }
        }
      }
    }
  }
  depends_on = [google_project_iam_member.job_sa_roles]
}

resource "google_cloud_run_v2_job" "load_bq" {
  name                = "load-bq"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.job_sa.email
      max_retries     = 1
      timeout         = "300s"
      containers {
        image = var.image
        args  = ["load-bq"]
        dynamic "env" {
          for_each = local.job_common_env
          content {
            name  = env.value.name
            value = env.value.value
          }
        }
      }
    }
  }
  depends_on = [
    google_project_iam_member.job_sa_roles,
    google_bigquery_table.property_features_daily,
  ]
}

resource "google_cloud_run_v2_job" "register_fs" {
  name                = "register-fs"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.job_sa.email
      max_retries     = 1
      timeout         = "600s"
      containers {
        image = var.image
        args  = ["register-fs"]
        dynamic "env" {
          for_each = local.job_common_env
          content {
            name  = env.value.name
            value = env.value.value
          }
        }
      }
    }
  }
  depends_on = [
    google_project_iam_member.job_sa_roles,
    google_bigquery_table.property_features_daily,
  ]
}

resource "google_cloud_run_v2_job" "batch_read" {
  name                = "batch-read"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.job_sa.email
      max_retries     = 1
      timeout         = "600s"
      containers {
        image = var.image
        args  = ["batch-read-offline"]
        dynamic "env" {
          for_each = local.job_common_env
          content {
            name  = env.value.name
            value = env.value.value
          }
        }
        env {
          name  = "GCS_BUCKET"
          value = google_storage_bucket.offline_batch.name
        }
      }
    }
  }
  depends_on = [
    google_project_iam_member.job_sa_roles,
    google_storage_bucket.offline_batch,
  ]
}
