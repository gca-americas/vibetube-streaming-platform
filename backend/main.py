import html
import os
import re
import shutil
import struct
import uvicorn
import uuid
import mimetypes
from contextlib import asynccontextmanager
from typing import List, Optional
from urllib.parse import unquote
from fastapi import FastAPI, File, UploadFile, Form, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from database import (
    init_db, get_db_conn, query_placeholder, get_event, insert_video,
    new_video_id, normalize_row, scalar, utc_now_iso, DatabaseBusy,
    sweep_stale_transcodes, count_by_status, count_uploads, claim_next_pending,
    touch_presence, count_present, find_by_project, replace_video,
    STATUS_PENDING, STATUS_PROCESSING, STATUS_READY, STATUS_FAILED,
    SOURCE_SEED, SOURCE_UPLOAD,
)
from events import public_event, upload_state

# Explicitly register HLS MIME types
mimetypes.add_type("application/x-mpegURL", ".m3u8")
mimetypes.add_type("video/MP2T", ".ts")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # The container starts uvicorn directly, so the __main__ block below never
    # runs in production. Schema creation and the sandbox migration have to
    # happen here or a deployed instance queries tables that do not exist.
    init_db()
    yield

app = FastAPI(title="Vibetube API", lifespan=lifespan)

# Add CORS Middleware to support direct API hits or dev proxy bypass
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(DatabaseBusy)
async def database_busy_handler(request, exc):
    """Surfaces a saturated connection pool as a retryable 503, not a 500."""
    return JSONResponse(
        status_code=503,
        content={"detail": "The server is busy. Please try again in a moment."},
        headers={"Retry-After": "5"},
    )

# Configure upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- Abuse limits -----------------------------------------------------------
# Uploads are deliberately anonymous, so the event code is the only gate and
# anyone holding a link can post. These bound what that costs.

# Largest accepted upload. Kept well under the Cloud Run instance memory
# limit: the filesystem there is in-memory, and Starlette spools the whole
# multipart body before this endpoint runs, so the ceiling has to leave room
# for the buffered body plus the process itself.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
UPLOAD_CHUNK_BYTES = 1024 * 1024

# Avatars and custom video thumbnails. Far smaller than a video, and capped
# separately so a generous video limit does not also permit huge images.
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(5 * 1024 * 1024)))

# Ceiling on videos transcoding at once in one showroom. Each one is a Cloud
# Run Job burning minutes of CPU across three renditions, triggered directly
# with no queue -- so without a cap, N uploads are N concurrent billed jobs.
# Backpressure here is crude but it is the difference between a bounded spend
# and an open one.
MAX_CONCURRENT_TRANSCODES = int(os.getenv("MAX_CONCURRENT_TRANSCODES", "20"))

# Total guest uploads a single showroom will accept, across its whole life.
# Uploads beyond this are refused outright -- unlike the concurrency cap,
# which only defers.
MAX_UPLOADS_PER_EVENT = int(os.getenv("MAX_UPLOADS_PER_EVENT", "300"))

# Viewers allowed in one showroom at a time. Presence is heartbeat-based and
# therefore approximate: a viewer who closes the tab still counts until their
# entry expires (PRESENCE_TTL_SECONDS).
MAX_CONCURRENT_VIEWERS = int(os.getenv("MAX_CONCURRENT_VIEWERS", "2000"))

# Mount static files to serve video uploads (kept for local development)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# The built frontend, copied in by the root Dockerfile. Absent during local
# development, where Vite serves the app and proxies /api here instead.
FRONTEND_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "static"))
FRONTEND_INDEX = os.path.join(FRONTEND_DIR, "index.html")
SERVE_FRONTEND = os.path.isfile(FRONTEND_INDEX)

_INDEX_CACHE: Optional[str] = None


