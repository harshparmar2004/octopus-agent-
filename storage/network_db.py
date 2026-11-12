"""
Network-level tables for the multi-niche engine:
- content_ledger    : every harvested clip (dedup + exclusive one-reel-one-account lock)
- rights_status     : credit / permission state per source clip
- blocked_creators  : creators who asked us to stop / issued takedowns
- account_profile   : per-account sub-niche, cadence and strike tracking
- post_insights     : Graph API insights snapshots (1h / 24h / 72h)
"""
import sqlite3
from typing import Any, Dict, List, Optional

from storage.db import get_connection

# The six core niches of the network: (id, name, description, color, icon, hashtags, cta, template_id)
CORE_NICHES = [
    ("ai_content", "AI Content & Showcase", "AI-generated videos, AI art and tool demos", "#7C5CFF", "🤖",
     "#ai #aiart #aivideo #generativeai", "Follow @{handle} for daily AI magic", "ai_showcase"),
    ("memes", "Memes", "Relatable memes with original captions", "#111111", "😂",
     "#memes #funny #relatable #memesdaily", "Follow @{handle} for daily memes", "meme_native"),
    ("concerts", "Concerts & Live Music", "Live concert moments, tours and festivals", "#FFD23F", "🎤",
     "#concert #livemusic #tour #concertvibes", "Follow @{handle} for the best live moments", "concert_tag"),
    ("girls_dance", "Girls' Dance & Parties", "Permissioned dance and girls'-night content", "#FF4FA3", "💃",
     "#dance #dancereels #girlsnightout #partyvibes", "Follow @{handle} for daily vibes", "girls_raw"),
    ("clubbing", "Clubbing Parties", "Club nights, DJs and nightlife moments", "#FF007F", "🪩",
     "#clubbing #nightlife #clublife #djset", "Follow @{handle} for weekend club drops", "clubbing_branded"),
    ("ai_tech", "Informative AI & Tech", "AI and tech news and explainers", "#DDF51A", "💡",
     "#ai #tech #technews #artificialintelligence", "Follow @{handle} for daily AI & tech breakdowns", "informative_cult"),
]

# Default cadence per niche: (daily_cap, min_gap_minutes)
NICHE_CADENCE = {
    "ai_content": (3, 180),
    "memes": (5, 120),
    "concerts": (2, 300),
    "girls_dance": (2, 300),
    "clubbing": (3, 180),
    "ai_tech": (2, 300),
}
DEFAULT_CADENCE = (2, 240)
STRIKE_PAUSE_THRESHOLD = 2


