import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

DATABASE_PATH = os.path.join(os.path.dirname(__file__), "vibetube.db")
DATABASE_URL = os.getenv("DATABASE_URL")

# Every video created before events existed belongs to this event.
SANDBOX_EVENT_CODE = "sandbox"

# Playback readiness.
#   PENDING    accepted and queued; no transcoder job exists yet
#   PROCESSING a transcoder job is running for this row
#   READY      playable
#   FAILED     transcoding failed, or the job never started
#
# PENDING is what lets an upload always succeed. Without it the only way to
# bound concurrent transcodes was to reject the upload outright, which turned
# a busy showroom into a wall of errors.
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

# A job that dies without reporting back would otherwise hold its slot for
# ever. Rows processing longer than this are treated as dead: the slot is
# released and the row marked failed.
TRANSCODE_STALE_MINUTES = int(os.getenv("TRANSCODE_STALE_MINUTES", "30"))

# Where a row came from. Only guest uploads count against a showroom's
# upload cap; seeded content is placed by an organiser and is exempt.
SOURCE_SEED = "seed"
SOURCE_UPLOAD = "upload"

# How long a heartbeat keeps a viewer counted as present. Must comfortably
# exceed the client's heartbeat interval, or a viewer flickers out between
# beats and the room appears emptier than it is.
PRESENCE_TTL_SECONDS = int(os.getenv("PRESENCE_TTL_SECONDS", "90"))

# Per-instance Postgres pool size. Cloud SQL caps total connections per
# instance, and Cloud Run runs many app instances against one database, so the
# real budget is DB_POOL_MAX x Cloud Run max-instances. See deploy.sh, which
# pins max-instances so that product stays under the tier's ceiling.
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "5"))

# How long a request waits for a free connection before giving up. Failing
# fast beats stacking requests behind a saturated database.
DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "10"))

_pool = None
_pool_lock = threading.Lock()
# psycopg2's ThreadedConnectionPool raises the moment it is exhausted instead
# of waiting, which would turn a burst of traffic into 500s. This gates entry
# so callers queue for a connection rather than being rejected outright.
_pool_slots = threading.BoundedSemaphore(DB_POOL_MAX)


class DatabaseBusy(Exception):
    """Every pooled connection was in use and none freed within the timeout."""


def _get_pool():
    """Builds the Postgres connection pool on first use.

    Opening a fresh connection per request means a TCP handshake plus auth on
    every call, which is what let ordinary traffic exhaust the database. The
    pool is created lazily and behind a lock so concurrent first requests
    cannot each build one.
    """
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            from psycopg2.pool import ThreadedConnectionPool

            class DictConnection(psycopg2.extensions.connection):
                def cursor(self, *args, **kwargs):
                    kwargs.setdefault("cursor_factory", RealDictCursor)
                    return super().cursor(*args, **kwargs)

            # minconn == maxconn on purpose. psycopg2 closes any returned
            # connection above minconn, so a lower floor would keep
            # reconnecting under load -- the very cost pooling exists to
            # avoid. Holding the full set keeps the per-instance count fixed
            # and predictable, which is what the deploy-time budget assumes.
            _pool = ThreadedConnectionPool(
                minconn=DB_POOL_MAX,
                maxconn=DB_POOL_MAX,
                dsn=DATABASE_URL,
                connection_factory=DictConnection,
            )
    return _pool


@contextmanager
def get_db_conn():
    if DATABASE_URL:
        pool = _get_pool()
        if not _pool_slots.acquire(timeout=DB_POOL_TIMEOUT):
            raise DatabaseBusy()
        try:
            conn = pool.getconn()
        except Exception:
            # Never hold a slot for a connection that was not handed out.
            _pool_slots.release()
            raise
        try:
            yield conn
        finally:
            # Callers commit explicitly. Roll back unconditionally before
            # returning the connection: a no-op when nothing is open, and the
            # only way to clear an aborted transaction left by a failed
            # statement, which would otherwise break the next borrower.
            try:
                conn.rollback()
                pool.putconn(conn)
            except Exception:
                # Connection is unusable -- discard it so the pool replaces it.
                pool.putconn(conn, close=True)
            finally:
                _pool_slots.release()
    else:
        # SQLite is a local file used only in development; pooling it would
        # add contention rather than remove it.
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

