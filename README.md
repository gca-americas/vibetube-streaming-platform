# Vibetube Video Streaming Platform

Vibetube is an event-based video streaming platform with a cinematic neon/glow aesthetic.

Viewers enter an **event code** to reach a showroom at `/e/CODE`. Each showroom is an isolated
mini-Vibetube: its own copy of the seed videos, its own uploads, and its own upload window.
Anyone with the link can watch; uploading is only possible while that event's window is open.

## How it is packaged

The app ships as **one container**: FastAPI serves both the JSON API and the built React app,
so there is no proxy hop and no second service to keep in sync. The transcoder is separate
because it is a batch job, not a web server — it runs for minutes at 100% CPU per video and
scales on a completely different curve from the API.

| Component | Stack | Deploys as |
|---|---|---|
| `frontend/` + `backend/` | React 18 + Vite, FastAPI | One Cloud Run **service** (root `Dockerfile`) |
| `transcoder/` | Python, FFmpeg | One Cloud Run **job** |

Storage is SQLite locally and Cloud SQL PostgreSQL in the cloud, selected by `DATABASE_URL`.

> `CATCHUP.md` and `ARCHITECTURE.md` predate both the event system and this single-container
> layout. Treat this README as the current reference.

## What a showroom shows

Each card carries a title, uploader name, and the absolute upload time in the viewer's own
timezone. Timestamps are stored as ISO-8601 UTC and formatted client-side.


### Sharing a video

Opening a video puts its id in the URL as `/e/CODE?v=<videoId>`, and the player offers **X**,
**LinkedIn**, and **Copy link**. A shared link opens straight into that video; if the video has
since been removed, the link falls back to the grid rather than erroring.

**Link previews are rendered server-side.** LinkedIn and X fetch the URL to build their card
and do not execute JavaScript, so the SPA fallback injects Open Graph and Twitter card tags into
the HTML before serving it — per video, per showroom, and a site default elsewhere. The card
shows the video's own thumbnail and a line in the uploader's voice.

> **Previews only work from a public URL.** A crawler cannot reach `localhost`, so testing a
> share locally will always show "cannot display preview". Deploy first, then check with
> [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/) — which also force-refreshes
> LinkedIn's cache, since it holds a preview for around 7 days and will otherwise keep serving
> the first (empty) one it saw.


---

## Running locally

Locally there is **no GCS and no transcoder**. Uploads are written to `backend/uploads/` and are
playable immediately, so videos never sit in a "processing" state. Metadata lives in a SQLite
file at `backend/vibetube.db`. Both are gitignored.

### Prerequisites

- Node.js 18+
- Python 3.11+

### The quick way

```bash
./dev.sh
```

This creates the virtualenv and installs dependencies on first run, starts both halves, and
shuts both down on Ctrl-C. Then open http://localhost:5173 and enter `sandbox`, or go straight
to http://localhost:5173/e/sandbox.

**Development runs two processes on purpose.** Vite serves the frontend with hot reload and
proxies `/api` to the backend on port 8000. The single-container layout is for deployment —
building the image on every edit would make the feedback loop unusable.

### Or start each half yourself

```bash
# Terminal 1
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export ADMIN_TOKEN=local-admin-token
python main.py                # http://127.0.0.1:8000

# Terminal 2
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

On first start the backend creates the schema, creates a `sandbox` event, and seeds it with the
8 default videos. Existing videos from before events existed are migrated into `sandbox`.

> Viewing and uploading are both anonymous — there is no sign-in anywhere. The Firebase auth
> code that used to sit here has been removed; the frontend needs no environment file at all.

### Running the production container locally

To exercise exactly what deploys — one process, one port, no Vite:

```bash
docker build -t vibetube .
docker run --rm -p 8080:8080 -e ADMIN_TOKEN=local-admin-token vibetube
```

Then open http://localhost:8080/e/sandbox. The API is on the same origin at
`http://localhost:8080/api/...`. There is no hot reload here; rebuild to see changes.

### Where thumbnails come from

Three different places, which is worth knowing when one looks wrong:

