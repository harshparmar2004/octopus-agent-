"""
Peak-Time Scheduler storage layer.

Tables:
  - reel_candidates : Candidate Pool of harvested (not yet posted) reels per niche, with scores
  - niche_schedules : Per-niche peak-slot configuration (IST by default)
  - slot_runs       : Execution log of every planned / pre-rendered / published slot

All timestamps are stored as ISO-8601 UTC strings ("YYYY-MM-DDTHH:MM:SS+00:00").
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from storage.db import get_connection

DEFAULT_SLOT_TIMES = ["08:00", "13:00", "18:00", "21:00"]
OPTIONAL_SLOT_TIMES = ["22:30"]
DEFAULT_TIMEZONE = "Asia/Kolkata"

# Safety guards (per destination account)
MAX_POSTS_PER_ACCOUNT_PER_DAY = 5
MIN_GAP_BETWEEN_POSTS_HOURS = 2.5
CANDIDATE_MAX_AGE_HOURS = 72


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        v = str(value).strip()
        if v.isdigit():
            return datetime.fromtimestamp(int(v), tz=timezone.utc)
        v = v.replace("Z", "+00:00")
        # Meta returns "+0000" offsets
        if len(v) > 5 and (v[-5] in "+-") and v[-3] != ":":
            v = v[:-2] + ":" + v[-2:]
        dt = datetime.fromisoformat(v.replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def init_scheduler_tables() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reel_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche_id TEXT NOT NULL,
            source_id INTEGER,
            source_handle TEXT,
            shortcode TEXT NOT NULL,
            permalink TEXT NOT NULL,
            caption TEXT,
            posted_at TEXT,
            like_count INTEGER,
            comments_count INTEGER,
            view_count INTEGER,
            source_followers INTEGER,
            duration_s REAL,
            media_type TEXT,
            velocity_score REAL DEFAULT 0,
            freshness_score REAL DEFAULT 0,
            niche_fit_score REAL DEFAULT 0,
            quality_score REAL DEFAULT 0,
            final_score REAL DEFAULT 0,
            score_reason TEXT,
            status TEXT DEFAULT 'DISCOVERED',
            pinned INTEGER DEFAULT 0,
            raw_video_path TEXT,
            selected_for_slot INTEGER,
            discovered_at TEXT,
            updated_at TEXT,
            UNIQUE(niche_id, shortcode)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cand_niche_status ON reel_candidates(niche_id, status, final_score)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS niche_schedules (
            niche_id TEXT PRIMARY KEY,
            slot_times TEXT NOT NULL,
            timezone TEXT DEFAULT 'Asia/Kolkata',
            jitter_minutes INTEGER DEFAULT 8,
            fanout_mode TEXT DEFAULT 'balanced',
            approval_mode TEXT DEFAULT 'telegram_timeout',
            approval_timeout_minutes INTEGER DEFAULT 20,
            min_score REAL DEFAULT 35,
            evergreen_fallback INTEGER DEFAULT 1,
            source_diversity INTEGER DEFAULT 1,
            enabled INTEGER DEFAULT 1,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS slot_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            niche_id TEXT NOT NULL,
            slot_time TEXT NOT NULL,
            slot_date TEXT NOT NULL,
            scheduled_for TEXT NOT NULL,
            candidate_id INTEGER,
            reel_id TEXT,
            status TEXT DEFAULT 'PLANNED',
            dry_run INTEGER DEFAULT 1,
            prepared_payload TEXT,
            accounts_total INTEGER DEFAULT 0,
            accounts_posted INTEGER DEFAULT 0,
            accounts_skipped INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            error TEXT,
            created_at TEXT,
            UNIQUE(niche_id, slot_date, slot_time)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_slot_runs_sched ON slot_runs(scheduled_for, status)")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Candidate Pool
# ---------------------------------------------------------------------------
def upsert_candidate(c: Dict[str, Any]) -> Optional[int]:
    """Insert a newly discovered candidate, or refresh its engagement metrics if it already exists.
    Never resets status of candidates already SELECTED/RENDERED/PUBLISHED/REJECTED."""
    now = to_iso(utcnow())
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, status FROM reel_candidates WHERE niche_id = ? AND shortcode = ?",
                (c["niche_id"], c["shortcode"]))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE reel_candidates
               SET like_count = COALESCE(?, like_count),
                   comments_count = COALESCE(?, comments_count),
                   view_count = COALESCE(?, view_count),
                   source_followers = COALESCE(?, source_followers),
                   caption = COALESCE(NULLIF(?, ''), caption),
                   updated_at = ?
             WHERE id = ?
        """, (c.get("like_count"), c.get("comments_count"), c.get("view_count"),
              c.get("source_followers"), c.get("caption") or "", now, row["id"]))
        cand_id = row["id"]
    else:
        cur.execute("""
            INSERT INTO reel_candidates
                (niche_id, source_id, source_handle, shortcode, permalink, caption, posted_at,
                 like_count, comments_count, view_count, source_followers, duration_s, media_type,
                 status, discovered_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DISCOVERED', ?, ?)
        """, (c["niche_id"], c.get("source_id"), c.get("source_handle"), c["shortcode"], c["permalink"],
              c.get("caption", ""), c.get("posted_at"), c.get("like_count"), c.get("comments_count"),
              c.get("view_count"), c.get("source_followers"), c.get("duration_s"), c.get("media_type"),
              now, now))
        cand_id = cur.lastrowid
    conn.commit()
    conn.close()
    return cand_id


