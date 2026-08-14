# Vibetube Catch-Up & Hand-Off Guide

Welcome to **Vibetube**! This document summarizes the project's development history, current architecture, Google Cloud Platform (GCP) deployment status, and the immediate next steps to transition development smoothly.

---

## 1. Overview of Completed Work

Vibetube has been built in eight incremental phases:
1. **Phase 1: Minimalist Search & Grid Main Page**: Built the React, Vite, TypeScript, and Tailwind CSS v4 frontend skeleton with mock data.
2. **Phase 2: Video Player Integration**: Added a custom glassmorphism modal player utilizing high-availability public domain video streams.
3. **Phase 3: Backend Decoupling**: Restructured the app into discrete `/frontend` and `/backend` packages, introducing a Python FastAPI server.
4. **Phase 4: SQLite Database**: Migrated backend data storage from JSON files to a local SQLite database (`vibetube.db`).
5. **Phase 5 & 6: Video & Binary Uploads**: Supported user video uploads, routing binary files to `/uploads` locally and mounting static file serving in FastAPI.
6. **Phase 7: Transcoding & HLS Streaming**: Developed a Python-based transcoder using `ffmpeg` to generate adaptive bitrate HLS formats (480p, 720p, 1080p, `master.m3u8`) and wired up client playback using `hls.js` with Safari fallbacks.
7. **Phase 8: Firebase Authentication**: Configured CDN-based Firebase Auth with a dual mode—automatic offline `MockAuth` simulation for seamless local development, and RS256 JWT validation on the backend verifying signature keys against Google's certificates.

---

## 2. System Architecture

The project consists of three main decoupled services:

```
                  ┌─────────────────────────────────┐
                  │          React Frontend         │
                  │        (Cloud Run Service)      │
                  └───────┬─────────────────┬───────┘
                          │                 │
             Fetch API    │                 │ Direct HLS Playback
             (HTTP Proxy) │                 │
                          ▼                 ▼
                  ┌───────────────┐     ┌────────────────────────┐
                  │FastAPI Backend│     │      GCS Bucket        │
                  │  (Cloud Run   │     │vibeflix-sandbox-public-│
                  │   Service)    │     │        streams         │
                  └──────┬──────┬─┘     └───────────▲────────────┘
                         │      │                   │
      Read/Write Metadata│      │Trigger Job        │ Upload
                         ▼      ▼                   │ Transcoded Files
                  ┌──────────┐ ┌──────────────────┐ │
                  │Database  │ │FFmpeg Transcoder │─┘
                  │(Cloud SQL│ │ (Cloud Run Job)  │
                  │PostgreSQL│ └────────┬─────────┘
                  └──────────┘          │
                                        │ Download
                                        ▼ Raw Upload
                               ┌────────────────────────┐
                               │       GCS Bucket       │
                               │vibeflix-sandbox-raw-   │
                               │         videos         │
                               └────────────────────────┘
```

### Component Details
*   **Frontend ([/frontend](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/frontend))**:
    *   **Tech Stack**: React 18, Vite, TypeScript, Tailwind CSS v4.
    *   **Features**: Dark mode/light mode themes, responsive grid, dynamic play-on-hover video cards, HLS-ready media player, upload modal, and authentication forms.
    *   **Auth**: Integrates with [firebase.ts](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/frontend/src/services/firebase.ts). In local environments, if Firebase keys are absent, it shifts to `MockAuth` where entering any email signs you in (with mock tokens like `mock-token-emailprefix`).
*   **Backend ([/backend](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/backend))**:
    *   **Tech Stack**: FastAPI, Uvicorn, SQLite (local) / PostgreSQL (production via `psycopg2`).
    *   **Database Management**: Defined in [database.py](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/backend/database.py). Connects dynamically based on `DATABASE_URL` env variable. Automatically performs migrations (adding `userId`) and populates seed data on startup.
    *   **Auth Validation**: Handled in [auth.py](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/backend/auth.py). Performs manual RS256 token verification, downloading public signing keys directly from Google. Validates custom `mock-token-` headers for local development.
    *   **Transcoder Triggers**: In production, raw uploads are saved to GCS. The backend then invokes GCP Cloud Run Job client library to launch the transcoder with container overrides (source paths, destination paths, tokens).
