output "offline_batch_bucket" {
  description = "batch-read-offline の JSONL 出力先 GCS bucket 名"
  value       = google_storage_bucket.offline_batch.name
}

output "feature_group_emb_a" {
  description = "Feature Group fg-property-emb-a のリソース名"
  value       = google_vertex_ai_feature_group.emb_a.name
}

output "feature_group_emb_b" {
  description = "Feature Group fg-property-emb-b のリソース名"
  value       = google_vertex_ai_feature_group.emb_b.name
}

output "job_sa_email" {
  description = "Cloud Run job 実行 Service Account のメールアドレス"
  value       = google_service_account.job_sa.email
}
