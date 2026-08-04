import os
import shutil
import uvicorn
import uuid
import mimetypes
from fastapi import FastAPI, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from database import init_db, get_db_conn
from auth import get_current_user

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

# Mount static files to serve video uploads
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/api/videos")
def get_videos():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos")
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
    # Save the binary video file
    file_extension = os.path.splitext(videoFile.filename)[1]
    unique_filename = f"{uuid.uuid4().hex}{file_extension}"
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
        cursor.execute("SELECT COUNT(*) FROM videos")
        count = cursor.fetchone()[0]
        video_id = f"v{count + 1}"
        
        # Fallback if ID collides
        cursor.execute("SELECT id FROM videos WHERE id = ?", (video_id,))
        if cursor.fetchone():
            video_id = f"v_{uuid.uuid4().hex[:8]}"
            
        cursor.execute("""
            INSERT INTO videos (
                id, title, description, thumbnailUrl, videoUrl,
                duration, views, uploadedAt, channelName, channelAvatar, userId
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_id,
            title,
            description,
            "/images/thumbnails/v1.jpg", # fallback thumbnail URL
            video_url,
            duration,
            0, # views
            "Just now",
            channel_name,
            channel_avatar,
            user_id
        ))
        conn.commit()
        return {"id": video_id, "status": "success"}

if __name__ == "__main__":
    init_db()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