def init_network_tables():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS content_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_key TEXT UNIQUE NOT NULL,      -- shortcode or canonical URL
            source_url TEXT,
            source_creator TEXT,
            niche_id TEXT,
            fingerprint TEXT,                     -- perceptual dHash of sampled frames (dedup only)
            score REAL DEFAULT 0,
            reel_id TEXT,
            assigned_account_id TEXT,             -- exclusive lock: one clip -> one account
            status TEXT DEFAULT 'NEW',            -- NEW, ASSIGNED, PUBLISHED, REJECTED, BLOCKED, TAKEN_DOWN
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            assigned_at TIMESTAMP
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_account ON content_ledger(assigned_account_id, assigned_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ledger_niche ON content_ledger(niche_id, status)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS rights_status (
            source_key TEXT PRIMARY KEY,
            creator_handle TEXT,
            niche_id TEXT,
            status TEXT DEFAULT 'credited_ok',    -- credited_ok, permission_required, permission_requested,
                                                  -- permission_granted, denied, blocked
            permission_requested_at TIMESTAMP,
            permission_granted_at TIMESTAMP,
            evidence TEXT,                        -- e.g. screenshot path / DM link of the creator's OK
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS blocked_creators (
            creator_handle TEXT PRIMARY KEY,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS account_profile (
            account_id TEXT PRIMARY KEY,
            sub_niche TEXT,                       -- comma-separated keywords, e.g. 'techno,ibiza,afterhours'
            daily_cap INTEGER,
            min_gap_minutes INTEGER,
            strike_count INTEGER DEFAULT 0,
            paused INTEGER DEFAULT 0,
            pause_reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS post_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id TEXT,
            reel_id TEXT,
            media_id TEXT,
            checkpoint TEXT,                      -- '1h', '24h', '72h'
            plays INTEGER, reach INTEGER, likes INTEGER, comments INTEGER,
            saves INTEGER, shares INTEGER,
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(media_id, checkpoint)
        )
    """)
    for n in CORE_NICHES:
        c.execute("""
            INSERT OR IGNORE INTO niches (id, name, description, brand_color, avatar_icon, default_hashtags, cta_text, template_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, n)
        c.execute("UPDATE niches SET template_id = ? WHERE id = ?", (n[7], n[0]))
    conn.commit()
    conn.close()


def _row(r) -> Optional[Dict[str, Any]]:
    return dict(r) if r else None


# ---------------------------------------------------------------- ledger
def ledger_get(source_key: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    r = conn.execute("SELECT * FROM content_ledger WHERE source_key = ?", (source_key,)).fetchone()
    conn.close()
    return _row(r)


def ledger_register(source_key: str, source_url: str = "", source_creator: str = "", niche_id: str = "",
                    fingerprint: str = "", score: float = 0.0, reel_id: Optional[str] = None) -> bool:
    """Inserts a clip into the ledger. Returns False if the source_key already exists."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO content_ledger (source_key, source_url, source_creator, niche_id, fingerprint, score, reel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (source_key, source_url, (source_creator or "").lstrip("@").lower(), niche_id, fingerprint, score, reel_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def ledger_fingerprints(niche_id: Optional[str] = None, limit: int = 5000) -> List[Dict[str, Any]]:
    conn = get_connection()
    q = "SELECT source_key, fingerprint, assigned_account_id, status FROM content_ledger WHERE fingerprint IS NOT NULL AND fingerprint != ''"
    args: list = []
    if niche_id:
        q += " AND niche_id = ?"
        args.append(niche_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in conn.execute(q, args).fetchall()]
    conn.close()
    return rows


def ledger_assign(source_key: str, account_id: str, reel_id: Optional[str] = None) -> bool:
    """Atomically locks a clip to one account. Returns False if it is already assigned."""
    conn = get_connection()
    cur = conn.execute("""
        UPDATE content_ledger
        SET assigned_account_id = ?, reel_id = COALESCE(?, reel_id), status = 'ASSIGNED', assigned_at = datetime('now')
        WHERE source_key = ? AND assigned_account_id IS NULL AND status IN ('NEW')
    """, (account_id, reel_id, source_key))
    conn.commit()
    ok = cur.rowcount == 1
    conn.close()
    return ok


def ledger_set_status(source_key: str, status: str):
    conn = get_connection()
    conn.execute("UPDATE content_ledger SET status = ? WHERE source_key = ?", (status, source_key))
    conn.commit()
    conn.close()


def account_assignments_since(account_id: str, hours: float) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM content_ledger
        WHERE assigned_account_id = ? AND assigned_at >= datetime('now', ?)
        ORDER BY assigned_at DESC
    """, (account_id, f"-{int(hours * 60)} minutes")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- rights
def rights_get(source_key: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    r = conn.execute("SELECT * FROM rights_status WHERE source_key = ?", (source_key,)).fetchone()
    conn.close()
    return _row(r)


def rights_upsert(source_key: str, **fields):
    allowed = {"creator_handle", "niche_id", "status", "permission_requested_at",
               "permission_granted_at", "evidence", "notes"}
    data = {k: v for k, v in fields.items() if k in allowed}
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO rights_status (source_key) VALUES (?)", (source_key,))
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        data["source_key"] = source_key
        conn.execute(f"UPDATE rights_status SET {sets}, updated_at = datetime('now') WHERE source_key = :source_key", data)
    conn.commit()
    conn.close()


def rights_list(status: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    if status:
        rows = conn.execute("SELECT * FROM rights_status WHERE status = ? ORDER BY updated_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM rights_status ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def block_creator(handle: str, reason: str = ""):
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO blocked_creators (creator_handle, reason) VALUES (?, ?)",
                 ((handle or "").lstrip("@").lower(), reason))
    conn.commit()
    conn.close()


def is_creator_blocked(handle: str) -> bool:
    conn = get_connection()
    r = conn.execute("SELECT 1 FROM blocked_creators WHERE creator_handle = ?",
                     ((handle or "").lstrip("@").lower(),)).fetchone()
    conn.close()
    return r is not None


# ---------------------------------------------------------------- accounts
def get_account_profile(account_id: str, niche_id: str = "") -> Dict[str, Any]:
    conn = get_connection()
    r = conn.execute("SELECT * FROM account_profile WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    cap, gap = NICHE_CADENCE.get(niche_id, DEFAULT_CADENCE)
    prof = dict(r) if r else {"account_id": account_id, "sub_niche": "", "strike_count": 0, "paused": 0, "pause_reason": None}
    prof["daily_cap"] = prof.get("daily_cap") or cap
    prof["min_gap_minutes"] = prof.get("min_gap_minutes") or gap
    return prof


def set_account_profile(account_id: str, **fields):
    allowed = {"sub_niche", "daily_cap", "min_gap_minutes", "strike_count", "paused", "pause_reason"}
    data = {k: v for k, v in fields.items() if k in allowed}
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO account_profile (account_id) VALUES (?)", (account_id,))
    if data:
        sets = ", ".join(f"{k} = :{k}" for k in data)
        data["account_id"] = account_id
        conn.execute(f"UPDATE account_profile SET {sets}, updated_at = datetime('now') WHERE account_id = :account_id", data)
    conn.commit()
    conn.close()


def record_strike(account_id: str, reason: str) -> Dict[str, Any]:
    """Adds a copyright/privacy strike; auto-pauses the account at the threshold."""
    prof = get_account_profile(account_id)
    strikes = int(prof.get("strike_count") or 0) + 1
    paused = 1 if strikes >= STRIKE_PAUSE_THRESHOLD else int(prof.get("paused") or 0)
    set_account_profile(account_id, strike_count=strikes, paused=paused,
                        pause_reason=(f"Auto-paused after {strikes} strikes: {reason}" if paused else prof.get("pause_reason")))
    return get_account_profile(account_id)


# ---------------------------------------------------------------- insights
def save_insight(account_id: str, reel_id: str, media_id: str, checkpoint: str, metrics: Dict[str, int]):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO post_insights (account_id, reel_id, media_id, checkpoint, plays, reach, likes, comments, saves, shares)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (account_id, reel_id, media_id, checkpoint,
          metrics.get("plays", 0), metrics.get("reach", 0), metrics.get("likes", 0),
          metrics.get("comments", 0), metrics.get("saves", 0), metrics.get("shares", 0)))
    conn.commit()
    conn.close()


def insights_for_creator(creator_handle: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT p.* FROM post_insights p
        JOIN content_ledger l ON l.reel_id = p.reel_id
        WHERE l.source_creator = ? AND p.checkpoint = '72h'
    """, ((creator_handle or "").lstrip("@").lower(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