*   **Transcoder ([/transcoder](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/transcoder))**:
    *   **Tech Stack**: Python (using `google-cloud-storage`, `requests`, and `click`), FFmpeg system library.
    *   **Execution Flow**: Defined in [job.py](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/transcoder/job.py) and [converter.py](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/transcoder/converter.py). Downloads the raw video from GCS, transcodes it into HLS streams of 480p, 720p, and 1080p, outputs a unified `master.m3u8` playlist, extracts a JPEG thumbnail at the video's midpoint, uploads the outputs back to the public GCS bucket, and sends a secure POST request to the backend callback endpoint with an `X-Transcoder-Token`.

---

## 3. Google Cloud Platform (GCP) Deployment

A deployment orchestration script is provided in [deploy.sh](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/deploy.sh). Running it provisions the infrastructure and deploys the services automatically.

### Infrastructural Resources Configured:
1.  **GCP Project Context**: Targeted to Project `vibeflix-sandbox` in region `us-central1`.
2.  **Storage (GCS)**:
    *   `gs://vibeflix-sandbox-raw-videos`: Private storage bucket for original video files.
    *   `gs://vibeflix-sandbox-public-streams`: Publicly readable bucket (`allUsers` has `roles/storage.objectViewer` permission) with custom CORS configs enabling Cross-Origin media streaming.
3.  **Cloud SQL PostgreSQL Instance**:
    *   Provisioned as `vibeflix-db-instance` running PostgreSQL 15 on a cost-efficient `db-f1-micro` machine.
    *   Creates the application database. Credentials now live in `.env` (gitignored), not in `deploy.sh`.
4.  **Artifact Registry**:
    *   Docker repository named `vibeflix-streaming-platform` storing images for all three services.
5.  **Cloud Run Services / Jobs**:
    *   `backend-service` (Cloud Run Service): Auto-connected to Cloud SQL using Unix sockets, set with the required database URL, bucket names, and transcoder secrets.
    *   `frontend-service` (Cloud Run Service): Hosts the built frontend served by Nginx. The Nginx configuration templates translate `BACKEND_URL` on container start to route `/api` requests correctly.
    *   `transcoder-job` (Cloud Run Job): Built from `/transcoder`. Initiated on-demand via the backend's GCP client library.

---

## 4. Next Steps

Here are the highest priority items that remain to be completed:

1.  **Firebase Production Configuration**:
    *   Provide real Firebase credentials in the frontend config or secrets vault.
    *   Configure `FIREBASE_PROJECT_ID` on the backend deployment so it verifies real JWT tokens instead of mock tokens in production.
2.  **CI/CD Pipeline Setup**:
    *   Automate deployment. Convert [deploy.sh](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/deploy.sh) tasks into a GitHub Actions workflow or a Google Cloud Build trigger.
3.  **Database Migration Management**:
    *   Introduce a migration management framework (such as `Alembic` for SQLAlechemy/Python) instead of relying on custom raw SQL updates inside [database.py](file:///Users/ljhenne/Git/github.com/ljhenne/vibeflix-streaming-platform/backend/database.py).
4.  **Security & IAM Hardening**:
    *   Transition Cloud Run service configurations in `deploy.sh` to use dedicated Service Accounts with least-privilege policies rather than default project compute accounts.
    *   Move the credentials in `.env` to GCP Secret Manager. They are no longer hardcoded in `deploy.sh`, but `.env` is still plaintext on disk.
5.  **Robust Transcoding Queue**:
    *   Currently, calling a Cloud Run Job directly on upload is synchronous. For high traffic, implement a messaging/queue service (e.g., Pub/Sub or Celery) where uploads post a message and transcoder workers consume tasks asynchronously.