def _index_template() -> str:
    """The built index.html, read once. It never changes within a container."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        with open(FRONTEND_INDEX, encoding="utf-8") as handle:
            _INDEX_CACHE = handle.read()
    return _INDEX_CACHE

class TranscodeCompletePayload(BaseModel):
    videoUrl: str
    thumbnailUrl: str
    # Measured by ffprobe. Empty when the probe failed, in which case the
    # value already on the row is kept.
    duration: str = ""

class TranscodeFailedPayload(BaseModel):
    error: str = "Transcoding failed."

class SeedVideo(BaseModel):
    title: str
    videoUrl: str
    description: str = ""
    thumbnailUrl: str = "?"
    duration: str = "0:00"
    channelName: str = "Vibetube"
    channelAvatar: str = "?"

class SeedPayload(BaseModel):
    videos: List[SeedVideo]

def require_admin(token: Optional[str]):
    """Guards the event-seeding endpoints.

    Fails closed: with no ADMIN_TOKEN configured the endpoints are unusable
    rather than open. Local development sets it in backend/.env.
    """
    secret = os.getenv("ADMIN_TOKEN")
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Admin endpoints are disabled because ADMIN_TOKEN is not configured.",
        )
    if token != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

def upload_to_gcs(bucket_name: str, file_obj, destination_blob_name: str) -> str:
    """Helper to upload a file object to a GCS bucket and return public URL."""
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    file_obj.seek(0)
    blob.upload_from_file(file_obj)
    return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"

def trigger_transcoder_job(video_id: str, unique_filename: str, event_code: str):
    """Triggers the Cloud Run Transcoder Job with environment overrides."""
    from google.cloud import run_v2

    job_name = os.getenv("TRANSCODER_JOB_NAME")
    project = os.getenv("GCP_PROJECT")
    location = os.getenv("GCP_LOCATION", "us-central1")
    raw_bucket = os.getenv("RAW_VIDEOS_BUCKET")
    public_bucket = os.getenv("PUBLIC_STREAMS_BUCKET")
    backend_url = os.getenv("BACKEND_URL")
    secret_token = os.getenv("TRANSCODER_SECRET_TOKEN")

    if not all([job_name, project, raw_bucket, public_bucket]):
        print("GCP variables not fully configured for transcoder job triggering. Skipping job trigger.")
        return False

    try:
        job_path = f"projects/{project}/locations/{location}/jobs/{job_name}"
        input_uri = f"gs://{raw_bucket}/{unique_filename}"
        # Namespaced by event so a finished event's media can be purged wholesale.
        output_dir_uri = f"gs://{public_bucket}/{event_code}/{video_id}/"

        client = run_v2.JobsClient()

        overrides = {
            "container_overrides": [
                {
                    "env": [
                        {"name": "INPUT_GCS_URI", "value": input_uri},
                        {"name": "OUTPUT_GCS_DIR", "value": output_dir_uri},
                        {"name": "VIDEO_ID", "value": video_id},
                        {"name": "BACKEND_URL", "value": backend_url},
                        {"name": "TRANSCODER_SECRET_TOKEN", "value": secret_token}
                    ]
                }
            ]
        }

        request = run_v2.RunJobRequest(
            name=job_path,
            overrides=overrides
        )

        print(f"Triggering Cloud Run Job {job_path} with overrides...")
        operation = client.run_job(request=request)
        print(f"Cloud Run Job run triggered successfully: {operation.metadata}")
        return True
    except Exception as e:
        print(f"Error triggering Cloud Run Job: {e}")
        return False

class UploadTooLarge(Exception):
    """Raised once a request body passes MAX_UPLOAD_BYTES."""


def looks_like_video(head: bytes) -> bool:
    """Sniffs a container signature from the first bytes of an upload.

    The browser's accept="video/*" is a file-picker filter, not a guarantee,
    and the declared content type is caller-supplied. Without this, arbitrary
    bytes can be stored and served with a .mp4 name: locally that reaches the
    player as an undecodable black box, and in the cloud it burns a transcoder
    job before failing. This is a cheap gate, not a full validation -- the
    transcoder remains the real authority on whether a file is usable.
    """
    if len(head) < 12:
        return False
    # ISO base media (mp4/m4v/mov): a 4-byte size then 'ftyp'.
    if head[4:8] == b"ftyp":
        return True
    # Matroska / WebM EBML header.
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return True
    # AVI: 'RIFF' .... 'AVI '
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return True
    # Ogg, FLV, and MPEG program/transport streams.
    if head[:4] == b"OggS" or head[:3] == b"FLV":
        return True
    if head[:3] == b"\x00\x00\x01" or head[0:1] == b"\x47":
        return True
    return False


def looks_like_image(head: bytes) -> bool:
    """Sniffs a still-image signature. Same reasoning as looks_like_video."""
    if len(head) < 12:
        return False
    if head[:3] == b"\xff\xd8\xff":                       # JPEG
        return True
    if head[:8] == b"\x89PNG\r\n\x1a\n":                  # PNG
        return True
    if head[:6] in (b"GIF87a", b"GIF89a"):                # GIF
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":     # WebP
        return True
    return False


def store_optional_image(image_file: Optional[UploadFile], label: str) -> Optional[str]:
    """Validates and stores an optional image, returning its URL or None.

    Kept separate from the video path: images have their own (much smaller)
    ceiling, and an unusable avatar should never fail an otherwise good video
    upload silently -- it raises so the uploader is told which file was wrong.
    """
    if image_file is None or not image_file.filename:
        return None

    file_obj = image_file.file
    file_obj.seek(0)
    head = file_obj.read(12)
    file_obj.seek(0, os.SEEK_END)
    size = file_obj.tell()
    file_obj.seek(0)

    if size == 0:
        return None
    if size > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That {label} is too large. The limit is "
                   f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB.",
        )
    if not looks_like_image(head):
        raise HTTPException(
            status_code=400,
            detail=f"That {label} is not an image. Use a JPEG, PNG, GIF or WebP.",
        )

    extension = os.path.splitext(image_file.filename)[1].lower() or ".jpg"
    unique_filename = f"{uuid.uuid4().hex}{extension}"
    public_bucket = os.getenv("PUBLIC_STREAMS_BUCKET")

    if public_bucket:
        # Straight to the public bucket: these are display assets, not
        # transcoder input, so they need no processing.
        try:
            return upload_to_gcs(public_bucket, file_obj, f"images/{unique_filename}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to store {label}: {e}")

    path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file_obj, buffer)
    return f"/uploads/{unique_filename}"


def enforce_upload_size(video_file: UploadFile):
    """Rejects oversized uploads, streaming rather than trusting the header.

    Uploads are anonymous, so an unbounded body is a direct route to filling a
    bucket and running up storage costs. Content-Length is only a hint -- it is
    absent on chunked requests and trivially wrong -- so the body is measured
    as it is read. Starlette has already spilled anything large to a temp file
    on disk by this point, which caps memory but not disk, so this still has to
    run before the file is copied anywhere durable.
    """
    file_obj = video_file.file
    total = 0
    head = b""
    file_obj.seek(0)
    while True:
        chunk = file_obj.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        if not head:
            head = chunk[:12]
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise UploadTooLarge()
    if total == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if not looks_like_video(head):
        raise HTTPException(
            status_code=400,
            detail="That file does not look like a video. Please upload a video file.",
        )
    file_obj.seek(0)
    return total


def store_raw_upload(video_file: UploadFile) -> tuple:
    """Persists an uploaded file to GCS (or local disk) and returns (url, filename)."""
    file_extension = os.path.splitext(video_file.filename or "")[1]
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    raw_bucket = os.getenv("RAW_VIDEOS_BUCKET")

    if raw_bucket:
        try:
            print(f"Uploading raw file {unique_filename} to GCS bucket {raw_bucket}...")
            video_url = upload_to_gcs(raw_bucket, video_file.file, unique_filename)
            print(f"File uploaded successfully to {video_url}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload video to GCS: {str(e)}")
    else:
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)
        video_url = f"/uploads/{unique_filename}"

    return video_url, unique_filename

def set_video_status(video_id: str, status: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            query_placeholder("UPDATE videos SET status = ? WHERE id = ?"),
            (status, video_id),
        )
        conn.commit()

def drain_queue(code: str) -> int:
    """Starts transcoder jobs for queued videos, up to the concurrency cap.

    Called after an upload and after every transcoder callback, so a freed
    slot is refilled immediately without anything polling. Safe to call at any
    time: if the queue is empty or the cap is reached it does nothing.

    Each job is triggered outside the database transaction that claimed it.
    Holding a connection open across a Cloud Run API call would tie up a pool
    slot for the duration of a network round trip, and the pool is small.
    """
    started = 0
    while True:
        with get_db_conn() as conn:
            cursor = conn.cursor()
            # Reclaim slots held by jobs that died silently before counting.
            swept = sweep_stale_transcodes(cursor)
            if swept:
                print(f"Released {swept} stale transcode slot(s) in {code}")

            if count_by_status(cursor, code, STATUS_PROCESSING) >= MAX_CONCURRENT_TRANSCODES:
                conn.commit()
                return started

            claimed = claim_next_pending(cursor, code)
            conn.commit()

        if not claimed:
            return started

        video_id = claimed["id"]
        # videoUrl holds the raw object name until the transcoder rewrites it.
        raw_name = os.path.basename(claimed.get("videoUrl") or "")
        if trigger_transcoder_job(video_id, raw_name, code):
            started += 1
        else:
            # The job never started, so nothing will ever call back for it.
            set_video_status(video_id, STATUS_FAILED)


def drain_event_of(video_id: str):
    """Drains the queue of whichever showroom a video belongs to.

    The transcoder callbacks identify a video, not an event, so the event has
    to be looked up before the queue can be advanced.
    """
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            query_placeholder("SELECT eventId FROM videos WHERE id = ?"), (video_id,)
        )
        event_code = scalar(cursor.fetchone())
    if event_code:
        drain_queue(event_code)


def ingest_upload(code: str, video_file: UploadFile, title: str, description: str,
                  duration: str, display_name: str, source: str = SOURCE_UPLOAD,
                  project_id: Optional[str] = None,
                  avatar_file: Optional[UploadFile] = None,
                  thumbnail_file: Optional[UploadFile] = None) -> str:
    """Stores an upload, records it, and queues it for transcoding.

    The upload itself always succeeds once it passes validation: the row is
    written PENDING and `drain_queue` starts a job only if the showroom is
    below its concurrency cap. Anything over the cap waits its turn instead of
    being rejected, which is the difference between a busy room and a broken
    one.

    Without GCS configured there is no transcoder, so the raw file is the
    final artifact and the row is immediately READY -- otherwise every locally
    uploaded video would sit queued for ever.
    """
    will_transcode = bool(os.getenv("RAW_VIDEOS_BUCKET"))

    # Validation first: everything here runs before the body is stored, so a
    # rejected upload costs no bucket write.
    try:
        enforce_upload_size(video_file)
    except UploadTooLarge:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"That video is too large. The limit is {limit_mb} MB.",
        )

    project_id = (project_id or "").strip() or None

    # A project id that already exists means "replace that submission", not
    # "reject this one" -- teams iterate, and re-submitting is the normal case.
    existing = None
    if project_id:
        with get_db_conn() as conn:
            cursor = conn.cursor()
            existing = find_by_project(cursor, code, project_id)
            if existing and existing.get("status") in (STATUS_PENDING, STATUS_PROCESSING):
                # Replacing now would leave the in-flight job to call back
                # against a row it no longer describes, overwriting the new
                # video's URLs with the old one's output.
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"The previous upload for project '{project_id}' is still "
                        "processing. Try again once it finishes."
                    ),
                )

    # Organiser seeding is exempt: the cap exists to bound guest contributions,
    # and someone with the admin token can already do as they like. A
    # replacement is exempt too -- it consumes no additional slot.
    if source == SOURCE_UPLOAD and existing is None:
        with get_db_conn() as conn:
            cursor = conn.cursor()
            if count_uploads(cursor, code) >= MAX_UPLOADS_PER_EVENT:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"This showroom has reached its limit of "
                        f"{MAX_UPLOADS_PER_EVENT} uploads."
                    ),
                )

    # Images first: they are small and cheap to reject, so a bad avatar fails
    # before the video is committed to storage.
    avatar_url = store_optional_image(avatar_file, "profile picture")
    thumbnail_url = store_optional_image(thumbnail_file, "video thumbnail")

    video_url, unique_filename = store_raw_upload(video_file)

    fields = {
        "title": title,
        "description": description,
        # "?" is the placeholder the transcoder replaces. A thumbnail the
        # uploader supplied is kept as-is -- see transcode_complete.
        "thumbnailUrl": thumbnail_url or "?",
        "videoUrl": video_url,
        "duration": duration,
        "createdAt": utc_now_iso(),
        "channelName": display_name.strip() or "Anonymous Vibe",
        "status": STATUS_PENDING if will_transcode else STATUS_READY,
    }

    with get_db_conn() as conn:
        cursor = conn.cursor()
        if existing:
            video_id = existing["id"]
            # None, not "?", so COALESCE keeps the previous picture when this
            # re-upload did not include one.
            replace_video(cursor, video_id, {**fields, "channelAvatar": avatar_url})
            print(f"Replaced video {video_id} for project '{project_id}' in {code}")
        else:
            video_id = new_video_id()
            insert_video(cursor, {
                **fields,
                "id": video_id,
                # "?" tells the card to fall back to the uploader's initials.
                "channelAvatar": avatar_url or "?",
                "userId": None,
                "source": source,
                "projectId": project_id,
            }, code)
        conn.commit()

    if will_transcode:
        drain_queue(code)

    return video_id

def load_event_or_404(cursor, code: str) -> dict:
    event = get_event(cursor, code)
    if not event:
        raise HTTPException(status_code=404, detail="No showroom found for that event code.")
    return event

@app.get("/api/events/{code}")
def read_event(code: str):
    """Resolves an event code. A 404 here is what renders the 'no showroom' screen."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        event = load_event_or_404(cursor, code)
        return JSONResponse(content=public_event(event))

