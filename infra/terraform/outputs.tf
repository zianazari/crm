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
