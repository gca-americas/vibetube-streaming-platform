import json
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="Vibeflix API")

# Add CORS Middleware to support direct API hits or dev proxy bypass
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load data on start
VIDEOS_PATH = os.path.join(os.path.dirname(__file__), "mockVideos.json")
try:
    with open(VIDEOS_PATH, "r") as f:
        videos_data = json.load(f)
except Exception as e:
    videos_data = []
    print(f"Error loading mockVideos.json: {e}")

@app.get("/api/videos")
def get_videos():
    return JSONResponse(content=videos_data)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