def scalar(row):
    """Extracts the first column from a row, regardless of cursor row type.

    SQLite rows are tuple-like; the Postgres RealDictCursor returns dicts.
    """
    if row is None:
        return None
    # RealDictCursor rows subclass dict; sqlite3.Row exposes keys() but not
    # values(), so it has to fall through to positional access.
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]

def utc_now_iso() -> str:
    """Current time as an ISO-8601 UTC string, the storage format for timestamps."""
    return datetime.now(timezone.utc).isoformat()

def new_video_id() -> str:
    """Generates a globally unique video id.

    Ids must be unique across every event: transcoder output paths and the
    transcode-complete callback are both keyed on the video id alone.
    """
    return f"v_{uuid.uuid4().hex[:12]}"

def load_seed_videos() -> list:
    """Reads the default seed video set shipped with the backend."""
    json_path = os.path.join(os.path.dirname(__file__), "mockVideos.json")
    if not os.path.exists(json_path):
        return []
    with open(json_path, "r") as f:
        return json.load(f)

def insert_video(cursor, video: dict, event_code: str) -> str:
    """Inserts a single video row into an event and returns its new id."""
    video_id = video.get("id") or new_video_id()
    cursor.execute(query_placeholder("""
        INSERT INTO videos (
            id, eventId, title, description, thumbnailUrl, videoUrl,
            duration, createdAt, channelName, channelAvatar,
            userId, status, processingStartedAt, source, projectId
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """), (
        video_id,
        event_code,
        video.get("title", "Untitled"),
        video.get("description", ""),
        video.get("thumbnailUrl", "?"),
        video.get("videoUrl", ""),
        video.get("duration", "0:00"),
        video.get("createdAt") or utc_now_iso(),
        video.get("channelName", "VibeCreator"),
        video.get("channelAvatar", "?"),
        video.get("userId"),
        # Seeded and externally hosted rows are watchable immediately; only
        # rows bound for the transcoder start out queued.
        video.get("status", STATUS_READY),
        video.get("processingStartedAt"),
        video.get("source", SOURCE_SEED),
        video.get("projectId"),
    ))
    return video_id


def new_ad_id() -> str:
    return f"ad_{uuid.uuid4().hex[:12]}"


def find_ad(cursor, event_code: str, project_id: str):
    """The active ad for a project in this showroom, or None."""
    cursor.execute(query_placeholder("""
        SELECT * FROM ads
        WHERE eventId = ? AND projectId = ? AND active = 1
        LIMIT 1
    """), (event_code, project_id))
    return normalize_row(cursor.fetchone())


def list_ads(cursor, event_code: str) -> list:
    cursor.execute(query_placeholder(
        "SELECT * FROM ads WHERE eventId = ? ORDER BY createdAt DESC, id"
    ), (event_code,))
    return [normalize_row(row) for row in cursor.fetchall()]


def upsert_ad(cursor, event_code: str, project_id: str, message: str,
              image_url: Optional[str]) -> str:
    """Creates or replaces the ad for a project.

    Re-submitting is how an advertiser corrects their copy, so this replaces
    rather than erroring. The image is preserved when the resubmission omits
    one -- same reasoning as replacing a video, where dropping the picture is
    almost never what was meant. Reactivates a previously disabled ad.
    """
    now = utc_now_iso()
    existing = find_ad_any_state(cursor, event_code, project_id)
    if existing:
        cursor.execute(query_placeholder("""
            UPDATE ads
            SET message = ?, imageUrl = COALESCE(?, imageUrl),
                active = 1, updatedAt = ?
            WHERE id = ?
        """), (message, image_url, now, existing["id"]))
        return existing["id"]

    ad_id = new_ad_id()
    cursor.execute(query_placeholder("""
        INSERT INTO ads (id, eventId, projectId, message, imageUrl, active, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
    """), (ad_id, event_code, project_id, message, image_url, now, now))
    return ad_id


