#!/bin/bash
set -e

# Configuration
PROJECT_ID="vibetube-sandbox"
REGION="us-central1"
REPO_NAME="vibetube-streaming-platform"
DB_INSTANCE_NAME="vibetube-db-instance"
RAW_BUCKET="vibetube-sandbox-raw-videos"
PUBLIC_BUCKET="vibetube-sandbox-public-streams"
JOB_NAME="transcoder-job"
SECRET_TOKEN="vibe_secret_123"
DB_PASSWORD="vibe_password_123"

echo "==============================================="
echo "  Starting Vibetube Deployment Orchestrator    "
echo "==============================================="

# 1. Select the correct GCP project
echo "-> Selecting GCP project: ${PROJECT_ID}..."
gcloud config set project ${PROJECT_ID}

# 2. Enable GCP Service APIs
echo "-> Enabling required GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

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
echo "-> Checking Cloud SQL Database Instance..."
if ! gcloud sql instances describe ${DB_INSTANCE_NAME} >/dev/null 2>&1; then
  echo "   WARNING: Cloud SQL instance provisioning can take 5 to 10 minutes."
  echo "   Creating database instance ${DB_INSTANCE_NAME} (PostgreSQL 15)..."
  gcloud sql instances create ${DB_INSTANCE_NAME} \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=${REGION} \
    --quiet
    
  echo "   Setting database master password..."
  gcloud sql users set-password postgres \
    --instance=${DB_INSTANCE_NAME} \
    --password=${DB_PASSWORD}
    
  echo "   Creating database 'vibetube'..."
  gcloud sql databases create vibetube --instance=${DB_INSTANCE_NAME}
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
echo "-> Building and pushing container images..."
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/transcoder:latest ./transcoder
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:latest ./backend
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/frontend:latest ./frontend

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

# 8. Deploy Backend Service (Initial deployment to resolve chicken-and-egg URL problem)
echo "-> Deploying Backend Cloud Run Service..."
gcloud run deploy backend-service \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/backend:latest \
  --region=${REGION} \
  --allow-unauthenticated \
  --add-cloudsql-instances=${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME} \
  --set-env-vars="DATABASE_URL=postgresql://postgres:${DB_PASSWORD}@/vibetube?host=/cloudsql/${PROJECT_ID}:${REGION}:${DB_INSTANCE_NAME},RAW_VIDEOS_BUCKET=${RAW_BUCKET},PUBLIC_STREAMS_BUCKET=${PUBLIC_BUCKET},TRANSCODER_JOB_NAME=${JOB_NAME},GCP_PROJECT=${PROJECT_ID},GCP_LOCATION=${REGION},TRANSCODER_SECRET_TOKEN=${SECRET_TOKEN}"

# Get dynamic backend URL
BACKEND_URL=$(gcloud run services describe backend-service --region=${REGION} --format="value(status.url)")
echo "   Backend URL resolved: ${BACKEND_URL}"

# Update Backend Service with its own URL so it knows what callback URL to pass to the transcoder job
echo "   Updating backend environment variables with service URL..."
gcloud run services update backend-service \
  --region=${REGION} \
  --update-env-vars="BACKEND_URL=${BACKEND_URL}"

# 9. Deploy Frontend Service
echo "-> Deploying Frontend Cloud Run Service..."
gcloud run deploy frontend-service \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/frontend:latest \
  --region=${REGION} \
  --allow-unauthenticated \
  --set-env-vars="BACKEND_URL=${BACKEND_URL}"

FRONTEND_URL=$(gcloud run services describe frontend-service --region=${REGION} --format="value(status.url)")

echo "==============================================="
echo "  Deployment completed successfully!          "
echo "  Vibetube Frontend: ${FRONTEND_URL}          "
echo "  Vibetube Backend:  ${BACKEND_URL}           "
echo "==============================================="