class PresencePayload(BaseModel):
    clientId: str


@app.post("/api/events/{code}/presence")
def event_presence(code: str, payload: PresencePayload):
    """Heartbeat that both claims and reports a seat in a showroom.

    Capacity is enforced here rather than at page load so that a viewer who
    stops beating -- closed tab, asleep laptop -- releases their seat on its
    own. The count is therefore approximate by design: someone who leaves
    still occupies a seat until PRESENCE_TTL_SECONDS elapses.

    An already-present viewer is never evicted, so a full room does not start
    throwing people out; it simply stops admitting new ones.
    """
    client_id = payload.clientId.strip()
    if not client_id:
        raise HTTPException(status_code=400, detail="clientId is required.")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        load_event_or_404(cursor, code)

        others = count_present(cursor, code, exclude_client=client_id)
        if others >= MAX_CONCURRENT_VIEWERS:
            conn.commit()
            raise HTTPException(
                status_code=503,
                detail=(
                    f"This showroom is full ({MAX_CONCURRENT_VIEWERS} viewers). "
                    "Try again in a moment."
                ),
            )

        present = touch_presence(cursor, code, client_id)
        conn.commit()

    return {
        "present": present,
        "capacity": MAX_CONCURRENT_VIEWERS,
    }


@app.get("/api/events/{code}/videos")
def get_event_videos(code: str):
    """Lists the videos belonging to one event. Newest first."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        load_event_or_404(cursor, code)
        cursor.execute(query_placeholder(
            "SELECT * FROM videos WHERE eventId = ? ORDER BY createdAt DESC, id"
        ), (code,))
        videos = [normalize_row(row) for row in cursor.fetchall()]
        return JSONResponse(content=videos)

@app.post("/api/events/{code}/videos")
async def create_video(
    code: str,
    title: str = Form(...),
    description: str = Form(""),
    duration: str = Form("3:00"),
    displayName: str = Form("Anonymous Vibe"),
    projectId: str = Form(""),
    videoFile: UploadFile = File(...),
    avatarFile: Optional[UploadFile] = File(None),
    thumbnailFile: Optional[UploadFile] = File(None),
):
    """Anonymous upload into an event, allowed only inside the upload window.

    avatarFile and thumbnailFile are optional. Without an avatar the card falls
    back to the uploader's initials; without a thumbnail the transcoder's
    generated frame is used.
    """
    with get_db_conn() as conn:
        cursor = conn.cursor()
        event = load_event_or_404(cursor, code)

    state = upload_state(event)
    if not state["uploadOpen"]:
        raise HTTPException(status_code=403, detail=state["reason"])

    video_id = ingest_upload(
        code, videoFile, title, description, duration, displayName,
        project_id=projectId, avatar_file=avatarFile, thumbnail_file=thumbnailFile,
    )
    return {"id": video_id, "status": "success"}

@app.post("/api/events/{code}/seed")
def seed_event_metadata(
    code: str,
    payload: SeedPayload,
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Adds pre-seeded videos that are already hosted elsewhere. Admin only."""
    require_admin(token)
    with get_db_conn() as conn:
        cursor = conn.cursor()
        load_event_or_404(cursor, code)
        created = [insert_video(cursor, video.model_dump(), code) for video in payload.videos]
        conn.commit()
    return {"created": created, "count": len(created)}

