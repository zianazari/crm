#!/bin/bash
# Runs on every boot: installs Docker once, then (re)deploys from instance metadata.
set -euo pipefail

meta() { curl -sf -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"; }

if ! command -v docker >/dev/null; then
  apt-get update -q
  apt-get install -yq ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

mkdir -p /opt/crm && cd /opt/crm
meta crm-compose > compose.yaml
meta crm-caddyfile > Caddyfile
REPO=$(meta crm-image-repo)
cat > deploy.env <<ENV
CRM_HOST=$(meta crm-host)
IMAGE_REPO=$REPO
IMAGE_TAG=${CRM_IMAGE_TAG:-$(meta crm-image-tag)}
ENV
umask 077
gcloud secrets versions access latest --secret=crm-env > .env
cat deploy.env >> .env

gcloud auth configure-docker "${REPO%%/*}" --quiet
docker compose --env-file .env pull
docker compose --env-file .env up -d --remove-orphans

# Daily database backup to Cloud Storage at 02:30 (the bucket deletes old ones).
BUCKET=$(meta crm-backups)
cat > /etc/cron.d/crm-backup <<CRON
30 2 * * * root cd /opt/crm && docker compose exec -T postgres pg_dump -U crm -Fc crm | gcloud storage cp - gs://$BUCKET/crm-\$(date +\%F).dump
CRON