| Source | Thumbnail |
|---|---|
| The 8 seed videos | Static JPEGs shipped in `frontend/public/images/thumbnails/`, referenced by `mockVideos.json`. Nothing generates them |
| Uploads in the cloud | FFmpeg extracts a frame at the video's **midpoint** (`transcoder/converter.py`), uploads it beside the HLS renditions, and the completion callback writes the URL back |
| Uploads locally | None. The row is created with `"?"` and there is no transcoder to replace it |

The midpoint is used rather than the first frame because opening frames are so often black.
A `?` on a locally uploaded card is expected, not a fault.

---

## Managing events

Events are created from the shell with the admin CLI. Run it from `backend/` with the same
environment as the server (it writes to the same database).

```bash
cd backend

# Create a showroom with an auto-generated code, seeded with the 8 default videos
python admin.py create-event --name "Vibe Summit 2026"

# Explicit code plus an upload window, entered in local time
python admin.py create-event \
  --name "Vibe Summit 2026" \
  --code SUMMIT \
  --opens  "2026-09-01 09:00" \
  --closes "2026-09-01 18:00" \
  --tz America/Los_Angeles

python admin.py list-events               # code, video count, upload state, window
python admin.py set-window --code SUMMIT --closes "2026-09-01 20:00" --tz America/Los_Angeles
python admin.py set-window --code SUMMIT --clear-closes    # uploads open indefinitely
python admin.py purge-event --code SUMMIT                  # deletes the event and its videos
```

Times are entered in the timezone you pass and stored as UTC. Omitting `--opens`/`--closes`
leaves that side unbounded. Codes are generated from a non-ambiguous alphabet (no `0`/`O`,
no `1`/`I`) and are non-sequential, so one code cannot be used to guess another.

`purge-event` removes database rows only. It prints the `gsutil` command for the corresponding
media but does not run it.

---

## Testing uploads

All examples assume the local backend on port 8000. You need a **real video file** — the server
sniffs the first bytes for a container signature, so random bytes with a `.mp4` name are
rejected. Grab a small public clip:

```bash
curl -sL -o /tmp/test-clip.mp4 https://media.w3.org/2010/05/sintel/trailer_hd.mp4
```

### What the server rejects

| Condition | Status | Notes |
|---|---|---|
| Larger than `MAX_UPLOAD_BYTES` (50 MB) | `413` | Measured while streaming, not from `Content-Length` |
| Not a recognised video container | `400` | ISO/MP4, Matroska/WebM, AVI, Ogg, FLV, MPEG accepted |
| Empty file | `400` | |
| Upload window closed | `403` | Server clock, not the browser's |
| Showroom at `MAX_UPLOADS_PER_EVENT` (300) | `409` | Total guest uploads, for the life of the showroom |

All of these are checked **before** anything is written to disk or GCS, so a rejected upload
costs no storage. The format sniff is a cheap gate, not full validation — the transcoder is
still the authority on whether a file is actually usable.

Note what is **not** in that list: being at the transcode concurrency cap. Uploads over
`MAX_CONCURRENT_TRANSCODES` are queued, not refused — see below.

---

## Uploading from another system

The upload endpoint is a plain `multipart/form-data` POST with **no authentication** — the event
code in the URL is the only gate. Anything that can send a multipart request can publish into a
showroom while its upload window is open.

```
POST  https://<service-url>/api/events/{code}/videos
Content-Type: multipart/form-data
```

`{code}` is the showroom code, e.g. `SUMMIT`. Case-sensitive.

### Request fields

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `videoFile` | file | **yes** | — | Max 50 MB. Must be a real video container |
| `title` | text | **yes** | — | Shown on the card |
| `description` | text | no | `""` | Shown in the player |
| `displayName` | text | no | `Anonymous Vibe` | Uploader name on the card |
| `projectId` | text | no | `""` | Re-using one **replaces** that project's video in place. Empty means none |
| `duration` | text | no | — | Rarely needed. Overwritten with the true runtime once transcoding finishes |
| `avatarFile` | file | no | — | Max 5 MB. JPEG/PNG/GIF/WebP. Omitted → initials shown |
| `thumbnailFile` | file | no | — | Max 5 MB. Omitted → a frame from the video's midpoint |