@app.post("/api/events/{code}/seed-upload")
async def seed_event_upload(
    code: str,
    title: str = Form(...),
    description: str = Form(""),
    duration: str = Form("3:00"),
    displayName: str = Form("Vibetube"),
    videoFile: UploadFile = File(...),
    token: str = Header(None, alias="X-Admin-Token"),
):
    """Admin file upload that runs the full transcode pipeline.

    Deliberately exempt from the upload window: organizers seed rooms before
    they open and top them up after they close.
    """
    require_admin(token)
    with get_db_conn() as conn:
        cursor = conn.cursor()
        load_event_or_404(cursor, code)

    video_id = ingest_upload(code, videoFile, title, description, duration, displayName,
                             source=SOURCE_SEED)
    return {"id": video_id, "status": "success"}

@app.post("/api/videos/{video_id}/transcode-complete")
def transcode_complete(
    video_id: str,
    payload: TranscodeCompletePayload,
    token: str = Header(None, alias="X-Transcoder-Token")
):
    """Transcoder callback.

    Intentionally not window-checked: a video uploaded just before the window
    closes finishes transcoding after it, and rejecting that callback would
    strand the video with a placeholder thumbnail forever.
    """
    secret_token = os.getenv("TRANSCODER_SECRET_TOKEN")
    if secret_token and token != secret_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        # The generated thumbnail only replaces the "?" placeholder. An
        # uploader who supplied their own poster frame keeps it -- otherwise
        # the transcoder would silently discard their choice minutes later.
        cursor.execute(
            query_placeholder("""
                UPDATE videos
                SET videoUrl = ?,
                    thumbnailUrl = CASE WHEN thumbnailUrl IS NULL OR thumbnailUrl = '?'
                                        THEN ? ELSE thumbnailUrl END,
                    duration = CASE WHEN ? <> '' THEN ? ELSE duration END,
                    status = ?
                WHERE id = ?
            """),
            (payload.videoUrl, payload.thumbnailUrl,
             payload.duration, payload.duration, STATUS_READY, video_id)
        )
        conn.commit()
    print(f"Video {video_id} transcoding completed. URLs updated to {payload.videoUrl}")
    # A slot just freed: start the next queued video immediately rather than
    # waiting for someone to upload again.
    drain_event_of(video_id)
    return {"status": "success"}