def find_ad_any_state(cursor, event_code: str, project_id: str):
    """Like find_ad but ignores `active`, so a disabled ad can be revived."""
    cursor.execute(query_placeholder(
        "SELECT * FROM ads WHERE eventId = ? AND projectId = ? LIMIT 1"
    ), (event_code, project_id))
    return normalize_row(cursor.fetchone())


def set_ads_active(cursor, event_code: str, active: bool) -> int:
    """Switches every ad in a showroom on or off. Returns rows affected."""
    cursor.execute(query_placeholder(
        "UPDATE ads SET active = ?, updatedAt = ? WHERE eventId = ?"
    ), (1 if active else 0, utc_now_iso(), event_code))
    return cursor.rowcount or 0


def find_by_project(cursor, event_code: str, project_id: str):
    """The existing video for a project id in this showroom, or None."""
    cursor.execute(query_placeholder(
        "SELECT * FROM videos WHERE eventId = ? AND projectId = ? LIMIT 1"
    ), (event_code, project_id))
    return normalize_row(cursor.fetchone())


def replace_video(cursor, video_id: str, video: dict):
    """Overwrites an existing row's content, keeping its id.

    Updating in place rather than deleting and re-inserting keeps every link
    that was already shared (`/e/CODE?v=<id>`) pointing at the right video, and
    means a replacement does not count against the showroom's upload cap.

    channelAvatar is preserved when the re-upload omits one -- someone
    replacing a video rarely means to drop their picture. thumbnailUrl is not:
    the old poster frame belongs to the old video, so it resets to the
    placeholder and lets the transcoder generate a fresh one.
    """
    cursor.execute(query_placeholder("""
        UPDATE videos SET
            title = ?,
            description = ?,
            videoUrl = ?,
            thumbnailUrl = ?,
            duration = ?,
            channelName = ?,
            channelAvatar = COALESCE(?, channelAvatar),
            createdAt = ?,
            status = ?,
            processingStartedAt = NULL
        WHERE id = ?
    """), (
        video.get("title", "Untitled"),
        video.get("description", ""),
        video.get("videoUrl", ""),
        video.get("thumbnailUrl", "?"),
        video.get("duration", "0:00"),
        video.get("channelName", "Anonymous Vibe"),
        video.get("channelAvatar"),
        video.get("createdAt") or utc_now_iso(),
        video.get("status", STATUS_READY),
        video_id,
    ))

def sweep_stale_transcodes(cursor) -> int:
    """Fails rows whose transcoder died without reporting back.

    Without this a lost job holds its concurrency slot for ever, and a
    showroom that loses a few jobs stops accepting new transcodes entirely.
    Rows with no processingStartedAt predate the column, so they are swept
    too rather than being allowed to pin a slot indefinitely.
    """
    cutoff = (
        datetime.now(timezone.utc) - timedelta(minutes=TRANSCODE_STALE_MINUTES)
    ).isoformat()
    cursor.execute(query_placeholder("""
        UPDATE videos SET status = ?
        WHERE status = ? AND (processingStartedAt IS NULL OR processingStartedAt < ?)
    """), (STATUS_FAILED, STATUS_PROCESSING, cutoff))
    return cursor.rowcount or 0


def count_by_status(cursor, event_code: str, status: str) -> int:
    cursor.execute(query_placeholder(
        "SELECT COUNT(*) FROM videos WHERE eventId = ? AND status = ?"
    ), (event_code, status))
    return scalar(cursor.fetchone()) or 0


def count_uploads(cursor, event_code: str) -> int:
    """Guest uploads in a showroom, in any state. Seeded rows do not count."""
    cursor.execute(query_placeholder(
        "SELECT COUNT(*) FROM videos WHERE eventId = ? AND source = ?"
    ), (event_code, SOURCE_UPLOAD))
    return scalar(cursor.fetchone()) or 0


