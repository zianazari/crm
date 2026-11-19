variable "project_id" {
  description = "GCP project to deploy into."
  type        = string
}

variable "region" {
  description = "Finland."
  type        = string
  default     = "europe-north1"
}

variable "zone" {
  type    = string
  default = "europe-north1-a"
}

variable "machine_type" {
  description = "Runs everything (web, API, worker, Postgres, Redis, RabbitMQ)."
  type        = string
  default     = "e2-standard-2"
}

variable "environment" {
  description = "staging or production (the app refuses development secrets in both)."
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "domain" {
  description = "Public host name. Empty: <ip>.sslip.io, which needs no DNS."
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Tag of the images in Artifact Registry (deploy/deploy.sh sets it)."
  type        = string
  default     = "latest"
}

variable "app_env" {
  description = "Extra CRM_* settings, e.g. the SMS/SMTP provider and its credentials."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "backup_retention_days" {
  type    = number
  default = 30
}

variable "demo" {
  description = "Demo site: SMS simulator and Mailpit instead of real providers (staging only)."
  type        = bool
  default     = true
}

variable "admin_cidrs" {
  description = "Who may reach the admin ports (API 8000, RabbitMQ 15672/5672, Mailpit 8025, SMS simulator 8030, Postgres 5432, Redis 6379)."
  type        = list(string)
}
