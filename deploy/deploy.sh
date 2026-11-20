#!/bin/bash
# Build both images with Cloud Build and roll the VM onto them.
#   deploy/deploy.sh            # tag = current git commit
set -euo pipefail
cd "$(dirname "$0")/.."
TAG=${1:-$(git rev-parse --short HEAD)}
TF=infra/terraform
REPO=$(terraform -chdir=$TF output -raw image_repo)
PROJECT=$(terraform -chdir=$TF output -raw image_repo | cut -d/ -f2)
ZONE=$(grep -E '^zone' $TF/terraform.tfvars 2>/dev/null | cut -d'"' -f2 || true)

gcloud builds submit --project "$PROJECT" --config deploy/cloudbuild.yaml \
  --substitutions "_REPO=$REPO,_TAG=$TAG" .
terraform -chdir=$TF apply -auto-approve -var "image_tag=$TAG"
gcloud compute ssh crm --project "$PROJECT" --zone "${ZONE:-europe-north1-a}" --tunnel-through-iap \
  --command "sudo google_metadata_script_runner startup"
echo "Deployed $TAG: $(terraform -chdir=$TF output -raw url)"