@app.post("/api/videos/{video_id}/transcode-failed")
def transcode_failed(
    video_id: str,
    payload: TranscodeFailedPayload,
    token: str = Header(None, alias="X-Transcoder-Token")
):
    """Transcoder failure callback.

    Without this a job that dies leaves the video processing forever, since
    the only other write to that row is the success callback.
    """
    secret_token = os.getenv("TRANSCODER_SECRET_TOKEN")
    if secret_token and token != secret_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            query_placeholder("UPDATE videos SET status = ? WHERE id = ?"),
            (STATUS_FAILED, video_id)
        )
        conn.commit()
    print(f"Video {video_id} transcoding failed: {payload.error}")
    # A failure frees its slot too; the queue must not stall on bad videos.
    drain_event_of(video_id)
    return {"status": "recorded"}

# Registered last on purpose: FastAPI matches routes in definition order, so
# every /api route above wins before this catch-all sees the request.
if SERVE_FRONTEND:
    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str, request: Request):
        """Serves the built SPA, falling back to index.html for client routes.

        Deep links like /e/SUMMIT have no file on disk -- the router resolves
        them in the browser -- so anything that is not a real asset returns
        index.html rather than a 404.
        """
        # Unmatched API paths must stay JSON 404s, not the HTML shell.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = os.path.realpath(os.path.join(FRONTEND_DIR, full_path))
        # Containment check: without it, ../ in the URL would escape the build.
        within_build = candidate == FRONTEND_DIR or candidate.startswith(FRONTEND_DIR + os.sep)
        if within_build and os.path.isfile(candidate):
            return FileResponse(candidate)

        # Social crawlers do not run JavaScript, so a client-rendered page has
        # nothing for them to read. The tags have to be in the HTML as served.
        return HTMLResponse(render_index_with_meta(full_path, request))