### Response

```json
{ "id": "v_44d4a0801ac2", "status": "success" }
```

`200` means **accepted**, not published. In the cloud the video is queued and becomes playable
minutes later; poll `GET /api/events/{code}/videos` and watch that `id` until its `status` is
`ready`.

### Errors

| Status | Meaning |
|---|---|
| `400` | Empty file, unrecognised video container, or an `avatarFile`/`thumbnailFile` that is not an image |
| `403` | The showroom's upload window is closed |
| `404` | No showroom with that code |
| `409` | The showroom hit its 300-upload cap, **or** that project's previous upload is still transcoding |
| `413` | `videoFile` over 50 MB, or an image over 5 MB |
| `503` | Server busy (connection pool saturated) — retryable, honours `Retry-After` |

Every error returns `{"detail": "..."}` with a message safe to show a user. Nothing is stored
when a request is rejected.

### Examples

```bash
# Minimal
curl -X POST https://<service-url>/api/events/SUMMIT/videos \
  -F "title=Our Demo" \
  -F "videoFile=@demo.mp4"

# Everything
curl -X POST https://<service-url>/api/events/SUMMIT/videos \
  -F "title=Team Rocket Demo" \
  -F "description=What we built and why" \
  -F "displayName=Christina Lin" \
  -F "projectId=team-rocket-01" \
  -F "videoFile=@demo.mp4" \
  -F "avatarFile=@me.jpg" \
  -F "thumbnailFile=@poster.png"
```

```python
import requests

with open("demo.mp4", "rb") as video, open("poster.png", "rb") as poster:
    response = requests.post(
        "https://<service-url>/api/events/SUMMIT/videos",
        data={
            "title": "Team Rocket Demo",
            "description": "What we built and why",
            "displayName": "Christina Lin",
            "projectId": "team-rocket-01",
        },
        files={"videoFile": video, "thumbnailFile": poster},
        timeout=300,          # a 50 MB upload over a slow link takes a while
    )
response.raise_for_status()
video_id = response.json()["id"]
```

Do **not** compute or send `duration` — ffprobe measures it during transcoding and the
completion callback overwrites whatever was stored. Anything you send is a temporary
placeholder shown for the few minutes before the video becomes `ready`.

### Replacing a submission

Re-uploading with a `projectId` that already exists **overwrites that video in place** rather
than creating a second one. This is the normal path for teams iterating on a submission.

- The video keeps its **id**, so any `?v=<id>` link already shared keeps working.
- It does **not** count against the showroom's upload cap.
- The profile picture is kept if the re-upload omits one; send a new `avatarFile` to change it.
- The thumbnail always resets — the old poster frame belongs to the old video. Send a new
  `thumbnailFile` to set one, or let the transcoder generate it.
- `createdAt` updates to the replacement time, so the card sorts as recently changed.

A replacement is refused with `409` while the previous upload for that project is still
`pending` or `processing`: the in-flight job would otherwise call back against a row it no
longer describes and overwrite the new video's URLs with the old one's output. Wait for it to
reach `ready` (or `failed`) and retry. Replacing a `failed` video is allowed, which is how you
retry after a bad encode.

### Reading a showroom back

`GET /api/events/{code}/videos` returns an array, newest first, each entry shaped:

```json
{
  "id": "v_44d4a0801ac2",
  "eventId": "SUMMIT",
  "title": "Team Rocket Demo",
  "description": "What we built and why",
  "projectId": "team-rocket-01",
  "channelName": "Christina Lin",
  "channelAvatar": "https://storage.googleapis.com/.../images/ab12.jpg",
  "thumbnailUrl": "https://storage.googleapis.com/.../thumbnail.jpg",
  "videoUrl": "https://storage.googleapis.com/.../master.m3u8",
  "duration": "4:32",
  "createdAt": "2026-08-14T18:22:40.538971+00:00",
  "status": "ready",
  "source": "upload"
}
```