def claim_next_pending(cursor, event_code: str):
    """Moves the oldest queued row into PROCESSING and returns it.

    Returns None when the queue is empty. The status is flipped in the same
    statement that selects the row so two instances draining concurrently
    cannot both claim it -- the second sees zero rows updated.
    """
    cursor.execute(query_placeholder("""
        SELECT id, videoUrl FROM videos
        WHERE eventId = ? AND status = ?
        ORDER BY createdAt, id
        LIMIT 1
    """), (event_code, STATUS_PENDING))
    row = normalize_row(cursor.fetchone())
    if not row:
        return None

    cursor.execute(query_placeholder("""
        UPDATE videos SET status = ?, processingStartedAt = ?
        WHERE id = ? AND status = ?
    """), (STATUS_PROCESSING, utc_now_iso(), row["id"], STATUS_PENDING))
    if not cursor.rowcount:
        return None
    return row


def touch_presence(cursor, event_code: str, client_id: str):
    """Records a heartbeat, then counts everyone currently present.

    Expired rows are deleted on the way through, which keeps the table from
    growing without needing a scheduled cleanup.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=PRESENCE_TTL_SECONDS)).isoformat()

    cursor.execute(query_placeholder(
        "DELETE FROM event_presence WHERE lastSeenAt < ?"
    ), (cutoff,))

    # Upsert: the same viewer reappearing must refresh rather than duplicate.
    cursor.execute(query_placeholder(
        "UPDATE event_presence SET lastSeenAt = ? WHERE eventId = ? AND clientId = ?"
    ), (now.isoformat(), event_code, client_id))
    if not cursor.rowcount:
        cursor.execute(query_placeholder(
            "INSERT INTO event_presence (eventId, clientId, lastSeenAt) VALUES (?, ?, ?)"
        ), (event_code, client_id, now.isoformat()))

    cursor.execute(query_placeholder(
        "SELECT COUNT(*) FROM event_presence WHERE eventId = ? AND lastSeenAt >= ?"
    ), (event_code, cutoff))
    return scalar(cursor.fetchone()) or 0


def count_present(cursor, event_code: str, exclude_client: str = None) -> int:
    """Viewers seen within the TTL, optionally ignoring one client."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=PRESENCE_TTL_SECONDS)
    ).isoformat()
    if exclude_client:
        cursor.execute(query_placeholder("""
            SELECT COUNT(*) FROM event_presence
            WHERE eventId = ? AND lastSeenAt >= ? AND clientId <> ?
        """), (event_code, cutoff, exclude_client))
    else:
        cursor.execute(query_placeholder(
            "SELECT COUNT(*) FROM event_presence WHERE eventId = ? AND lastSeenAt >= ?"
        ), (event_code, cutoff))
    return scalar(cursor.fetchone()) or 0


def seed_event(cursor, event_code: str) -> int:
    """Gives an event its own fresh copy of the default seed videos.

    Copies get new ids so the same seed set can exist in every event at once.
    The rows point at externally hosted media, so this costs no storage.
    """
    seeds = load_seed_videos()
    for seed in seeds:
        copy = dict(seed)
        copy.pop("id", None)
        insert_video(cursor, copy, event_code)
    return len(seeds)

def create_event(cursor, code: str, name: str, opens_at, closes_at, with_seed: bool = True) -> int:
    """Creates an event row and optionally seeds it. Returns the seeded count."""
    cursor.execute(query_placeholder("""
        INSERT INTO events (code, name, uploadOpensAt, uploadClosesAt, createdAt)
        VALUES (?, ?, ?, ?, ?)
    """), (code, name, opens_at, closes_at, utc_now_iso()))
    return seed_event(cursor, code) if with_seed else 0

