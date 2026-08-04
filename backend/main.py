import uvicorn
import uuid
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from database import init_db, get_db_conn

app = FastAPI(title="Vibeflix API")

# Add CORS Middleware to support direct API hits or dev proxy bypass
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field("")
    thumbnailUrl: str = Field("")
    videoUrl: str = Field(..., min_length=1)
    duration: str = Field("3:00")
    channelName: str = Field("VibeCreator")
    channelAvatar: str = Field("/images/avatars/v1.jpg")

@app.get("/api/videos")
def get_videos():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos")
        rows = cursor.fetchall()
        videos = [dict(row) for row in rows]
        return JSONResponse(content=videos)

@app.post("/api/videos")
def create_video(video: VideoCreate):
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
                duration, views, uploadedAt, channelName, channelAvatar
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_id,
            video.title,
            video.description,
            video.thumbnailUrl or "/images/thumbnails/v1.jpg",
            video.videoUrl,
            video.duration,
            0, # views
            "Just now",
            video.channelName,
            video.channelAvatar
        ))
        conn.commit()
        return {"id": video_id, "status": "success"}

if __name__ == "__main__":
    init_db()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
