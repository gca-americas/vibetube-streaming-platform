import json
import os
import sqlite3
from contextlib import contextmanager

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "vibeflix.db")

@contextmanager
def get_db_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    db_exists = os.path.exists(DATABASE_PATH)
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                thumbnailUrl TEXT,
                videoUrl TEXT,
                duration TEXT,
                views INTEGER DEFAULT 0,
                uploadedAt TEXT,
                channelName TEXT,
                channelAvatar TEXT
            )
        """)
        conn.commit()
        
        if not db_exists:
            json_path = os.path.join(os.path.dirname(__file__), "mockVideos.json")
            if os.path.exists(json_path):
                with open(json_path, "r") as f:
                    videos = json.load(f)
                    for video in videos:
                        cursor.execute("""
                            INSERT OR IGNORE INTO videos (
                                id, title, description, thumbnailUrl, videoUrl,
                                duration, views, uploadedAt, channelName, channelAvatar
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            video["id"], video["title"], video["description"],
                            video["thumbnailUrl"], video["videoUrl"], video["duration"],
                            video["views"], video["uploadedAt"], video["channelName"],
                            video["channelAvatar"]
                        ))
                conn.commit()
                print("Database initialized and seeded from mockVideos.json")