ANONYMOUS_NAMES = {"", "anonymous vibe", "anonymous"}

# Kept byte-identical to buildShareText in frontend/src/components/
# ShareButtons.tsx, including the pick() hash, so the X post and the LinkedIn
# card say the same thing about the same video.
CREDITED_BLURBS = (
    '🍿 Grab the popcorn — {name} made "{title}" with Google Cloud and Gemini.',
    '🎬 Lights, camera, {name}! "{title}", built with Google Cloud and Gemini.',
    '🚀 {name} shipped it: "{title}", cooked up with Google Cloud and Gemini.',
    '✨ Straight from {name}\'s brain to your screen — "{title}", made with Google Cloud and Gemini.',
    '🤖 {name} + Google Cloud + Gemini = "{title}". Roll the tape.',
    '🎧 {name} hit record and out came "{title}", powered by Google Cloud and Gemini.',
)

ANONYMOUS_BLURBS = (
    '🍿 Grab the popcorn — "{title}", made with Google Cloud and Gemini.',
    '🎬 Lights, camera, "{title}" — built with Google Cloud and Gemini.',
    '🚀 Freshly shipped: "{title}", cooked up with Google Cloud and Gemini.',
    '✨ Someone made "{title}" with Google Cloud and Gemini, and it is worth a look.',
    '🤖 Google Cloud + Gemini = "{title}". Roll the tape.',
    '🎧 Somebody hit record and out came "{title}", powered by Google Cloud and Gemini.',
)


