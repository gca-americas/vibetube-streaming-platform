#!/bin/bash
set -e

# --- Configuration ----------------------------------------------------------
# The target project and every secret live in .env, which is gitignored. This
# script is committed, so it must not carry either. Copy .env.example to .env
# and fill it in before deploying.
ENV_FILE="$(cd "$(dirname "$0")" && pwd)/.env"
if [ ! -f "${ENV_FILE}" ]; then
  echo "ERROR: ${ENV_FILE} not found."
  echo "       cp .env.example .env   then fill in PROJECT_ID and the secrets."
  exit 1
fi
# `set -a` exports everything the file defines, so it reaches gcloud too.
set -a
# shellcheck source=/dev/null
. "${ENV_FILE}"
set +a

# Fail before touching GCP rather than half-deploying against a bad config.
# Only the target project is needed: credentials live in Secret Manager, are
# generated there on first deploy, and are never written to disk.
: "${PROJECT_ID:?must be set in .env}"
REGION="${REGION:-us-central1}"

# Secret Manager names. The values are generated in GCP and read only by the
# Cloud Run runtime service account.
SECRET_DATABASE_URL="${SECRET_DATABASE_URL:-vibetube-database-url}"
SECRET_TRANSCODER_TOKEN="${SECRET_TRANSCODER_TOKEN:-vibetube-transcoder-token}"
SECRET_ADMIN_TOKEN="${SECRET_ADMIN_TOKEN:-vibetube-admin-token}"

# Resource names. Overridable from .env, but the defaults are derived from
# PROJECT_ID so that two projects never collide on a globally-unique bucket
# name and nothing has to be renamed by hand.
REPO_NAME="${REPO_NAME:-vibetube}"
DB_INSTANCE_NAME="${DB_INSTANCE_NAME:-vibetube-db-instance}"
DB_NAME="${DB_NAME:-vibetube}"
RAW_BUCKET="${RAW_BUCKET:-${PROJECT_ID}-raw-videos}"
PUBLIC_BUCKET="${PUBLIC_BUCKET:-${PROJECT_ID}-public-streams}"
JOB_NAME="${JOB_NAME:-transcoder-job}"
SERVICE_NAME="${SERVICE_NAME:-vibetube-service}"

# Cloud SQL machine type. db-g1-small is the next tier above db-f1-micro;
# both are shared-core, so a busy event may still want a dedicated vCPU
# (db-n1-standard-1). The tier also sets the connection ceiling -- see below.
DB_TIER="${DB_TIER:-db-g1-small}"

# --- Blast radius -----------------------------------------------------------
# Uploads are anonymous, so these bound what an abusive client can cost.
#
# The database connection budget is the binding constraint: every Cloud Run
# instance holds its own pool, so keep MAX_INSTANCES x DB_POOL_MAX under the
# tier's max_connections -- 10 x 5 = 50 here. Confirm the real ceiling after
# any tier change with:  SHOW max_connections;
MAX_INSTANCES="${MAX_INSTANCES:-10}"
DB_POOL_MAX="5"
# Requests served per instance before Cloud Run adds another.
CONCURRENCY="60"
# Largest accepted upload, in bytes (50 MB). Must stay well below MEMORY:
# Cloud Run's filesystem is in-memory and the multipart body is buffered in
# full before the size check can run.
MAX_UPLOAD_BYTES="52428800"
# Set explicitly rather than relying on the 512Mi default, so the headroom
# above MAX_UPLOAD_BYTES is deliberate.
MEMORY="1Gi"
# Videos transcoding simultaneously within one showroom. Each is a billed
# Cloud Run Job, so this caps concurrent spend per event. Uploads over the cap
# are queued, not rejected.
MAX_CONCURRENT_TRANSCODES="20"
# Total guest uploads one showroom will accept. Reached, further uploads 409.
MAX_UPLOADS_PER_EVENT="300"
# Simultaneous viewers per showroom, enforced by heartbeat. At this scale the
# database tier and pool settings below are the real constraint -- see the
# capacity note in README.md before raising it further.
MAX_CONCURRENT_VIEWERS="2000"
# How long a heartbeat holds a seat. Must exceed the client's 30s interval.
PRESENCE_TTL_SECONDS="90"
# A transcode still running after this is treated as dead and its slot freed.
TRANSCODE_STALE_MINUTES="30"

