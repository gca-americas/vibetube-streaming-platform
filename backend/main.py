import os
import shutil
import uvicorn
import uuid
import mimetypes
from fastapi import FastAPI, File, UploadFile, Form, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from database import init_db, get_db_conn, query_placeholder

# Explicitly register HLS MIME types
mimetypes.add_type("application/x-mpegURL", ".m3u8")
mimetypes.add_type("video/MP2T", ".ts")

app = FastAPI(title="Vibeflix API")

# Add CORS Middleware to support direct API hits or dev proxy bypass
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static files to serve video uploads (kept for local development)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

class TranscodeCompletePayload(BaseModel):
    videoUrl: str
    thumbnailUrl: str

def upload_to_gcs(bucket_name: str, file_obj, destination_blob_name: str) -> str:
    """Helper to upload a file object to a GCS bucket and return public URL."""
    from google.cloud import storage
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    file_obj.seek(0)
    blob.upload_from_file(file_obj)
    return f"https://storage.googleapis.com/{bucket_name}/{destination_blob_name}"

def trigger_transcoder_job(video_id: str, unique_filename: str):
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
        output_dir_uri = f"gs://{public_bucket}/{video_id}/"
        
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

from auth import get_current_user

@app.get("/api/videos")
def get_videos():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(query_placeholder("SELECT * FROM videos"))
        rows = cursor.fetchall()
        videos = [dict(row) for row in rows]
        return JSONResponse(content=videos)

@app.post("/api/videos")
async def create_video(
    title: str = Form(...),
    description: str = Form(""),
    duration: str = Form("3:00"),
    videoFile: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    file_extension = os.path.splitext(videoFile.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
    
    raw_bucket = os.getenv("RAW_VIDEOS_BUCKET")
    
    if raw_bucket:
        # Production GCS Upload flow
        try:
            print(f"Uploading raw file {unique_filename} to GCS bucket {raw_bucket}...")
            video_url = upload_to_gcs(raw_bucket, videoFile.file, unique_filename)
            print(f"File uploaded successfully to {video_url}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload video to GCS: {str(e)}")
    else:
        # Local file system fallback
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(videoFile.file, buffer)
        video_url = f"/uploads/{unique_filename}"
    
    # Get user profile information
    user_id = current_user["uid"]
    channel_name = current_user.get("name") or current_user.get("email") or "VibeCreator"
    channel_avatar = current_user.get("picture") or "?"
    
    with get_db_conn() as conn:
        cursor = conn.cursor()
        
        # Determine unique sequential ID (e.g. v9, v10)
        cursor.execute(query_placeholder("SELECT COUNT(*) FROM videos"))
        row = cursor.fetchone()
        count = 0
        if row:
            if isinstance(row, dict) or hasattr(row, 'keys'):
                count = list(row.values())[0]
            else:
                count = row[0]
        video_id = f"v{count + 1}"
        
        # Fallback if ID collides
        cursor.execute(query_placeholder("SELECT id FROM videos WHERE id = ?"), (video_id,))
        if cursor.fetchone():
            video_id = f"v_{uuid.uuid4().hex[:8]}"
            
        cursor.execute(query_placeholder("""
            INSERT INTO videos (
                id, title, description, thumbnailUrl, videoUrl,
                duration, views, uploadedAt, channelName, channelAvatar, userId
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (
            video_id,
            title,
            description,
            "?", # placeholder thumbnail URL until transcode completes
            video_url, # play raw MP4 until transcode overrides it
            duration,
            0, # views
            "Just now",
            channel_name,
            channel_avatar,
            user_id
        ))
        conn.commit()
        
    # Trigger cloud transcoder job asynchronously if raw_bucket is set
    if raw_bucket:
        trigger_transcoder_job(video_id, unique_filename)
        
    return {"id": video_id, "status": "success"}

@app.post("/api/videos/{video_id}/transcode-complete")
def transcode_complete(
    video_id: str,
    payload: TranscodeCompletePayload,
    token: str = Header(None, alias="X-Transcoder-Token")
):
    secret_token = os.getenv("TRANSCODER_SECRET_TOKEN")
    if secret_token and token != secret_token:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            query_placeholder("UPDATE videos SET videoUrl = ?, thumbnailUrl = ? WHERE id = ?"),
            (payload.videoUrl, payload.thumbnailUrl, video_id)
        )
        conn.commit()
    print(f"Video {video_id} transcoding completed. URLs updated to {payload.videoUrl}")
    return {"status": "success"}

if __name__ == "__main__":
    init_db()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