def pick_variant(seed: str, count: int) -> int:
    """Stable index from a seed. Must match pick() in ShareButtons.tsx.

    Deterministic rather than random so a video's share text never changes
    between the card someone sees and the post they publish, while different
    videos still get different lines.

    Hashes UTF-16 code units, not codepoints: JavaScript's charCodeAt yields
    surrogate halves for anything above the BMP, so iterating Python's ord()
    would disagree with the frontend on any seed containing an emoji.
    """
    encoded = (seed or "").encode("utf-16-le")
    units = struct.unpack(f"<{len(encoded) // 2}H", encoded)
    h = 0
    for unit in units:
        h = (h * 31 + unit) & 0xFFFFFFFF
    return h % count


def share_blurb(author: Optional[str], title: str, event_name: str,
                description: Optional[str] = None, limit: int = 300,
                seed: str = "") -> str:
    """The line that appears on a shared card.

    Deliberately playful and in the uploader's voice: this is what someone's
    followers actually read, and a flat "X created Y" reads like a changelog.
    Anonymous uploads use a creator-less phrasing so a card never claims to be
    from "Anonymous Vibe".
    """
    name = (author or "").strip()
    anonymous = name.lower() in ANONYMOUS_NAMES
    variants = ANONYMOUS_BLURBS if anonymous else CREDITED_BLURBS
    template = variants[pick_variant(seed or title, len(variants))]
    blurb = template.format(name=name, title=title)

    extra = (description or "").strip()
    if extra:
        blurb = f"{blurb} {extra}"
    elif event_name:
        blurb = f"{blurb} Now showing in {event_name}."
    # Crawlers truncate long descriptions anyway; doing it here keeps the cut
    # at a word boundary rather than mid-sentence.
    if len(blurb) > limit:
        blurb = blurb[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return blurb


def _absolute(url: Optional[str], request: Request) -> Optional[str]:
    """Makes a stored URL absolute. Crawlers reject relative og:image."""
    if not url or url == "?":
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{str(request.base_url).rstrip('/')}/{url.lstrip('/')}"


def _meta_for(path: str, request: Request) -> dict:
    """Resolves the page being served into share-card metadata.

    Three cases: a single video, a showroom, and everything else. Any database
    failure falls through to the site-level defaults -- a missing preview is a
    far better outcome than a 500 on the page itself.
    """
    site = "Vibetube"
    meta = {
        "title": site,
        "description": "Enter an event code to step into the showroom.",
        "image": _absolute("/logo.svg", request),
        "url": str(request.url),
        "type": "website",
    }

    match = re.match(r"^e/([^/]+)/?$", path)
    if not match:
        return meta

    code = unquote(match.group(1))
    video_id = request.query_params.get("v")

    try:
        with get_db_conn() as conn:
            cursor = conn.cursor()
            event = get_event(cursor, code)
            if not event:
                return meta

            if video_id:
                cursor.execute(
                    query_placeholder(
                        "SELECT * FROM videos WHERE id = ? AND eventId = ?"
                    ),
                    (video_id, code),
                )
                video = normalize_row(cursor.fetchone())
                if video:
                    meta.update({
                        "title": f"{video['title']} — {site}",
                        "description": share_blurb(
                            video.get("channelName"),
                            video["title"],
                            event["name"],
                            video.get("description"),
                            seed=video["id"],
                        ),
                        "image": _absolute(video.get("thumbnailUrl"), request)
                                 or meta["image"],
                        "type": "video.other",
                    })
                    return meta

            meta.update({
                "title": f"{event['name']} — {site}",
                "description": f"Watch what people are sharing in {event['name']}.",
            })
    except Exception as e:
        # Never let preview metadata break page delivery.
        print(f"Could not build share metadata for '{path}': {e}")

    return meta


def render_index_with_meta(path: str, request: Request) -> str:
    """Injects Open Graph and Twitter card tags into the built index.html.

    Every value is HTML-escaped: titles and descriptions are supplied by
    whoever uploaded the video, so injecting them raw would let an uploader
    close the meta tag and write arbitrary markup into the page.
    """
    meta = _meta_for(path, request)
    esc = lambda value: html.escape(str(value or ""), quote=True)

    tags = [
        f'<meta property="og:site_name" content="Vibetube" />',
        f'<meta property="og:type" content="{esc(meta["type"])}" />',
        f'<meta property="og:title" content="{esc(meta["title"])}" />',
        f'<meta property="og:description" content="{esc(meta["description"])}" />',
        f'<meta property="og:url" content="{esc(meta["url"])}" />',
        f'<meta name="description" content="{esc(meta["description"])}" />',
        # LinkedIn reads og:*; X needs its own card type to render an image.
        f'<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{esc(meta["title"])}" />',
        f'<meta name="twitter:description" content="{esc(meta["description"])}" />',
    ]
    if meta["image"]:
        tags.append(f'<meta property="og:image" content="{esc(meta["image"])}" />')
        tags.append(f'<meta name="twitter:image" content="{esc(meta["image"])}" />')

    block = "\n    ".join(tags)
    template = _index_template()
    if "</head>" in template:
        return template.replace("</head>", f"    {block}\n  </head>", 1)
    return block + template


if __name__ == "__main__":
    init_db()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