echo "==============================================="
echo "  Starting Vibetube Deployment Orchestrator    "
echo "==============================================="

# 1. Select the correct GCP project
echo "-> Selecting GCP project: ${PROJECT_ID}..."
if ! gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
  echo "ERROR: project '${PROJECT_ID}' does not exist or is not visible to"
  echo "       $(gcloud config get-value account 2>/dev/null)."
  echo "       Check PROJECT_ID in .env against:  gcloud projects list"
  exit 1
fi
gcloud config set project ${PROJECT_ID}

# Enabling APIs and creating a Cloud SQL instance both require billing. Without
# this check the script gets several steps in before failing on a message that
# does not name the real cause.
if [ "$(gcloud billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' 2>/dev/null)" != "True" ]; then
  echo "ERROR: billing is not enabled on '${PROJECT_ID}'."
  echo "       Cloud Run, Cloud SQL and Cloud Build all require it. Link a"
  echo "       billing account, then re-run:"
  echo "         gcloud billing accounts list"
  echo "         gcloud billing projects link ${PROJECT_ID} --billing-account=ACCOUNT_ID"
  exit 1
fi

# 2. Enable GCP Service APIs
echo "-> Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com

# --- Secret Manager ---------------------------------------------------------
# Credentials are generated inside GCP on first deploy and never leave it. They
# are not in .env, not in this script, and never written to disk -- so there is
# nothing to leak from a laptop or a commit.
#
# The Cloud Run runtime service account is granted read access per secret,
# rather than a project-wide role.
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${RUNTIME_SA:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

secret_exists() {
  gcloud secrets describe "$1" >/dev/null 2>&1
}

# Creates the secret with a freshly generated value if it does not exist yet.
# Existing secrets are left completely alone: re-running this script must never
# rotate a credential out from under a running service.
ensure_generated_secret() {
  local name="$1"
  if secret_exists "${name}"; then
    echo "   Secret ${name} already exists (leaving it unchanged)."
    return
  fi
  echo "   Creating secret ${name} with a generated value..."
  gcloud secrets create "${name}" --replication-policy=automatic >/dev/null
  openssl rand -hex 32 | tr -d '\n' \
    | gcloud secrets versions add "${name}" --data-file=- >/dev/null
}

grant_secret_access() {
  gcloud secrets add-iam-policy-binding "$1" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
}

echo "-> Ensuring Secret Manager entries..."
ensure_generated_secret "${SECRET_TRANSCODER_TOKEN}"
ensure_generated_secret "${SECRET_ADMIN_TOKEN}"

# 3. Create Cloud Storage Buckets
echo "-> Checking GCS Buckets..."
if ! gcloud storage buckets describe gs://${RAW_BUCKET} >/dev/null 2>&1; then
  echo "   Creating raw videos bucket gs://${RAW_BUCKET}..."
  gcloud storage buckets create gs://${RAW_BUCKET} --location=${REGION}
fi

if ! gcloud storage buckets describe gs://${PUBLIC_BUCKET} >/dev/null 2>&1; then
  echo "   Creating public streaming bucket gs://${PUBLIC_BUCKET}..."
  gcloud storage buckets create gs://${PUBLIC_BUCKET} --location=${REGION}
  
  # Allow public read access to streaming files
  echo "   Applying public reader IAM policies..."
  gcloud storage buckets update gs://${PUBLIC_BUCKET} --clear-pap
  gcloud storage buckets add-iam-policy-binding gs://${PUBLIC_BUCKET} \
    --member=allUsers \
    --role=roles/storage.objectViewer
    
  # Create CORS config for streaming delivery
  echo "   Applying CORS rules to allow browser media player downloads..."
  cat <<EOF > /tmp/cors.json
[
  {
    "origin": ["*"],
    "method": ["GET", "HEAD", "OPTIONS"],
    "responseHeader": ["Content-Type", "Access-Control-Allow-Origin"],
    "maxAgeSeconds": 3600
  }
]
EOF
  gcloud storage buckets update gs://${PUBLIC_BUCKET} --cors-file=/tmp/cors.json
  rm -f /tmp/cors.json
fi

# 4. Provision Cloud SQL PostgreSQL Instance
#
# The database password is generated here, used immediately, and stored only as
# part of the DATABASE_URL secret. It is held in a shell variable for the few
# lines that need it and never echoed, written to a file, or passed to Cloud
# Run directly -- the service reads the whole DSN from Secret Manager.
echo "-> Checking Cloud SQL Database Instance..."
if ! gcloud sql instances describe ${DB_INSTANCE_NAME} >/dev/null 2>&1; then
  echo "   WARNING: Cloud SQL instance provisioning can take 5 to 10 minutes."
  echo "   Creating database instance ${DB_INSTANCE_NAME} (PostgreSQL 15, ${DB_TIER})..."
  gcloud sql instances create ${DB_INSTANCE_NAME} \
    --database-version=POSTGRES_15 \
    --tier=${DB_TIER} \
    --region=${REGION} \
    --quiet

  GENERATED_DB_PASSWORD="$(openssl rand -base64 32 | tr -d '\n/+=' | cut -c1-32)"

  echo "   Setting database master password..."
  gcloud sql users set-password postgres \
    --instance=${DB_INSTANCE_NAME} \
    --password="${GENERATED_DB_PASSWORD}" >/dev/null

  echo "   Creating database '${DB_NAME}'..."
  gcloud sql databases create ${DB_NAME} --instance=${DB_INSTANCE_NAME} >/dev/null

  echo "   Storing DATABASE_URL in Secret Manager..."
  DSN="postgresql://postgres:${GENERATED_DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME}"
  if ! secret_exists "${SECRET_DATABASE_URL}"; then
    gcloud secrets create "${SECRET_DATABASE_URL}" --replication-policy=automatic >/dev/null
  fi
  printf '%s' "${DSN}" | gcloud secrets versions add "${SECRET_DATABASE_URL}" --data-file=- >/dev/null
  unset GENERATED_DB_PASSWORD DSN
fi

# An instance without a matching secret cannot be recovered automatically: the
# password is not retrievable from Cloud SQL. Say so plainly rather than
# deploying a service that cannot reach its database.
if ! secret_exists "${SECRET_DATABASE_URL}"; then
  echo ""
  echo "ERROR: Cloud SQL instance '${DB_INSTANCE_NAME}' exists but secret"
  echo "       '${SECRET_DATABASE_URL}' does not, so the connection string is unknown."
  echo "       Either store the existing DSN:"
  echo "         printf '%s' 'postgresql://postgres:PASSWORD@/${DB_NAME}?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME}' \\"
  echo "           | gcloud secrets create ${SECRET_DATABASE_URL} --data-file=-"
  echo "       or reset the password and store the new one the same way:"
  echo "         gcloud sql users set-password postgres --instance=${DB_INSTANCE_NAME} --prompt-for-password"
  exit 1
fi

# 5. Create Artifact Registry
echo "-> Checking Docker Artifact Registry..."
if ! gcloud artifacts repositories describe ${REPO_NAME} --location=${REGION} >/dev/null 2>&1; then
  echo "   Creating Artifact Registry Repository..."
  gcloud artifacts repositories create ${REPO_NAME} \
    --repository-format=docker \
    --location=${REGION}
fi

# 6. Build and Publish Docker Containers
# Two images only: the app (API + built frontend in one container) and the
# transcoder. The app image builds from the repo root so its Dockerfile can
# reach both frontend/ and backend/.
echo "-> Building and pushing container images..."
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/transcoder:latest ./transcoder
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/app:latest .

# 7. Deploy Cloud Run Transcoder Job
echo "-> Deploying/Updating Cloud Run Job: ${JOB_NAME}..."
# Run jobs replace if exists, else create
if gcloud run jobs describe ${JOB_NAME} --region=${REGION} >/dev/null 2>&1; then
  gcloud run jobs update ${JOB_NAME} \
    --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/transcoder:latest \
    --region=${REGION}
else
  gcloud run jobs create ${JOB_NAME} \
    --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/transcoder:latest \
    --region=${REGION}
fi

# 8. Deploy the app service. Deployed once to learn its own URL, then updated
# with it, since the transcoder needs a callback address to report back to.
#
# Access is granted immediately before the deploy so the first revision can
# read its secrets; IAM changes can take a moment to propagate, and a revision
# that starts without them crash-loops on a missing DATABASE_URL.
echo "-> Granting the runtime service account access to the secrets..."
for SECRET in "${SECRET_DATABASE_URL}" "${SECRET_TRANSCODER_TOKEN}" "${SECRET_ADMIN_TOKEN}"; do
  grant_secret_access "${SECRET}"
done

echo "-> Deploying Vibetube Cloud Run Service..."
gcloud run deploy ${SERVICE_NAME} \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/app:latest \
  --region=${REGION} \
  --allow-unauthenticated \
  --max-instances=${MAX_INSTANCES} \
  --concurrency=${CONCURRENCY} \
  --memory=${MEMORY} \
  --add-cloudsql-instances=${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME} \
  --service-account=${RUNTIME_SA} \
  --set-secrets="DATABASE_URL=${SECRET_DATABASE_URL}:latest,TRANSCODER_SECRET_TOKEN=${SECRET_TRANSCODER_TOKEN}:latest,ADMIN_TOKEN=${SECRET_ADMIN_TOKEN}:latest" \
  --set-env-vars="RAW_VIDEOS_BUCKET=${RAW_BUCKET},PUBLIC_STREAMS_BUCKET=${PUBLIC_BUCKET},TRANSCODER_JOB_NAME=${JOB_NAME},GCP_PROJECT=${PROJECT_ID},GCP_LOCATION=${REGION},DB_POOL_MAX=${DB_POOL_MAX},MAX_UPLOAD_BYTES=${MAX_UPLOAD_BYTES},MAX_CONCURRENT_TRANSCODES=${MAX_CONCURRENT_TRANSCODES},MAX_UPLOADS_PER_EVENT=${MAX_UPLOADS_PER_EVENT},MAX_CONCURRENT_VIEWERS=${MAX_CONCURRENT_VIEWERS},PRESENCE_TTL_SECONDS=${PRESENCE_TTL_SECONDS},TRANSCODE_STALE_MINUTES=${TRANSCODE_STALE_MINUTES}"

# Get the service URL, which is now both the site and the API origin.
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region=${REGION} --format="value(status.url)")
echo "   Service URL resolved: ${SERVICE_URL}"

