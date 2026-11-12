import sqlite3
import json
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from config import settings

DB_PATH = settings.STORAGE_DIR / "octopus_agent.db"

def get_connection():
    settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_octopus_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Accounts Table (Supports 20-30+ Accounts)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,               -- e.g. 'quantum', 'ai', 'robotics_01'
            handle TEXT NOT NULL,              -- e.g. '@octopus.quantum'
            display_name TEXT NOT NULL,        -- e.g. 'OctopusQuantum'
            niche TEXT NOT NULL,               -- e.g. 'Quantum Computing & Deep Tech'
            ig_user_id TEXT,                   -- Meta Graph API Instagram Business ID
            access_token TEXT,                 -- Page/User Access Token
            avatar_initials TEXT DEFAULT 'OC',
            brand_color TEXT DEFAULT '#00b4d8',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Master Reels Library Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reels_tracker (
            id TEXT PRIMARY KEY,
            source_url TEXT NOT NULL,
            original_title TEXT,
            hook_text TEXT,
            caption TEXT,
            raw_video_path TEXT,
            rendered_video_path TEXT,
            rendered_filename TEXT,
            status TEXT DEFAULT 'HARVESTED',   -- HARVESTED, ENRICHED, READY, BROADCASTING, BROADCASTED, FAILED
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Safe column additions if table was created previously without them
    for col in ["rendered_video_path", "rendered_filename"]:
        try:
            cursor.execute(f"ALTER TABLE reels_tracker ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    # 3. Account-Specific Broadcast Logs (Which reel was posted to which account)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reel_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            rendered_video_path TEXT,
            rendered_filename TEXT,
            status TEXT DEFAULT 'PENDING',     -- PENDING, READY, PUBLISHED, FAILED
            instagram_media_id TEXT,
            instagram_post_url TEXT,
            error_message TEXT,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (reel_id) REFERENCES reels_tracker(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)
    
    # 4. Monitored Sources Watchlist Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitored_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,       -- 'instagram_handle', 'reddit_sub', 'direct_url', 'youtube'
            source_value TEXT NOT NULL,      -- e.g. 'uncover.quantum' or 'physicsgifs'
            category TEXT NOT NULL,          -- category/niche (quantum, ai, robotics, etc.)
            target_account_id TEXT,          -- Destination account ID (e.g. 'quantum')
            auto_publish INTEGER DEFAULT 1,  -- 1 = auto-post immediately, 0 = queue for review
            last_scraped_post_id TEXT,       -- Shortcode/ID of the last processed reel
            is_active INTEGER DEFAULT 1,
            last_checked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 0. Niches / Cluster Table (Full independence to create and manage custom niches)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS niches (
            id TEXT PRIMARY KEY,               -- e.g. 'information', 'quantum', 'ai'
            name TEXT NOT NULL,                -- e.g. 'Information & Infotainment'
            description TEXT,                  -- e.g. 'Viral educational facts, curious knowledge'
            brand_color TEXT DEFAULT '#ea580c',
            avatar_icon TEXT DEFAULT '💡',
            default_hashtags TEXT,
            cta_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Safe column additions if table was created previously without them
    for col, col_type in [
        ("target_account_id", "TEXT"),
        ("auto_publish", "INTEGER DEFAULT 1"),
        ("last_scraped_post_id", "TEXT"),
        ("niche_id", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE monitored_sources ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE accounts ADD COLUMN niche_id TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE accounts ADD COLUMN profile_pic_url TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE niches ADD COLUMN automation_config TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE niches ADD COLUMN template_id TEXT DEFAULT 'informative_cult'")
    except sqlite3.OperationalError:
        pass


    # Seed default initial accounts if empty
    cursor.execute("SELECT COUNT(*) FROM accounts")
    if cursor.fetchone()[0] == 0:
        default_accounts = [
            ("quantum", "@octopus.quantum", "OctopusQuantum", "Quantum Physics & Computing", "", "", "OQ", "#00b4d8", 1),
            ("robotics", "@octopus.robotics", "OctopusRobotics", "Humanoid Robotics & Embodied AI", "", "", "OR", "#e63946", 1),
            ("ai", "@octopus.ai", "OctopusAI", "Generative AI & Machine Learning", "", "", "OA", "#7209b7", 1),
            ("space", "@octopus.space", "OctopusSpace", "Astrophysics & Space Exploration", "", "", "OS", "#f72585", 1),
            ("biotech", "@octopus.biotech", "OctopusBioTech", "Synthetic Biology & Longevity", "", "", "OB", "#4cc9f0", 1),
        ]
        cursor.executemany("""
            INSERT INTO accounts (id, handle, display_name, niche, ig_user_id, access_token, avatar_initials, brand_color, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, default_accounts)

    # Seed default niches if empty
    cursor.execute("SELECT COUNT(*) FROM niches")
    if cursor.fetchone()[0] == 0:
        default_niches = [
            ("information", "Information & Infotainment", "Viral educational facts, curious knowledge & deep phenomena", "#ea580c", "💡", "#information #facts #curiosity #knowledge #didyouknow", "Follow @{handle} for daily mind-blowing information!"),
            ("quantum", "Quantum Physics & Computing", "Subatomic physics, quantum computing & superposition", "#00b4d8", "⚛️", "#quantum #physics #science #tech", "Follow @{handle} for cutting-edge quantum discoveries!"),
            ("ai", "Generative AI & Machine Learning", "Artificial intelligence, LLMs, neural networks & automation", "#7209b7", "🤖", "#ai #machinelearning #artificialintelligence #tech", "Follow @{handle} for daily AI breakthroughs!"),
            ("robotics", "Humanoid Robotics & Embodied AI", "Bipedal robots, automation, actuators & mechatronics", "#e63946", "🦾", "#robotics #engineering #humanoid #future", "Follow @{handle} for next-gen robotics!"),
            ("space", "Astrophysics & Space Exploration", "NASA, SpaceX, cosmology, galaxies & deep space missions", "#f72585", "🚀", "#space #astrophysics #cosmos #universe", "Follow @{handle} for daily cosmos exploration!"),
            ("biotech", "Synthetic Biology & Longevity", "Gene editing, CRISPR, longevity medicine & cellular biology", "#4cc9f0", "🧬", "#biotech #crispr #longevity #biology", "Follow @{handle} for future biology insights!"),
        ]
        cursor.executemany("""
            INSERT INTO niches (id, name, description, brand_color, avatar_icon, default_hashtags, cta_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, default_niches)

    # Seed initial accounts if empty (including 10 Information pages + 5 Tech pages)
    cursor.execute("SELECT COUNT(*) FROM accounts")
    if cursor.fetchone()[0] <= 5:
        # Make sure the 10 Information pages are present
        info_accounts = [
            ("info_01", "@info.daily", "InfoDaily", "Information", "information", "", "", "ID", "#ea580c", 1),
            ("info_02", "@curious.minds", "CuriousMinds", "Information", "information", "", "", "CM", "#f97316", 1),
            ("info_03", "@daily.knowledge", "DailyKnowledge", "Information", "information", "", "", "DK", "#fb923c", 1),
            ("info_04", "@deep.facts", "DeepFacts", "Information", "information", "", "", "DF", "#fdba74", 1),
            ("info_05", "@mind.uncovered", "MindUncovered", "Information", "information", "", "", "MU", "#c2410c", 1),
            ("info_06", "@quick.intel", "QuickIntel", "Information", "information", "", "", "QI", "#9a3412", 1),
            ("info_07", "@world.infotainment", "WorldInfotainment", "Information", "information", "", "", "WI", "#ea580c", 1),
            ("info_08", "@insight.pulse", "InsightPulse", "Information", "information", "", "", "IP", "#f97316", 1),
            ("info_09", "@curiosity.stream", "CuriosityStream", "Information", "information", "", "", "CS", "#fb923c", 1),
            ("info_10", "@facts.nexus", "FactsNexus", "Information", "information", "", "", "FN", "#c2410c", 1),
        ]
        for acc in info_accounts:
            cursor.execute("""
                INSERT OR IGNORE INTO accounts (id, handle, display_name, niche, niche_id, ig_user_id, access_token, avatar_initials, brand_color, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, acc)

    # Ensure existing accounts have niche_id populated
    cursor.execute("UPDATE accounts SET niche_id = 'quantum' WHERE id = 'quantum' OR niche LIKE '%quantum%'")
    cursor.execute("UPDATE accounts SET niche_id = 'robotics' WHERE id = 'robotics' OR niche LIKE '%robotics%'")
    cursor.execute("UPDATE accounts SET niche_id = 'ai' WHERE id = 'ai' OR niche LIKE '%ai%' OR niche LIKE '%machine%'")
    cursor.execute("UPDATE accounts SET niche_id = 'space' WHERE id = 'space' OR niche LIKE '%space%'")
    cursor.execute("UPDATE accounts SET niche_id = 'biotech' WHERE id = 'biotech' OR niche LIKE '%biotech%'")
    cursor.execute("UPDATE accounts SET niche_id = 'information' WHERE id LIKE 'info_%'")
    cursor.execute("UPDATE accounts SET niche_id = 'girls_dance', niche = 'Girls'' Dance & Parties' WHERE id = 'cute_aarohi_007' OR handle LIKE '%cute.aarohi%'")

    # Seed extended niches (Parties, Organizing, Fashion) with their templates
    extended_niches = [
        ("parties", "Parties, EDM & Nightlife", "EDM festivals, DJ drops, club culture & event recaps", "#FF007F", "🎉", "#nightlife #edmlifestyle #partyvibes #techno #festivalvibes #clubbing", "Follow @{handle} for weekend party drops!", "nightlife_party"),
        ("organizing", "Home Organizing & ASMR", "Decluttering, Sunday resets, pantry setups & clean home hacks", "#84A98C", "🧺", "#organizationhacks #sundayreset #cleantok #minimalisthome", "Follow @{handle} for weekly reset inspiration!", "organizing_home"),
        ("fashion", "Fashion & Beauty Lifestyle", "Capsule wardrobes, clean girl aesthetic outfits & chic lookbooks", "#D4AF37", "✨", "#outfitinspo #capsulewardrobe #cleangirlstyle #aestheticfits", "Follow @{handle} for daily chic rotation inspo!", "fashion_editorial"),
    ]
    for n in extended_niches:
        cursor.execute("""
            INSERT OR IGNORE INTO niches (id, name, description, brand_color, avatar_icon, default_hashtags, cta_text, template_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, n)
        cursor.execute("UPDATE niches SET template_id = ? WHERE id = ?", (n[7], n[0]))

    # Seed accounts for Parties, Organizing, and Fashion pods
    party_accounts = [
        ("party_01", "@miami.nights", "MiamiNights", "Parties & Nightlife", "parties", "", "", "MN", "#FF007F", 1),
        ("party_02", "@edm.pulse", "EDMPulse", "Parties & Nightlife", "parties", "", "", "EP", "#00F0FF", 1),
        ("party_03", "@afterhours.club", "AfterhoursClub", "Parties & Nightlife", "parties", "", "", "AC", "#f43f5e", 1),
        ("party_04", "@festival.vibes", "FestivalVibes", "Parties & Nightlife", "parties", "", "", "FV", "#a855f7", 1),
        ("party_05", "@club.tulum", "ClubTulum", "Parties & Nightlife", "parties", "", "", "CT", "#ec4899", 1),
        ("party_06", "@neon.energy", "NeonEnergy", "Parties & Nightlife", "parties", "", "", "NE", "#3b82f6", 1),
        ("party_07", "@techno.pulse", "TechnoPulse", "Parties & Nightlife", "parties", "", "", "TP", "#6366f1", 1),
        ("party_08", "@bass.heavy", "BassHeavy", "Parties & Nightlife", "parties", "", "", "BH", "#8b5cf6", 1),
        ("party_09", "@rave.society", "RaveSociety", "Parties & Nightlife", "parties", "", "", "RS", "#d946ef", 1),
        ("party_10", "@drop.vault", "DropVault", "Parties & Nightlife", "parties", "", "", "DV", "#FF007F", 1),
    ]
    for acc in party_accounts:
        cursor.execute("""
            INSERT OR IGNORE INTO accounts (id, handle, display_name, niche, niche_id, ig_user_id, access_token, avatar_initials, brand_color, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, acc)

    organizing_accounts = [
        ("org_01", "@organize.daily", "OrganizeDaily", "Home Organizing & ASMR", "organizing", "", "", "OD", "#84A98C", 1),
        ("org_02", "@reset.routine", "ResetRoutine", "Home Organizing & ASMR", "organizing", "", "", "RR", "#52796F", 1),
        ("org_03", "@clean.spaces", "CleanSpaces", "Home Organizing & ASMR", "organizing", "", "", "CS", "#354F52", 1),
        ("org_04", "@pantry.perfection", "PantryPerfection", "Home Organizing & ASMR", "organizing", "", "", "PP", "#2F3E46", 1),
        ("org_05", "@neat.living", "NeatLiving", "Home Organizing & ASMR", "organizing", "", "", "NL", "#84A98C", 1),
        ("org_06", "@declutter.flow", "DeclutterFlow", "Home Organizing & ASMR", "organizing", "", "", "DF", "#52796F", 1),
        ("org_07", "@asmr.organize", "ASMROrganize", "Home Organizing & ASMR", "organizing", "", "", "AO", "#C86237", 1),
        ("org_08", "@aesthetic.home", "AestheticHome", "Home Organizing & ASMR", "organizing", "", "", "AH", "#D5BDAF", 1),
        ("org_09", "@tidy.haven", "TidyHaven", "Home Organizing & ASMR", "organizing", "", "", "TH", "#84A98C", 1),
        ("org_10", "@order.simplified", "OrderSimplified", "Home Organizing & ASMR", "organizing", "", "", "OS", "#52796F", 1),
    ]
    for acc in organizing_accounts:
        cursor.execute("""
            INSERT OR IGNORE INTO accounts (id, handle, display_name, niche, niche_id, ig_user_id, access_token, avatar_initials, brand_color, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, acc)

    fashion_accounts = [
        ("fash_01", "@chic.rotation", "ChicRotation", "Fashion & Beauty Lifestyle", "fashion", "", "", "CR", "#D4AF37", 1),
        ("fash_02", "@minimal.fits", "MinimalFits", "Fashion & Beauty Lifestyle", "fashion", "", "", "MF", "#C5A059", 1),
        ("fash_03", "@style.notes", "StyleNotes", "Fashion & Beauty Lifestyle", "fashion", "", "", "SN", "#E5C158", 1),
        ("fash_04", "@aesthetic.wardrobe", "AestheticWardrobe", "Fashion & Beauty Lifestyle", "fashion", "", "", "AW", "#A38035", 1),
        ("fash_05", "@capsule.styling", "CapsuleStyling", "Fashion & Beauty Lifestyle", "fashion", "", "", "CS", "#D4AF37", 1),
        ("fash_06", "@quiet.luxury", "QuietLuxury", "Fashion & Beauty Lifestyle", "fashion", "", "", "QL", "#8C6D23", 1),
        ("fash_07", "@french.vibe", "FrenchVibe", "Fashion & Beauty Lifestyle", "fashion", "", "", "FV", "#D4AF37", 1),
        ("fash_08", "@daily.lookbook", "DailyLookbook", "Fashion & Beauty Lifestyle", "fashion", "", "", "DL", "#C5A059", 1),
        ("fash_09", "@couture.pulse", "CouturePulse", "Fashion & Beauty Lifestyle", "fashion", "", "", "CP", "#E5C158", 1),
        ("fash_10", "@clean.girl.fits", "CleanGirlFits", "Fashion & Beauty Lifestyle", "fashion", "", "", "CG", "#D4AF37", 1),
    ]
    for acc in fashion_accounts:
        cursor.execute("""
            INSERT OR IGNORE INTO accounts (id, handle, display_name, niche, niche_id, ig_user_id, access_token, avatar_initials, brand_color, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, acc)


    # Seed 7 benchmark sources for the Information Niche if missing
    info_sources = [
        ("instagram_handle", "dailyfacts", "information", "information", "info_01", 1),
        ("instagram_handle", "uncover.ai", "information", "information", "info_02", 1),
        ("instagram_handle", "interestingengineering", "information", "information", "info_03", 1),
        ("instagram_handle", "physicsfun", "information", "information", "info_04", 1),
        ("instagram_handle", "mindblowingfacts", "information", "information", "info_05", 1),
        ("instagram_handle", "science.daily", "information", "information", "info_06", 1),
        ("reddit_sub", "facts", "information", "information", "info_07", 1),
    ]
    for s in info_sources:
        cursor.execute("""
            INSERT OR IGNORE INTO monitored_sources (source_type, source_value, category, niche_id, target_account_id, auto_publish)
            VALUES (?, ?, ?, ?, ?, ?)
        """, s)

    # Ensure existing sources have niche_id populated
    cursor.execute("UPDATE monitored_sources SET niche_id = category WHERE niche_id IS NULL OR niche_id = ''")

    conn.commit()
    conn.close()

    # Peak-Time Scheduler tables (Candidate Pool, niche schedules, slot runs)
    from storage.scheduler_db import init_scheduler_tables
    init_scheduler_tables()

    # Network tables (content ledger, rights, account profiles, insights) + 6 core niches
    from storage.network_db import init_network_tables
    init_network_tables()

    # Seed 6 Core Network Niches' Accounts if missing or below target count
    conn = get_connection()
    c = conn.cursor()
    core_niche_seeds = [
        ("ai_tech", "ai_tech", "@aitech.daily", "AI Tech Daily", "Informative AI & Tech", "AT", "#DDF51A", 20),
        ("clubbing", "clubbing", "@clubbing.pulse", "Clubbing Nights", "Clubbing Parties", "CP", "#FF007F", 20),
        ("memes", "memes", "@daily.memes", "Daily Memes", "Memes", "DM", "#111111", 10),
        ("concerts", "concerts", "@concert.live", "Concert Moments", "Concerts & Live Music", "CL", "#FFD23F", 10),
        ("ai_content", "ai_content", "@ai.showcase", "AI Showcase", "AI Content & Showcase", "AS", "#7C5CFF", 15),
        ("girls_dance", "girls_dance", "@dance.vibes", "Dance Vibes", "Girls' Dance & Parties", "DV", "#FF4FA3", 15),
    ]
    for nid, prefix, h_prefix, d_prefix, n_name, initials, color, target_count in core_niche_seeds:
        c.execute("SELECT COUNT(*) FROM accounts WHERE niche_id = ?", (nid,))
        curr = c.fetchone()[0]
        if curr < target_count:
            for i in range(curr + 1, target_count + 1):
                acc_id = f"{prefix}_{i:02d}"
                handle = f"{h_prefix}{i:02d}"
                disp_name = f"{d_prefix} {i:02d}"
                c.execute("""
                    INSERT OR IGNORE INTO accounts (id, handle, display_name, niche, niche_id, ig_user_id, access_token, avatar_initials, brand_color, is_active)
                    VALUES (?, ?, ?, ?, ?, '', '', ?, ?, 1)
                """, (acc_id, handle, disp_name, n_name, nid, initials, color))
    conn.commit()
    conn.close()

# Accounts operations
def get_all_accounts(active_only: bool = True) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM accounts"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id"
    cursor.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_account_by_id(account_id: str) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def add_or_update_account(account_data: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    data = dict(account_data)
    if "niche_id" not in data or not data["niche_id"]:
        data["niche_id"] = data.get("niche", "information").lower().replace(" ", "_").split("_")[0]
    data.setdefault("ig_user_id", None)
    data.setdefault("access_token", None)
    data.setdefault("avatar_initials", "OC")
    data.setdefault("brand_color", "#ea580c")
    data.setdefault("profile_pic_url", None)
    data.setdefault("is_active", 1)
    cursor.execute("""
        INSERT INTO accounts (id, handle, display_name, niche, niche_id, ig_user_id, access_token, avatar_initials, brand_color, profile_pic_url, is_active)
        VALUES (:id, :handle, :display_name, :niche, :niche_id, :ig_user_id, :access_token, :avatar_initials, :brand_color, :profile_pic_url, :is_active)
        ON CONFLICT(id) DO UPDATE SET
            handle = excluded.handle,
            display_name = excluded.display_name,
            niche = excluded.niche,
            niche_id = excluded.niche_id,
            ig_user_id = COALESCE(excluded.ig_user_id, accounts.ig_user_id),
            access_token = COALESCE(excluded.access_token, accounts.access_token),
            avatar_initials = excluded.avatar_initials,
            brand_color = excluded.brand_color,
            profile_pic_url = COALESCE(excluded.profile_pic_url, accounts.profile_pic_url),
            is_active = excluded.is_active
    """, data)
    conn.commit()
    conn.close()

def delete_account(account_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    conn.commit()
    conn.close()

# Master Reel tracker operations
def insert_or_update_reel(reel_data: Dict[str, Any]):
    if not reel_data or "id" not in reel_data:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM reels_tracker WHERE id = ?", (reel_data["id"],))
    exists = cursor.fetchone() is not None

    if not exists:
        full_data = {
            "id": reel_data.get("id"),
            "source_url": reel_data.get("source_url", ""),
            "original_title": reel_data.get("original_title"),
            "hook_text": reel_data.get("hook_text"),
            "caption": reel_data.get("caption"),
            "raw_video_path": reel_data.get("raw_video_path"),
            "rendered_video_path": reel_data.get("rendered_video_path"),
            "rendered_filename": reel_data.get("rendered_filename"),
            "status": reel_data.get("status", "HARVESTED"),
            "error_message": reel_data.get("error_message")
        }
        cursor.execute("""
            INSERT INTO reels_tracker (
                id, source_url, original_title, hook_text, caption,
                raw_video_path, rendered_video_path, rendered_filename, status, error_message
            ) VALUES (
                :id, :source_url, :original_title, :hook_text, :caption,
                :raw_video_path, :rendered_video_path, :rendered_filename, :status, :error_message
            )
        """, full_data)
    else:
        # Dynamic partial update
        update_keys = [k for k in reel_data.keys() if k != "id" and k in [
            "source_url", "original_title", "hook_text", "caption",
            "raw_video_path", "rendered_video_path", "rendered_filename", "status", "error_message"
        ]]
        if update_keys:
            set_clause = ", ".join([f"{k} = :{k}" for k in update_keys])
            cursor.execute(f"UPDATE reels_tracker SET {set_clause} WHERE id = :id", reel_data)

    conn.commit()
    conn.close()

def get_all_reels(limit: int = 50) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reels_tracker ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_reel(reel_id: str) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reels_tracker WHERE id = ?", (reel_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# Aliases for backward compatibility
get_reel_by_id = get_reel
init_tracker_db = init_octopus_db

def is_source_already_scraped(url: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM reels_tracker WHERE source_url = ?", (url,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# Broadcast logs operations
def record_broadcast_log(log_data: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO broadcast_logs (
            reel_id, account_id, rendered_video_path, rendered_filename,
            status, instagram_media_id, instagram_post_url, error_message, published_at
        ) VALUES (
            :reel_id, :account_id, :rendered_video_path, :rendered_filename,
            :status, :instagram_media_id, :instagram_post_url, :error_message, :published_at
        )
    """, log_data)
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id

def update_broadcast_log(log_id: int, updates: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
    updates["log_id"] = log_id
    cursor.execute(f"UPDATE broadcast_logs SET {set_clause} WHERE id = :log_id", updates)
    conn.commit()
    conn.close()

def get_broadcast_logs_for_reel(reel_id: str) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, a.handle, a.display_name
        FROM broadcast_logs b
        JOIN accounts a ON b.account_id = a.id
        WHERE b.reel_id = ?
        ORDER BY b.id DESC
    """, (reel_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_recent_broadcast_activity(limit: int = 100) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, a.handle, a.display_name, a.avatar_initials, a.brand_color, a.profile_pic_url, a.niche, r.hook_text, r.original_title, r.source_url
        FROM broadcast_logs b
        JOIN accounts a ON b.account_id = a.id
        JOIN reels_tracker r ON b.reel_id = r.id
        ORDER BY b.created_at DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

# Sources operations
def get_monitored_sources() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM monitored_sources WHERE is_active = 1 ORDER BY category, id")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_active_sources_by_type(source_type: str = "instagram_handle") -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM monitored_sources 
        WHERE source_type = ? AND is_active = 1 
        ORDER BY id
    """, (source_type,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def add_monitored_source(*args, **kwargs):
    if len(args) == 1 and isinstance(args[0], dict):
        d = args[0]
        source_type = d.get("source_type", "instagram_handle")
        source_value = d.get("source_value", "")
        category = d.get("category", "general")
        target_account_id = d.get("target_account_id") or category
        auto_publish = d.get("auto_publish", 1)
        niche_id = d.get("niche_id") or category
    else:
        source_type = args[0] if len(args) > 0 else kwargs.get("source_type", "instagram_handle")
        source_value = args[1] if len(args) > 1 else kwargs.get("source_value", "")
        category = args[2] if len(args) > 2 else kwargs.get("category", "general")
        target_account_id = args[3] if len(args) > 3 else kwargs.get("target_account_id", category)
        auto_publish = args[4] if len(args) > 4 else kwargs.get("auto_publish", 1)
        niche_id = kwargs.get("niche_id") or category

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO monitored_sources (source_type, source_value, category, target_account_id, auto_publish, niche_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (source_type, source_value.strip().lstrip("@"), category, target_account_id or category, auto_publish, niche_id))
    conn.commit()
    conn.close()

def update_source_last_scraped(source_id: int, post_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE monitored_sources 
        SET last_scraped_post_id = ?, last_checked_at = ?
        WHERE id = ?
    """, (post_id, now_str, source_id))
    conn.commit()
    conn.close()

def delete_monitored_source(source_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM monitored_sources WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()

def get_network_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM accounts WHERE is_active = 1")
    active_accounts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM accounts")
    total_accounts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM reels_tracker")
    total_reels = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM broadcast_logs")
    total_broadcasts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM broadcast_logs WHERE status = 'PUBLISHED'")
    successful_broadcasts = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM monitored_sources WHERE is_active = 1")
    monitored_sources_count = cursor.fetchone()[0]
    conn.close()
    
    rate = round((successful_broadcasts / total_broadcasts * 100), 1) if total_broadcasts > 0 else 100.0
    return {
        "active_accounts": active_accounts,
        "total_accounts": total_accounts,
        "total_reels": total_reels,
        "total_broadcasts": total_broadcasts,
        "successful_broadcasts": successful_broadcasts,
        "success_rate": rate,
        "monitored_sources": monitored_sources_count
    }

# ==================== NICHE CLUSTER & POD OPERATIONS ====================

def create_or_update_niche(niche_data: Dict[str, Any]):
    conn = get_connection()
    cursor = conn.cursor()
    payload = {
        "id": niche_data["id"],
        "name": niche_data.get("name", niche_data["id"].capitalize()),
        "description": niche_data.get("description", ""),
        "brand_color": niche_data.get("brand_color", "#ea580c"),
        "avatar_icon": niche_data.get("avatar_icon", "📁"),
        "default_hashtags": niche_data.get("default_hashtags", ""),
        "cta_text": niche_data.get("cta_text", "")
    }
    cursor.execute("""
        INSERT INTO niches (id, name, description, brand_color, avatar_icon, default_hashtags, cta_text)
        VALUES (:id, :name, :description, :brand_color, :avatar_icon, :default_hashtags, :cta_text)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            brand_color = excluded.brand_color,
            avatar_icon = excluded.avatar_icon,
            default_hashtags = excluded.default_hashtags,
            cta_text = excluded.cta_text
    """, payload)
    conn.commit()
    conn.close()

def get_all_niches() -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*,
               (SELECT COUNT(*) FROM accounts a WHERE a.niche_id = n.id AND a.is_active = 1) AS active_accounts,
               (SELECT COUNT(*) FROM accounts a WHERE a.niche_id = n.id) AS total_accounts,
               (SELECT COUNT(*) FROM monitored_sources s WHERE s.niche_id = n.id AND s.is_active = 1) AS total_sources
        FROM niches n
        ORDER BY (CASE WHEN n.id = 'information' THEN 0 ELSE 1 END), n.name
    """)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_niche_by_id(niche_id: str) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM niches WHERE id = ?", (niche_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_niche(niche_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM niches WHERE id = ?", (niche_id,))
    cursor.execute("UPDATE accounts SET niche_id = 'information' WHERE niche_id = ?", (niche_id,))
    cursor.execute("UPDATE monitored_sources SET niche_id = 'information' WHERE niche_id = ?", (niche_id,))
    conn.commit()
    conn.close()

def get_niche_cluster(niche_id: str, allow_placeholders: bool = False) -> Dict[str, Any]:
    niche = get_niche_by_id(niche_id)
    if not niche:
        # Fallback to create it if requested
        niche = {
            "id": niche_id,
            "name": niche_id.capitalize(),
            "description": f"Automated cluster for {niche_id}",
            "brand_color": "#ea580c",
            "avatar_icon": "💡",
            "default_hashtags": f"#{niche_id}",
            "cta_text": f"Follow for more {niche_id} content!"
        }
    
    conn = get_connection()
    cursor = conn.cursor()

    NICHE_ALIASES = {
        "ai_tech": ["ai_tech", "information", "ai", "tech"],
        "information": ["information", "ai_tech", "ai", "tech"],
        "clubbing": ["clubbing", "parties", "party"],
        "parties": ["parties", "clubbing", "party"],
        "girls_dance": ["girls_dance", "girls_party", "girls", "dance"],
        "girls_party": ["girls_party", "girls_dance", "girls", "dance"],
        "ai_content": ["ai_content", "ai"],
        "memes": ["memes", "meme"],
        "concerts": ["concerts", "concert"],
    }
    aliases = NICHE_ALIASES.get(niche_id, [niche_id])
    placeholders = ",".join(["?"] * len(aliases))
    
    # 1. Connected destination accounts for this niche
    cursor.execute(f"""
        SELECT * FROM accounts 
        WHERE (niche_id IN ({placeholders}) OR niche LIKE ?) AND is_active = 1
        ORDER BY id
    """, (*aliases, f"%{niche_id}%"))
    all_accounts = [dict(r) for r in cursor.fetchall()]

    # Filter strictly to accounts configured with real Meta Graph credentials (access_token + ig_user_id)
    auth_accounts = [
        acc for acc in all_accounts
        if acc.get("access_token") and len(str(acc["access_token"]).strip()) > 20 and acc.get("ig_user_id") and len(str(acc["ig_user_id"]).strip()) > 3
    ]
    accounts = all_accounts if allow_placeholders else auth_accounts
    
    # 2. Bound competitor source handles for this niche
    cursor.execute(f"""
        SELECT * FROM monitored_sources 
        WHERE (niche_id IN ({placeholders}) OR category IN ({placeholders})) AND is_active = 1
        ORDER BY id
    """, (*aliases, *aliases))
    sources = [dict(r) for r in cursor.fetchall()]
    
    # 3. Recent broadcasts for this niche
    cursor.execute(f"""
        SELECT b.*, a.handle, a.display_name, a.avatar_initials, a.brand_color, a.profile_pic_url, a.niche, r.hook_text, r.original_title, r.source_url
        FROM broadcast_logs b
        JOIN accounts a ON b.account_id = a.id
        JOIN reels_tracker r ON b.reel_id = r.id
        WHERE a.niche_id IN ({placeholders}) OR a.niche LIKE ?
        ORDER BY b.created_at DESC
        LIMIT 15
    """, (*aliases, f"%{niche_id}%"))
    recent_broadcasts = [dict(r) for r in cursor.fetchall()]
    
    conn.close()

    # Parse or initialize automation_config
    raw_cfg = niche.get("automation_config")
    cfg = None
    if raw_cfg:
        try:
            cfg = json.loads(raw_cfg) if isinstance(raw_cfg, str) else raw_cfg
        except Exception:
            cfg = None
    if not cfg:
        cfg = {
            "source_mode": "all_sources",
            "selected_source": sources[0]["source_value"] if sources else "",
            "direct_url": "",
            "ai_caption_mode": "smart_adapt",
            "cta_template": f"Follow @{{destination_account}} for more daily {niche.get('name', niche_id)} breakdowns!",
            "hook_style": "curiosity",
            "custom_headline": "",
            "auto_hashtags": True,
            "custom_hashtags": niche.get("default_hashtags", f"#{niche_id} #viral #curiosity"),
            "include_attribution": True,
            "verified_badge": True,
            "video_ratio": "auto",
            "branding_template": "dynamic"
        }
    niche["automation_config"] = cfg
    
    return {
        "niche": niche,
        "automation_config": cfg,
        "accounts": accounts,
        "sources": sources,
        "recent_broadcasts": recent_broadcasts,
        "total_accounts": len(accounts),
        "total_sources": len(sources)
    }

def save_niche_automation_config(niche_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cfg_json = json.dumps(config)
    cursor.execute("""
        UPDATE niches SET automation_config = ? WHERE id = ?
    """, (cfg_json, niche_id))
    if "cta_template" in config and config["cta_template"]:
        cursor.execute("UPDATE niches SET cta_text = ? WHERE id = ?", (config["cta_template"], niche_id))
    if "custom_hashtags" in config and config["custom_hashtags"]:
        cursor.execute("UPDATE niches SET default_hashtags = ? WHERE id = ?", (config["custom_hashtags"], niche_id))
    conn.commit()
    conn.close()
    return config

def bulk_add_accounts_to_niche(niche_id: str, accounts: List[Dict[str, Any]]) -> int:
    niche = get_niche_by_id(niche_id)
    niche_name = niche["name"] if niche else niche_id.capitalize()
    brand_color = niche["brand_color"] if niche else "#ea580c"
    
    count = 0
    for a in accounts:
        handle = a.get("handle", "").strip()
        if not handle:
            continue
        if not handle.startswith("@"):
            handle = f"@{handle}"
        
        acc_id = a.get("id") or handle.lstrip("@").replace(".", "_").lower()
        disp_name = a.get("display_name") or handle.lstrip("@").replace(".", " ").title()
        
        add_or_update_account({
            "id": acc_id,
            "handle": handle,
            "display_name": disp_name,
            "niche": niche_name,
            "niche_id": niche_id,
            "ig_user_id": a.get("ig_user_id", ""),
            "access_token": a.get("access_token", ""),
            "avatar_initials": a.get("avatar_initials") or "".join([w[0].upper() for w in disp_name.split()][:2]),
            "brand_color": a.get("brand_color") or brand_color,
            "profile_pic_url": a.get("profile_pic_url") or (f"/assets/logos/logo_{acc_id}.png" if Path(f"assets/logos/logo_{acc_id}.png").exists() else None),
            "is_active": a.get("is_active", 1)
        })
        count += 1
    return count

def bulk_add_sources_to_niche(niche_id: str, source_handles: List[str]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    count = 0
    for h in source_handles:
        clean_handle = h.strip().lstrip("@")
        if not clean_handle:
            continue
        cursor.execute("""
            INSERT OR IGNORE INTO monitored_sources (source_type, source_value, category, niche_id, target_account_id, auto_publish)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("instagram_handle", clean_handle, niche_id, niche_id, "", 1))
        count += 1
    conn.commit()
    conn.close()
    return count





def get_niche_template(niche_id: str) -> str:
    """Returns the template ID assigned to a niche, fallback to 'informative_cult'."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT template_id FROM niches WHERE id = ?", (niche_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row["template_id"]:
        return row["template_id"]
    return "informative_cult"

def set_niche_template(niche_id: str, template_id: str) -> bool:
    """Assigns a template ID to a niche."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE niches SET template_id = ? WHERE id = ?", (template_id, niche_id))
    conn.commit()
    conn.close()
    return True