# Every camelCase column across both tables, keyed by its lowercase form.
# Postgres folds unquoted identifiers, so `SELECT *` there yields `createdat`
# and `uploadopensat` where SQLite yields `createdAt` and `uploadOpensAt`.
# Rows are normalised back to these spellings on the way out so that callers --
# the window logic and the entire frontend contract -- see one shape whichever
# engine is behind them.
_CANONICAL_FIELDS = (
    "id", "eventId", "title", "description", "thumbnailUrl", "videoUrl",
    "duration", "createdAt", "channelName", "channelAvatar", "userId", "status",
    "processingStartedAt", "source", "projectId",
    "code", "name", "uploadOpensAt", "uploadClosesAt", "adsClosesAt",
    "clientId", "lastSeenAt",
    "message", "imageUrl", "active", "updatedAt",
)
_CANONICAL_BY_LOWER = {field.lower(): field for field in _CANONICAL_FIELDS}

def normalize_row(row):
    """Restores canonical camelCase keys on a result row."""
    if row is None:
        return None
    return {
        _CANONICAL_BY_LOWER.get(str(key).lower(), key): value
        for key, value in dict(row).items()
    }

def get_event(cursor, code: str):
    """Looks up a single event by code. Returns a dict or None."""
    cursor.execute(query_placeholder("SELECT * FROM events WHERE code = ?"), (code,))
    return normalize_row(cursor.fetchone())

def _column_names(cursor, table: str) -> set:
    """Existing column names for a table, lowercased.

    Postgres folds unquoted identifiers to lower case, so a column declared as
    `userId` is stored as `userid`, while SQLite preserves the original
    spelling. Comparing case-sensitively therefore reports every camelCase
    column as missing on Postgres, and the follow-up ALTER fails with
    DuplicateColumn. Normalising both sides keeps the check portable.
    """
    if DATABASE_URL:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {str(scalar(row)).lower() for row in cursor.fetchall()}
    cursor.execute(f"PRAGMA table_info({table})")
    return {str(row[1]).lower() for row in cursor.fetchall()}

def _add_column_if_missing(cursor, table: str, column: str, ddl_type: str):
    if column.lower() not in _column_names(cursor, table):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")

VIDEOS_DDL = """
    CREATE TABLE IF NOT EXISTS videos (
        id TEXT PRIMARY KEY,
        eventId TEXT,
        title TEXT NOT NULL,
        description TEXT,
        thumbnailUrl TEXT,
        videoUrl TEXT,
        duration TEXT,
        -- No view counting: there is no endpoint that records a play, so any
        -- number here would be decoration. createdAt is the real upload time.
        createdAt TEXT,
        channelName TEXT,
        channelAvatar TEXT,
        userId TEXT,
        status TEXT DEFAULT 'ready',
        -- When the row was handed to a transcoder. Used to detect jobs that
        -- died without reporting back; null unless status is 'processing'.
        processingStartedAt TEXT,
        -- Submitter's project identifier. Unique within a showroom, absent on
        -- seeded rows.
        projectId TEXT
    )
"""

# Presence heartbeats, used to cap concurrent viewers per showroom. Rows are
# transient: anything older than the TTL is swept on the next heartbeat.
ADS_DDL = """
    CREATE TABLE IF NOT EXISTS ads (
        id TEXT PRIMARY KEY,
        eventId TEXT NOT NULL,
        -- Matches videos.projectId: an ad plays before that project's video.
        projectId TEXT NOT NULL,
        message TEXT NOT NULL,
        -- Null for a text-only ad, which gets the animated treatment instead.
        imageUrl TEXT,
        active INTEGER DEFAULT 1,
        createdAt TEXT,
        updatedAt TEXT
    )
"""

PRESENCE_DDL = """
    CREATE TABLE IF NOT EXISTS event_presence (
        eventId TEXT NOT NULL,
        clientId TEXT NOT NULL,
        lastSeenAt TEXT NOT NULL,
        PRIMARY KEY (eventId, clientId)
    )
"""

EVENTS_DDL = """
    CREATE TABLE IF NOT EXISTS events (
        code TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        uploadOpensAt TEXT,
        uploadClosesAt TEXT,
        createdAt TEXT
    )
"""