def get_candidate(candidate_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM reel_candidates WHERE id = ?", (candidate_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_candidates(niche_id: str, statuses: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_connection()
    q = "SELECT * FROM reel_candidates WHERE niche_id = ?"
    params: List[Any] = [niche_id]
    if statuses:
        q += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    q += " ORDER BY pinned DESC, final_score DESC, discovered_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_candidate(candidate_id: int, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    updates = dict(updates)
    updates["updated_at"] = to_iso(utcnow())
    cols = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection()
    conn.execute(f"UPDATE reel_candidates SET {cols} WHERE id = ?", (*updates.values(), candidate_id))
    conn.commit()
    conn.close()


def expire_stale_candidates(max_age_hours: int = CANDIDATE_MAX_AGE_HOURS) -> int:
    """Expire unposted candidates whose source post is older than max_age_hours (or discovered long ago
    when the source timestamp is unknown). Evergreen fallback still considers SCORED items up to 7 days."""
    cutoff = to_iso(utcnow() - timedelta(days=7))
    conn = get_connection()
    cur = conn.execute("""
        UPDATE reel_candidates SET status = 'EXPIRED', updated_at = ?
         WHERE status IN ('DISCOVERED', 'SCORED')
           AND COALESCE(posted_at, discovered_at) < ?
    """, (to_iso(utcnow()), cutoff))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def sources_used_today(niche_id: str, day_start_utc: datetime) -> List[str]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT c.source_handle FROM slot_runs s
          JOIN reel_candidates c ON c.id = s.candidate_id
         WHERE s.niche_id = ? AND s.scheduled_for >= ?
           AND s.status NOT IN ('SKIPPED', 'FAILED')
    """, (niche_id, to_iso(day_start_utc))).fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]


def was_posted_recently(shortcode: str, days: int = 14) -> bool:
    cutoff = to_iso(utcnow() - timedelta(days=days))
    conn = get_connection()
    row = conn.execute("""
        SELECT 1 FROM reel_candidates
         WHERE shortcode = ? AND status = 'PUBLISHED' AND updated_at >= ? LIMIT 1
    """, (shortcode, cutoff)).fetchone()
    conn.close()
    return bool(row)


# ---------------------------------------------------------------------------
# Niche schedules
# ---------------------------------------------------------------------------
def _default_schedule(niche_id: str) -> Dict[str, Any]:
    return {
        "niche_id": niche_id,
        "slot_times": list(DEFAULT_SLOT_TIMES),
        "timezone": DEFAULT_TIMEZONE,
        "jitter_minutes": 8,
        "fanout_mode": "balanced",
        "approval_mode": "telegram_timeout",
        "approval_timeout_minutes": 20,
        "min_score": 35.0,
        "evergreen_fallback": True,
        "source_diversity": True,
        "enabled": True,
    }


def _row_to_schedule(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["slot_times"] = json.loads(d.get("slot_times") or "[]")
    except Exception:
        d["slot_times"] = list(DEFAULT_SLOT_TIMES)
    for b in ("evergreen_fallback", "source_diversity", "enabled"):
        d[b] = bool(d.get(b))
    return d


def get_niche_schedule(niche_id: str) -> Dict[str, Any]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM niche_schedules WHERE niche_id = ?", (niche_id,)).fetchone()
    conn.close()
    return _row_to_schedule(row) if row else _default_schedule(niche_id)


def validate_slot_times(slot_times: List[str]) -> List[str]:
    clean = []
    for t in slot_times:
        t = str(t).strip()
        hh, mm = t.split(":")
        h, m = int(hh), int(mm)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError(f"Invalid slot time: {t}")
        clean.append(f"{h:02d}:{m:02d}")
    clean = sorted(set(clean))
    if len(clean) > MAX_POSTS_PER_ACCOUNT_PER_DAY:
        raise ValueError(f"At most {MAX_POSTS_PER_ACCOUNT_PER_DAY} slots per day are allowed.")
    # Enforce minimum spacing between consecutive slots
    mins = [int(x[:2]) * 60 + int(x[3:]) for x in clean]
    for a, b in zip(mins, mins[1:]):
        if (b - a) < MIN_GAP_BETWEEN_POSTS_HOURS * 60:
            raise ValueError(f"Slots must be at least {MIN_GAP_BETWEEN_POSTS_HOURS}h apart.")
    return clean


def save_niche_schedule(niche_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    merged = get_niche_schedule(niche_id)
    merged.update({k: v for k, v in cfg.items() if v is not None and k != "niche_id"})
    merged["slot_times"] = validate_slot_times(merged["slot_times"])
    conn = get_connection()
    conn.execute("""
        INSERT INTO niche_schedules
            (niche_id, slot_times, timezone, jitter_minutes, fanout_mode, approval_mode,
             approval_timeout_minutes, min_score, evergreen_fallback, source_diversity, enabled, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(niche_id) DO UPDATE SET
            slot_times = excluded.slot_times, timezone = excluded.timezone,
            jitter_minutes = excluded.jitter_minutes, fanout_mode = excluded.fanout_mode,
            approval_mode = excluded.approval_mode, approval_timeout_minutes = excluded.approval_timeout_minutes,
            min_score = excluded.min_score, evergreen_fallback = excluded.evergreen_fallback,
            source_diversity = excluded.source_diversity, enabled = excluded.enabled,
            updated_at = excluded.updated_at
    """, (niche_id, json.dumps(merged["slot_times"]), merged["timezone"], int(merged["jitter_minutes"]),
          merged["fanout_mode"], merged["approval_mode"], int(merged["approval_timeout_minutes"]),
          float(merged["min_score"]), int(bool(merged["evergreen_fallback"])),
          int(bool(merged["source_diversity"])), int(bool(merged["enabled"])), to_iso(utcnow())))
    conn.commit()
    conn.close()
    return get_niche_schedule(niche_id)


# ---------------------------------------------------------------------------
# Slot runs
# ---------------------------------------------------------------------------
def create_slot_run(niche_id: str, slot_time: str, slot_date: str, scheduled_for: datetime,
                    dry_run: bool = True) -> Dict[str, Any]:
    """Idempotent: one slot run per (niche, date, slot_time)."""
    conn = get_connection()
    conn.execute("""
        INSERT OR IGNORE INTO slot_runs (niche_id, slot_time, slot_date, scheduled_for, status, dry_run, created_at)
        VALUES (?, ?, ?, ?, 'PLANNED', ?, ?)
    """, (niche_id, slot_time, slot_date, to_iso(scheduled_for), int(dry_run), to_iso(utcnow())))
    conn.commit()
    row = conn.execute("SELECT * FROM slot_runs WHERE niche_id = ? AND slot_date = ? AND slot_time = ?",
                       (niche_id, slot_date, slot_time)).fetchone()
    conn.close()
    return dict(row)


def get_slot_run(slot_run_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM slot_runs WHERE id = ?", (slot_run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_slot_run(slot_run_id: int, updates: Dict[str, Any]) -> None:
    if not updates:
        return
    updates = dict(updates)
    if isinstance(updates.get("prepared_payload"), (dict, list)):
        updates["prepared_payload"] = json.dumps(updates["prepared_payload"])
    cols = ", ".join(f"{k} = ?" for k in updates)
    conn = get_connection()
    conn.execute(f"UPDATE slot_runs SET {cols} WHERE id = ?", (*updates.values(), slot_run_id))
    conn.commit()
    conn.close()


def get_slot_runs(since: Optional[datetime] = None, until: Optional[datetime] = None,
                  niche_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    q = """SELECT s.*, c.source_handle, c.permalink, c.final_score, c.caption AS candidate_caption
             FROM slot_runs s LEFT JOIN reel_candidates c ON c.id = s.candidate_id WHERE 1=1"""
    params: List[Any] = []
    if since:
        q += " AND s.scheduled_for >= ?"
        params.append(to_iso(since))
    if until:
        q += " AND s.scheduled_for <= ?"
        params.append(to_iso(until))
    if niche_id:
        q += " AND s.niche_id = ?"
        params.append(niche_id)
    q += " ORDER BY s.scheduled_for ASC LIMIT ?"
    params.append(limit)
    conn = get_connection()
    rows = conn.execute(q, params).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("prepared_payload", None)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Per-account posting guards
# ---------------------------------------------------------------------------
def _parse_db_ts(v: Optional[str]) -> Optional[datetime]:
    return from_iso(v)


def count_account_posts_since(account_id: str, since: datetime) -> int:
    conn = get_connection()
    rows = conn.execute("""
        SELECT published_at FROM broadcast_logs
         WHERE account_id = ? AND status = 'PUBLISHED' AND published_at IS NOT NULL
    """, (account_id,)).fetchall()
    conn.close()
    n = 0
    for r in rows:
        ts = _parse_db_ts(r[0])
        if ts and ts >= since:
            n += 1
    return n


def last_post_time(account_id: str) -> Optional[datetime]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT published_at FROM broadcast_logs
         WHERE account_id = ? AND status = 'PUBLISHED' AND published_at IS NOT NULL
    """, (account_id,)).fetchall()
    conn.close()
    times = [t for t in (_parse_db_ts(r[0]) for r in rows) if t]
    return max(times) if times else None


def account_guard(account_id: str, now: Optional[datetime] = None) -> Optional[str]:
    """Returns a skip reason if the account must NOT post right now, else None."""
    now = now or utcnow()
    if count_account_posts_since(account_id, now - timedelta(hours=24)) >= MAX_POSTS_PER_ACCOUNT_PER_DAY:
        return f"daily cap reached ({MAX_POSTS_PER_ACCOUNT_PER_DAY}/24h)"
    last = last_post_time(account_id)
    if last and (now - last) < timedelta(hours=MIN_GAP_BETWEEN_POSTS_HOURS):
        return f"last post {int((now - last).total_seconds() // 60)} min ago (< {MIN_GAP_BETWEEN_POSTS_HOURS}h gap)"
    return None
