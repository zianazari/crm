output "url" {
  value = "https://${local.host}"
}

output "ip" {
  value = google_compute_address.crm.address
}

output "image_repo" {
  value = local.image_repo
}

output "backups_bucket" {
  value = google_storage_bucket.backups.name
}

output "admin" {
  description = "The admin ports and their login (passwords are in Secret Manager, crm-env)."
  value = {
    api      = "https://${local.host}:8000/docs"
    rabbitmq = "https://${local.host}:15672 (crm / RABBITMQ_PASSWORD)"
    mailpit  = "https://${local.host}:8025 (admin / admin_password)"
    sms      = "https://${local.host}:8030 (admin / admin_password)"
    postgres = "${google_compute_address.crm.address}:5432 (crm / POSTGRES_PASSWORD)"
    redis    = "${google_compute_address.crm.address}:6379 (REDIS_PASSWORD)"
  }
}

output "admin_password" {
  value     = random_password.admin.result
  sensitive = true
}
