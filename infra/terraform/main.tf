locals {
  services = [
    "compute.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "iap.googleapis.com",
  ]
  host       = var.domain != "" ? var.domain : "${replace(google_compute_address.crm.address, ".", "-")}.sslip.io"
  image_repo = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.crm.repository_id}"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

# -- images ------------------------------------------------------------------------------

resource "google_artifact_registry_repository" "crm" {
  repository_id = "crm"
  format        = "DOCKER"
  location      = var.region
  depends_on    = [google_project_service.apis]

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions { keep_count = 10 }
  }
}

# -- network -----------------------------------------------------------------------------

resource "google_compute_address" "crm" {
  name       = "crm"
  region     = var.region
  depends_on = [google_project_service.apis]
}

resource "google_compute_firewall" "web" {
  depends_on    = [google_project_service.apis]
  name          = "crm-web"
  network       = "default"
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["crm"]
  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
}

resource "google_compute_firewall" "admin" {
  depends_on    = [google_project_service.apis]
  name          = "crm-admin"
  network       = "default"
  direction     = "INGRESS"
  source_ranges = var.admin_cidrs
  target_tags   = ["crm"]
  allow {
    protocol = "tcp"
    ports    = ["8000", "15672", "8025", "8030", "5672", "5432", "6379"]
  }
}

# SSH only through Identity-Aware Proxy (gcloud compute ssh --tunnel-through-iap).
resource "google_compute_firewall" "iap_ssh" {
  depends_on    = [google_project_service.apis]
  name          = "crm-iap-ssh"
  network       = "default"
  direction     = "INGRESS"
  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["crm"]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# -- secrets -----------------------------------------------------------------------------

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "random_password" "rabbitmq" {
  length  = 32
  special = false
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "random_password" "otp" {
  length  = 64
  special = false
}

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "random_password" "admin" {
  length  = 20
  special = false
}

resource "random_password" "sms_webhook" {
  length  = 48
  special = false
}

locals {
  env = merge({
    CRM_ENVIRONMENT        = var.environment
    CRM_DATABASE_URL       = "postgresql+psycopg://crm:${random_password.postgres.result}@postgres:5432/crm"
    CRM_REDIS_URL          = "redis://:${random_password.redis.result}@redis:6379/0"
    CRM_RABBITMQ_URL       = "amqp://crm:${random_password.rabbitmq.result}@rabbitmq:5672/"
    CRM_JWT_SECRET         = random_password.jwt.result
    CRM_OTP_SECRET         = random_password.otp.result
    CRM_SMS_WEBHOOK_SECRET = random_password.sms_webhook.result
    CRM_MESSAGING_MODE     = "queue"
    CRM_COOKIE_SECURE      = "true"
    CRM_PUBLIC_WEB_URL     = "https://${local.host}"
    POSTGRES_PASSWORD      = random_password.postgres.result
    RABBITMQ_PASSWORD      = random_password.rabbitmq.result
    REDIS_PASSWORD         = random_password.redis.result
    ADMIN_PASSWORD         = random_password.admin.result
    }, var.demo ? {
    COMPOSE_PROFILES     = "demo"
    CRM_DEMO_SIMULATORS  = "true"
    CRM_SMS_SINK_URL     = "http://sms-sink:8030"
    CRM_SMS_CALLBACK_URL = "http://api:8000/webhooks/sms"
    CRM_SMTP_HOST        = "mailpit"
    CRM_SMTP_PORT        = "1025"
  } : {}, var.app_env)
}

resource "google_secret_manager_secret" "env" {
  secret_id = "crm-env"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "env" {
  secret      = google_secret_manager_secret.env.id
  secret_data = "${join("\n", [for k, v in local.env : "${k}=${v}"])}\n"
}

# -- backups -----------------------------------------------------------------------------

resource "google_storage_bucket" "backups" {
  name                        = "${var.project_id}-crm-backups"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition { age = var.backup_retention_days }
    action { type = "Delete" }
  }
}

# -- the VM ------------------------------------------------------------------------------

resource "google_service_account" "vm" {
  depends_on   = [google_project_service.apis]
  account_id   = "crm-vm"
  display_name = "CRM VM"
}

resource "google_artifact_registry_repository_iam_member" "vm_pull" {
  repository = google_artifact_registry_repository.crm.name
  location   = var.region
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_secret_manager_secret_iam_member" "vm_env" {
  secret_id = google_secret_manager_secret.env.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_storage_bucket_iam_member" "vm_backups" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_logs" {
  for_each = toset(["roles/logging.logWriter", "roles/monitoring.metricWriter"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.vm.email}"
}

# Docker's data (Postgres, Redis, RabbitMQ, certificates) lives on its own disk, so it
# survives the VM being recreated. Snapshots below keep a week of daily copies.
resource "google_compute_disk" "data" {
  name       = "crm-data"
  type       = "pd-balanced"
  zone       = var.zone
  size       = 30
  depends_on = [google_project_service.apis]

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_resource_policy" "daily" {
  name   = "crm-daily-snapshot"
  region = var.region
  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = "01:00"
      }
    }
    retention_policy {
      max_retention_days    = 7
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "data" {
  name = google_compute_resource_policy.daily.name
  disk = google_compute_disk.data.name
  zone = var.zone
}

resource "google_compute_instance" "crm" {
  name         = "crm"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["crm"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 40
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "crm-data"
  }

  network_interface {
    network = "default"
    access_config {
      nat_ip = google_compute_address.crm.address
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot = true
  }

  metadata = {
    enable-oslogin = "TRUE"
    crm-host       = local.host
    crm-image-repo = local.image_repo
    crm-image-tag  = var.image_tag
    crm-backups    = google_storage_bucket.backups.name
    crm-compose    = file("${path.module}/../../deploy/compose.yaml")
    crm-caddyfile  = file("${path.module}/../../deploy/Caddyfile")
    # A metadata key (not metadata_startup_script), so editing it never replaces the VM.
    startup-script = file("${path.module}/startup.sh")
  }

  depends_on = [
    google_secret_manager_secret_version.env,
    google_artifact_registry_repository_iam_member.vm_pull,
    google_secret_manager_secret_iam_member.vm_env,
  ]
}
