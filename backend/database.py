import json
import os
import sqlite3
from contextlib import contextmanager

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "vibeflix.db")
DATABASE_URL = os.getenv("DATABASE_URL")

@contextmanager
def get_db_conn():
    if DATABASE_URL:
        # PostgreSQL integration
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Connection factory returning RealDictCursor by default
        class DictConnection(psycopg2.extensions.connection):
            def cursor(self, *args, **kwargs):
                kwargs.setdefault('cursor_factory', RealDictCursor)
                return super().cursor(*args, **kwargs)
                
        conn = psycopg2.connect(DATABASE_URL, connection_factory=DictConnection)
        try:
            yield conn
        finally:
            conn.close()
    else:
        # SQLite integration
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

def query_placeholder(query: str) -> str:
    """Replaces ? placeholders with %s if using PostgreSQL."""
    if DATABASE_URL:
        return query.replace("?", "%s")
    return query

def init_db():
    if DATABASE_URL:
        # Postgres init
        with get_db_conn() as conn:
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
                    channelAvatar TEXT,
                    userId TEXT
                )
            """)
            conn.commit()
            
            cursor.execute("ALTER TABLE videos ADD COLUMN IF NOT EXISTS userId TEXT")
            conn.commit()
            
            cursor.execute("SELECT COUNT(*) FROM videos")
            row = cursor.fetchone()
            count = 0
            if row:
                if isinstance(row, dict) or hasattr(row, 'keys'):
                    count = list(row.values())[0]
                else:
                    count = row[0]
                    
            if count == 0:
                json_path = os.path.join(os.path.dirname(__file__), "mockVideos.json")
                if os.path.exists(json_path):
                    with open(json_path, "r") as f:
                        videos = json.load(f)
                        for video in videos:
                            cursor.execute(
                                query_placeholder("""
                                    INSERT INTO videos (
                                        id, title, description, thumbnailUrl, videoUrl,
                                        duration, views, uploadedAt, channelName, channelAvatar
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ON CONFLICT (id) DO NOTHING
                                """), (
                                    video["id"], video["title"], video["description"],
                                    video["thumbnailUrl"], video["videoUrl"], video["duration"],
                                    video["views"], video["uploadedAt"], video["channelName"],
                                    video["channelAvatar"]
                                )
                            )
                    conn.commit()
                    print("Postgres database initialized and seeded from mockVideos.json")
    else:
        # Local SQLite init
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
                    channelAvatar TEXT,
                    userId TEXT
                )
            """)
            conn.commit()
            
            cursor.execute("PRAGMA table_info(videos)")
            columns = [row[1] for row in cursor.fetchall()]
            if "userId" not in columns:
                cursor.execute("ALTER TABLE videos ADD COLUMN userId TEXT")
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