`status` is one of `pending`, `processing`, `ready`, `failed`. **Only `ready` is playable.**
`videoUrl` is an HLS master playlist once transcoding finishes; before that it points at the
raw upload and should not be used. A `"?"` in `channelAvatar` or `thumbnailUrl` means "none
supplied" — render initials or a placeholder.

`GET /api/events/{code}` returns the showroom itself, including `uploadOpen` — check it before
uploading to fail fast rather than on a `403`.

### Seeding as an organiser

Two admin routes bypass the upload window and the per-showroom cap. Both require the token from
Secret Manager in an `X-Admin-Token` header; they return `503` if `ADMIN_TOKEN` is unset on the
server and `403` if it does not match.

- `POST /api/events/{code}/seed` — JSON metadata for videos already hosted elsewhere. No
  transcoding, appears instantly.
- `POST /api/events/{code}/seed-upload` — same multipart form as above, run through the full
  pipeline.

See [Seed a showroom over HTTP](#seed-a-showroom-over-http) for worked examples.

---

### The transcode queue

An accepted upload is written `pending` and starts transcoding only when the showroom is below
`MAX_CONCURRENT_TRANSCODES` (20). The queue drains on every upload and again on every
transcoder callback, so a freed slot refills immediately without anything polling for it.

Cards show `Queued` → `Processing` → playable, and the grid polls every 5s while either state
is present. This is why an upload always succeeds during a busy event: a 300-upload showroom
runs 20 at a time and everyone else simply waits, instead of a wall of errors.

A job that dies without reporting back would otherwise hold its slot forever, so any row
processing longer than `TRANSCODE_STALE_MINUTES` (30) is treated as dead: marked failed and its
slot released.

### Concurrent viewers

Each showroom admits `MAX_CONCURRENT_VIEWERS` (2000) at once, enforced by a heartbeat to
`POST /api/events/{code}/presence` every 30s. A seat is held for `PRESENCE_TTL_SECONDS` (90),
so a viewer who closes the tab frees theirs shortly after. Over capacity returns `503` and the
"showroom is full" screen; an **already-present** viewer is never evicted, so a full room stops
admitting rather than ejecting.

The count is approximate by design — it is keyed on a random `clientId` in `localStorage`, so
the same person in two browsers counts twice.

### Upload into an open showroom

```bash
curl -X POST http://localhost:8000/api/events/sandbox/videos \
  -F "title=My Test Clip" \
  -F "description=Uploaded from curl" \
  -F "displayName=Christina" \
  -F "videoFile=@/tmp/test-clip.mp4"
# {"id":"v_a1b2c3d4e5f6","status":"success"}
```

`displayName` is optional and defaults to `Anonymous Vibe`. No authentication is involved.

### Confirm it landed, and only in that showroom

```bash
curl -s http://localhost:8000/api/events/sandbox/videos | python3 -m json.tool | head -20
```

The newest upload sorts first. Listing a different event will not include it.

### Confirm oversized and non-video uploads are refused

```bash
# 60 MB of noise: fails the size check first
head -c 60000000 /dev/urandom > /tmp/too-big.mp4
curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8000/api/events/sandbox/videos \
  -F "title=Too Big" -F "videoFile=@/tmp/too-big.mp4"
# 413

# A text file wearing a .mp4 extension
echo "not a video" > /tmp/fake.mp4
curl -s -X POST http://localhost:8000/api/events/sandbox/videos \
  -F "title=Fake" -F "videoFile=@/tmp/fake.mp4"
# {"detail":"That file does not look like a video. Please upload a video file."}
```

### Confirm the upload window is enforced

```bash
# A showroom whose window closed in 2020
python admin.py create-event --name "Closed Room" --code LOCKED --closes "2020-01-01 10:00" --tz UTC

curl -s http://localhost:8000/api/events/LOCKED
# ..."uploadOpen":false,"uploadState":"closed","reason":"The upload window ... has closed."

curl -s -o /dev/null -w "%{http_code}\n" -X POST \
  http://localhost:8000/api/events/LOCKED/videos \
  -F "title=Too Late" -F "videoFile=@/tmp/test-clip.mp4"
# 403
```

The window is enforced on the server. Hiding the upload button in the UI is presentation only —
an upload that starts before the deadline and arrives after it is still rejected.

### Confirm an unknown code has no showroom

```bash
curl -s -w " [%{http_code}]\n" http://localhost:8000/api/events/NOSUCHCODE
# {"detail":"No showroom found for that event code."} [404]
```

### Seed a showroom over HTTP

Two admin routes, both requiring `X-Admin-Token`. They return `503` if `ADMIN_TOKEN` is unset
and `403` if it does not match.

**Metadata for videos already hosted elsewhere** — no transcoding, added instantly:

```bash
curl -X POST http://localhost:8000/api/events/sandbox/seed \
  -H "X-Admin-Token: local-admin-token" \
  -H "Content-Type: application/json" \
  -d '{"videos":[{
        "title":"Opening Keynote",
        "videoUrl":"https://media.w3.org/2010/05/sintel/trailer_hd.mp4",
        "thumbnailUrl":"/images/thumbnails/v1.jpg",
        "duration":"12:00",
        "channelName":"Vibetube"
      }]}'
# {"created":["v_..."],"count":1}
```

**A real file**, run through the full transcoder pipeline. This route ignores the upload window,
so organizers can seed a room before it opens or top it up after it closes:

```bash
curl -X POST http://localhost:8000/api/events/LOCKED/seed-upload \
  -H "X-Admin-Token: local-admin-token" \
  -F "title=Organizer Clip" \
  -F "videoFile=@/tmp/test-clip.mp4"
```

### Testing the processing state

Locally there is no transcoder, so uploads are `ready` on arrival and you will not see the
processing card. To exercise it, set a row's status by hand and watch the grid update — the
showroom polls every 5 seconds while anything is processing:

```bash
sqlite3 backend/vibetube.db \
  "UPDATE videos SET status='processing' WHERE id='<video-id>';"
# The card switches to a spinner within ~5s, then back when you set it to 'ready'.
```

In the cloud this happens on its own: uploads start as `processing`, and the transcoder's
callback flips them to `ready` (or `failed`) when the job finishes.

---

## Deploying to Google Cloud

`deploy.sh` provisions everything and deploys one Cloud Run service plus one Cloud Run job. It
is idempotent — existing buckets, database instances, and registries are detected and skipped.

### Prerequisites

- `gcloud` CLI, authenticated (`gcloud auth login`)
- A GCP project with billing enabled
- Docker is **not** required locally; images build with Cloud Build

### Configure

```bash
cp .env.example .env
```

`.env` needs exactly **one** value — the project to deploy into:

```bash
PROJECT_ID=vibetube-streaming-platform
```

**There are no credentials in `.env`, and none in `deploy.sh`.** The database password, the
transcoder callback token, and the admin token are generated *inside GCP* on the first deploy
and stored in Secret Manager. Cloud Run reads them at runtime through `--set-secrets`. Nothing
sensitive is written to disk, so there is nothing on a laptop or in a commit to leak.

Re-running `deploy.sh` never rotates an existing secret — it only creates missing ones.

Before touching anything, the script checks that the project exists, that **billing is enabled**,
and that `.env` is present. Each failure names the actual cause instead of surfacing several
steps later as a confusing API error.

To read a secret back when you need it:

```bash
gcloud secrets versions access latest --secret=vibetube-admin-token --project=$PROJECT_ID
```

Everything else has a default and is optional. Bucket names derive from `PROJECT_ID`
(`<project>-raw-videos`, `<project>-public-streams`) because bucket names are globally
unique — deriving them keeps two deployments from colliding. Override any of them in
`.env` only when adopting resources that already exist under other names.

The tuning knobs stay in `deploy.sh`; they are not secrets, and they are explained in
[Limits and blast radius](#limits-and-blast-radius).

### Deploy

```bash
./deploy.sh
```

It prints the service URL on completion. The first run takes 10–15 minutes, mostly waiting on
Cloud SQL provisioning.

### What gets created

| Resource | Name | Purpose |
|---|---|---|
| GCS bucket | `<project>-raw-videos` | Private. Original uploads |
| GCS bucket | `<project>-public-streams` | Public + CORS. HLS segments and thumbnails |
| Cloud SQL | `vibetube-db-instance` | PostgreSQL 15, `db-g1-small` |
| Artifact Registry | `vibetube` | Docker images |
| Cloud Run service | `vibetube-service` | The whole app: API + frontend |
| Cloud Run job | `transcoder-job` | FFmpeg, triggered per upload |
| Secret Manager | `vibetube-database-url` | Full Postgres DSN, generated on first deploy |
| Secret Manager | `vibetube-transcoder-token` | Transcoder callback auth |
| Secret Manager | `vibetube-admin-token` | Guards the seeding endpoints |

Two images are built: `app` (from the root `Dockerfile`, build context is the repo root so it
can reach both `frontend/` and `backend/`) and `transcoder`.

### Adopting an existing deployment

Resources are named `vibetube-*` and buckets derive from `PROJECT_ID`. If you are pointing at a
project that already holds resources under the old `vibeflix-*` names, **do not just rename
them** — a GCP project ID is fixed for the life of the project, and bucket and Cloud SQL
instance names are global identifiers rather than editable labels. Pointing the script at a
different name provisions an empty replacement and strands the media in the old bucket. Set the
existing names explicitly in `.env` instead (`RAW_BUCKET`, `PUBLIC_BUCKET`,
`DB_INSTANCE_NAME`, `DB_NAME`, `REPO_NAME`).

Cloud Run services are the exception: stateless and cheap to replace. Any service left over
from an earlier layout (`frontend-service`, `backend-service`, `vibeflix-service`) keeps
running and serving stale code until removed — `deploy.sh` detects them and prints the delete
commands rather than removing them for you.

Transcoded media is namespaced per event at `gs://<public-bucket>/<eventCode>/<videoId>/`, so a
finished event's media can be removed in one command.

The backend runs its schema migration on startup, so a deploy against an existing database
migrates it in place.

### Limits and blast radius

Uploads are anonymous by design — the event code is the only gate, and anyone holding a link
can post while the window is open. These settings bound what that can cost.

| Setting | Default | Bounds |
|---|---|---|
| `MAX_UPLOAD_BYTES` | 50 MB | Storage per upload |
| `MAX_UPLOADS_PER_EVENT` | 300 per showroom | Total guest uploads |
| `MAX_CONCURRENT_TRANSCODES` | 20 per showroom | Simultaneous billed Cloud Run Jobs |
| `MAX_CONCURRENT_VIEWERS` | 2000 per showroom | Simultaneous viewers |
| `MAX_INSTANCES` | 10 | Cloud Run scale-out |
| `DB_POOL_MAX` | 5 per instance | Cloud SQL connections |
| `DB_TIER` | `db-g1-small` | Database capacity and connection ceiling |
| `MEMORY` | 1Gi | Instance memory |

> **Polling is the dominant load, not the database tier.** A 300-video room serialises to
> ~111 KB per video-list response. At 2000 viewers polling every 5s that is ~400 req/s and
> ~43 MB/s of egress — roughly 150 GB/hour — and no instance size fixes it. The cheap fix is a
> lightweight version endpoint that clients poll instead, refetching the full list only when it
> changes. See [Known gaps](#known-gaps).

Two relationships are load-bearing:

**`MAX_INSTANCES` × `DB_POOL_MAX` must stay under the Cloud SQL connection ceiling.** Every
instance holds its own pool, and the tier sets the ceiling. `db-f1-micro` and `db-g1-small`
are both shared-core; `db-n1-standard-1` is the first with a dedicated vCPU. The
defaults give 10 × 5 = 50. Raising either without moving to a larger tier produces
connection-exhaustion errors under load.

**`MAX_UPLOAD_BYTES` must stay well under `MEMORY`.** Cloud Run's filesystem is in-memory, and
the multipart body is buffered in full before the size check can run — so the ceiling has to
leave room for the buffered body plus the process itself.

Connections are pooled rather than opened per request. When every connection is busy, callers
queue for up to `DB_POOL_TIMEOUT` seconds and then receive a retryable `503` with `Retry-After`,
rather than a 500.

### Creating events in the cloud

The admin CLI talks to the database directly, so point it at Cloud SQL through the
[Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/sql-proxy):

```bash
cloud-sql-proxy $PROJECT_ID:us-central1:vibetube-db-instance &

cd backend
# The DSN lives in Secret Manager; rewrite its socket host for the proxy.
export DATABASE_URL="$(gcloud secrets versions access latest \
    --secret=vibetube-database-url --project=$PROJECT_ID \
  | sed 's#@/#@127.0.0.1:5432/#; s#?host=.*##')"
python admin.py create-event --name "Vibe Summit 2026" --code SUMMIT \
  --opens "2026-09-01 09:00" --closes "2026-09-01 18:00" --tz America/Los_Angeles
```

Share the resulting `https://<service-url>/e/SUMMIT`. `deploy.sh` prints these exact commands,
with your project's values filled in, when it finishes.

---

## Known gaps

- **Event codes are shareable, not secret.** Anyone with the URL can watch, and can upload while
  the window is open. The window is the only upload control; there is no delete endpoint.
- **The size check runs after the body is received.** FastAPI parses the whole multipart body
  before the endpoint executes, so the cap prevents the *storage* cost but not the transfer.
  Rejecting on `Content-Length` in middleware would make oversized uploads cost one round-trip
  instead of a full transfer.
- **No total storage cap.** `MAX_UPLOAD_BYTES` is per request. Nothing bounds cumulative
  uploads per showroom or per day; that needs byte accounting and a `SUM` check per event.
- **The transcode cap can wedge.** It counts rows with `status='processing'`. If a transcoder
  dies without reporting back, those rows stay `processing` forever and the showroom is stuck
  at its ceiling. A staleness timeout on that count would fix it.
- **The video list is polled in full.** Every viewer refetches all ~111 KB every 5s while
  anything is queued or processing. At 2000 viewers that is ~43 MB/s of egress for data that
  rarely changes. A `version` endpoint returning a count and a last-changed marker, with the
  full list fetched only on change, would cut that by orders of magnitude. This is the single
  highest-value change left.
- **The queue has no cross-instance lock.** `claim_next_pending` flips status in the same
  statement that selects, so two instances cannot claim the same row — but the drain loop
  itself can run concurrently on several instances, briefly exceeding
  `MAX_CONCURRENT_TRANSCODES` under a burst. Bounded and self-correcting, not exact.
- **One unreportable failure.** If the transcoder finishes but cannot reach the backend, the
  video stays `processing` until the stale sweep fails it — so the video is lost even though
  its media transcoded fine. A retry queue would fix it properly.
- **Presence is the only hot write path.** Up to 2000 rows per room rewritten every 30s. It is
  the natural first thing to move to Memorystore if the database tier becomes the constraint.
- **`userId` is a dead column.** Always `NULL` since Firebase auth was removed. Harmless, but
  dropping it is a destructive migration and has not been done.
- **No view counting.** Removed rather than faked. Adding it means a write endpoint, which is
  trivially spammable without a rate limit, and meaningful dedupe needs shared state
  (Memorystore) because in-memory counters do not work across Cloud Run instances.
- **No CI/CD and no migration framework.** Schema changes are hand-rolled `ALTER TABLE`
  statements in `backend/database.py`.

---

## Building the frontend alone

The root `Dockerfile` runs this for you; these are only useful for checking a build or
debugging the bundle in isolation.

```bash
cd frontend
npm run build       # tsc + vite build -> dist/
npm run preview     # serve the bundle alone, with no API behind it
```

Note that `npm run preview` has no backend, so every showroom will fail to load. To see the
production build working, run the container instead.