def init_db():
    """Creates tables, migrates pre-event rows into the sandbox event, and seeds it."""
    with get_db_conn() as conn:
        cursor = conn.cursor()

        cursor.execute(EVENTS_DDL)
        cursor.execute(VIDEOS_DDL)
        cursor.execute(PRESENCE_DDL)
        cursor.execute(ADS_DDL)
        conn.commit()

        # Lets an organiser switch ads off once the event is over, without a
        # redeploy. Same shape and resolver as the upload window.
        _add_column_if_missing(cursor, "events", "adsClosesAt", "TEXT")
        conn.commit()

        # Columns added after the original single-tenant schema shipped.
        _add_column_if_missing(cursor, "videos", "userId", "TEXT")
        _add_column_if_missing(cursor, "videos", "eventId", "TEXT")
        _add_column_if_missing(cursor, "videos", "createdAt", "TEXT")
        _add_column_if_missing(cursor, "videos", "status", "TEXT")
        _add_column_if_missing(cursor, "videos", "processingStartedAt", "TEXT")
        _add_column_if_missing(cursor, "videos", "projectId", "TEXT")
        # Distinguishes guest uploads from seeded content, so the per-showroom
        # upload cap counts only what guests actually contributed.
        _add_column_if_missing(cursor, "videos", "source", "TEXT")
        conn.commit()

        # Rows predating the column are seed content by definition.
        cursor.execute(query_placeholder(
            "UPDATE videos SET source = ? WHERE source IS NULL"
        ), (SOURCE_SEED,))
        conn.commit()

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_eventId ON videos (eventId)")
        # The queue drains by (event, status) and orders by age on every
        # upload and every callback, so it is worth an index of its own.
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_videos_event_status "
            "ON videos (eventId, status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_presence_event_seen "
            "ON event_presence (eventId, lastSeenAt)"
        )
        # Enforced in the database as well as in the handler: two uploads
        # racing with the same project id would otherwise both pass the
        # application check. Partial, so the many seeded rows with no project
        # id do not collide with each other.
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_videos_event_project "
            "ON videos (eventId, projectId) WHERE projectId IS NOT NULL"
        )
        # One ad per project per showroom; re-submitting replaces it. Enforced
        # in the database as well as the handler so two concurrent submissions
        # cannot both insert.
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_ads_event_project "
            "ON ads (eventId, projectId)"
        )
        conn.commit()

        # The sandbox event always exists; it is where pre-event videos live.
        if not get_event(cursor, SANDBOX_EVENT_CODE):
            cursor.execute(query_placeholder("""
                INSERT INTO events (code, name, uploadOpensAt, uploadClosesAt, createdAt)
                VALUES (?, ?, ?, ?, ?)
            """), (SANDBOX_EVENT_CODE, "Sandbox", None, None, utc_now_iso()))
            conn.commit()

        # Backfill: any video predating the events table belongs to the sandbox.
        cursor.execute(query_placeholder(
            "UPDATE videos SET eventId = ? WHERE eventId IS NULL"
        ), (SANDBOX_EVENT_CODE,))
        conn.commit()

        # Give rows written before createdAt existed a sortable timestamp.
        cursor.execute(query_placeholder(
            "UPDATE videos SET createdAt = ? WHERE createdAt IS NULL"
        ), (utc_now_iso(),))
        conn.commit()

        # Rows predating the status column are already watchable.
        cursor.execute(query_placeholder(
            "UPDATE videos SET status = ? WHERE status IS NULL"
        ), (STATUS_READY,))
        conn.commit()

        # Seed the sandbox only when it is empty, so restarts never duplicate rows.
        cursor.execute(query_placeholder(
            "SELECT COUNT(*) FROM videos WHERE eventId = ?"
        ), (SANDBOX_EVENT_CODE,))
        if scalar(cursor.fetchone()) == 0:
            count = seed_event(cursor, SANDBOX_EVENT_CODE)
            conn.commit()
            print(f"Seeded sandbox event with {count} videos from mockVideos.json")

        print("Database initialized")