# Hand the service its own URL so it can tell the transcoder where to call back.
echo "   Updating environment variables with service URL..."
gcloud run services update ${SERVICE_NAME} \
  --region=${REGION} \
  --update-env-vars="BACKEND_URL=${SERVICE_URL}"

echo "==============================================="
echo "  Deployment completed successfully!"
echo "  Vibetube: ${SERVICE_URL}"
echo ""
echo "  Create an event before sharing a link. The DSN comes from Secret"
echo "  Manager, so no password is printed here or stored on disk:"
echo ""
echo "    cloud-sql-proxy ${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME} &"
echo "    cd backend"
echo "    export DATABASE_URL=\"\$(gcloud secrets versions access latest \\"
echo "        --secret=${SECRET_DATABASE_URL} --project=${PROJECT_ID} \\"
echo "      | sed 's#@/#@127.0.0.1:5432/#; s#?host=.*##')\""
echo "    python admin.py create-event --name 'My Event' --code DEMO"
echo "    -> share ${SERVICE_URL}/e/DEMO"
echo ""
echo "  Admin token, when you need it for the seeding endpoints:"
echo "    gcloud secrets versions access latest --secret=${SECRET_ADMIN_TOKEN} --project=${PROJECT_ID}"
echo "==============================================="

# Services left behind by earlier layouts and by the Vibeflix -> Vibetube
# rename. They keep running and serving stale code until removed, but deleting
# a service is not something this script should do on its own -- report it and
# let the operator decide.
for OLD_SERVICE in frontend-service backend-service vibeflix-service; do
  if gcloud run services describe ${OLD_SERVICE} --region=${REGION} >/dev/null 2>&1; then
    echo ""
    echo "NOTE: '${OLD_SERVICE}' is superseded by '${SERVICE_NAME}' and is no"
    echo "      longer used. Its URL will stop working once you remove it:"
    echo "        gcloud run services delete ${OLD_SERVICE} --region=${REGION}"
  fi
done
