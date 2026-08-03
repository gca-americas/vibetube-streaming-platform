import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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

# Initialize database on startup
init_db()

@app.get("/api/videos")
def get_videos():
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos")
        rows = cursor.fetchall()
        videos = [dict(row) for row in rows]
        return JSONResponse(content=videos)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
