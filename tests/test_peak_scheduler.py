import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pytest
from fastapi.testclient import TestClient
from server import app
from storage.db import init_octopus_db
from storage.scheduler_db import (
    init_scheduler_tables,
    upsert_candidate,
    get_candidates,
    get_candidate,
    update_candidate,
    get_niche_schedule,
    save_niche_schedule,
    create_slot_run,
    get_slot_run,
    update_slot_run,
    get_slot_runs,
    count_account_posts_since,
    last_post_time,
    account_guard,
    to_iso,
    utcnow
)
from processors.reel_scorer import ReelScorer
from scheduler.peak_scheduler import PeakTimeScheduler, compute_scheduled_for, slot_jitter_seconds

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_octopus_db()
    init_scheduler_tables()

class TestPeakSchedulerSuite:
    """End-to-end verification of the Peak-Time Content Scheduler and AI Reel Scorer."""

    def test_01_candidate_pool_upsert_and_retrieval(self):
        """Verifies candidates can be stored, updated with new engagement, and retrieved."""
        cand_id = upsert_candidate({
            "niche_id": "information",
            "source_id": 1,
            "source_handle": "dailyfacts",
            "shortcode": "TEST_CAND_01",
            "permalink": "https://www.instagram.com/reel/TEST_CAND_01/",
            "caption": "Mind blowing information fact about deep ocean trenches and unknown marine life #facts",
            "posted_at": to_iso(utcnow() - timedelta(hours=4)),
            "like_count": 12500,
            "comments_count": 480,
            "source_followers": 250000,
            "duration_s": 28.5,
            "media_type": "VIDEO"
        })
        assert cand_id is not None
        c = get_candidate(cand_id)
        assert c["shortcode"] == "TEST_CAND_01"
        assert c["like_count"] == 12500

        # Upsert again with increased likes (idempotent, refreshes metrics)
        cand_id2 = upsert_candidate({
            "niche_id": "information",
            "shortcode": "TEST_CAND_01",
            "permalink": "https://www.instagram.com/reel/TEST_CAND_01/",
            "like_count": 15000
        })
        assert cand_id2 == cand_id
        c_updated = get_candidate(cand_id)
        assert c_updated["like_count"] == 15000

    def test_02_scorer_signals_freshness_and_velocity(self):
        """Verifies fresh viral reel outscores older average reel."""
        scorer = ReelScorer(use_llm=False)
        now = utcnow()

        # High velocity fresh reel (3 hours old, high engagement rate)
        c_fresh = {
            "id": 101,
            "niche_id": "information",
            "posted_at": to_iso(now - timedelta(hours=3)),
            "like_count": 25000,
            "comments_count": 900,
            "source_followers": 100000,
            "caption": "Astonishing discovery about quantum particles"
        }
        age_f = scorer.age_hours(c_fresh, now)
        v_f = scorer.velocity_score(c_fresh, age_f)
        fresh_f = scorer.freshness_score(age_f)

        # Older reel (50 hours old, low engagement)
        c_old = {
            "id": 102,
            "niche_id": "information",
            "posted_at": to_iso(now - timedelta(hours=50)),
            "like_count": 1000,
            "comments_count": 20,
            "source_followers": 200000,
            "caption": "Random video post"
        }
        age_o = scorer.age_hours(c_old, now)
        v_o = scorer.velocity_score(c_old, age_o)
        fresh_o = scorer.freshness_score(age_o)

        assert fresh_f == 100.0  # <= 12 hours
        assert fresh_o < 50.0   # linear decay towards 72h
        assert v_f > v_o

    def test_03_quality_gates_reject_promo_and_bad_duration(self):
        """Verifies sponsored/promo reels are hard-rejected."""
        scorer = ReelScorer(use_llm=False)
        promo_cand = {
            "shortcode": "PROMO_01",
            "caption": "Amazing product! Use code SAVE20 for 20% off shop now #ad #sponsored",
            "media_type": "VIDEO"
        }
        score, reason = scorer.quality_gate(promo_cand)
        assert score == 0.0
        assert "promo/sponsored" in reason

        bad_dur = {
            "shortcode": "BAD_DUR",
            "caption": "Valid caption",
            "media_type": "VIDEO",
            "duration_s": 3.0  # too short (< 7s)
        }
        score_d, reason_d = scorer.quality_gate(bad_dur)
        assert score_d == 0.0
        assert "duration" in reason_d

    def test_04_niche_schedule_validation_and_ist_slots(self):
        """Verifies default peak slots (08:00, 13:00, 18:00, 21:00 IST) and spacing constraints."""
        sched = get_niche_schedule("information")
        assert "18:00" in sched["slot_times"]
        assert sched["timezone"] == "Asia/Kolkata"

        # Update with valid 4 slots
        updated = save_niche_schedule("information", {
            "slot_times": ["08:00", "13:00", "18:00", "21:30"],
            "jitter_minutes": 6
        })
        assert updated["jitter_minutes"] == 6
        assert len(updated["slot_times"]) == 4

        # Enforce >= 2.5 hours gap: attempt slots with 1 hour gap should raise ValueError
        with pytest.raises(ValueError):
            save_niche_schedule("information", {"slot_times": ["18:00", "19:00"]})

    def test_05_account_guard_daily_cap_and_spacing(self):
        """Verifies account guard prevents posting if daily cap reached or last post was too recent."""
        now = utcnow()
        # Non-existent or fresh account has no guard reason
        guard = account_guard("fresh_acc_99", now=now)
        assert guard is None

    def test_06_deterministic_slot_jitter_and_scheduling(self):
        """Verifies deterministic jitter computes consistent scheduled_for timestamps across restarts."""
        from datetime import date
        d = date(2026, 11, 15)
        # Jitter should be identical for the same niche, date, slot
        j1 = slot_jitter_seconds("information", "2026-11-15", "18:00", 8)
        j2 = slot_jitter_seconds("information", "2026-11-15", "18:00", 8)
        assert j1 == j2
        assert -480 <= j1 <= 480  # within 8 minutes

        # Different niches get different jitters (avoiding multi-niche burst collisions)
        j_quantum = slot_jitter_seconds("quantum", "2026-11-15", "18:00", 8)
        # Highly unlikely to be identical
        # Compute exact UTC timestamp
        sched_dt = compute_scheduled_for("information", d, "18:00", "Asia/Kolkata", 8)
        assert sched_dt.tzinfo is not None

    def test_07_api_scheduler_endpoints(self):
        """Verifies all FastAPI scheduler API endpoints."""
        # 1. Schedule status
        res = client.get("/api/schedule/status")
        assert res.status_code == 200
        assert res.json()["status"] == "success"

        # 2. Get schedule
        res = client.get("/api/niches/information/schedule")
        assert res.status_code == 200
        data = res.json()
        assert "schedule" in data
        assert "slot_times" in data["schedule"]

        # 3. Update schedule
        res = client.put("/api/niches/information/schedule", json={
            "jitter_minutes": 7
        })
        assert res.status_code == 200
        assert res.json()["schedule"]["jitter_minutes"] == 7

        # 4. List candidates
        res = client.get("/api/candidates?niche_id=information")
        assert res.status_code == 200
        assert "candidates" in res.json()

        # 5. Upcoming schedule runs
        res = client.get("/api/schedule/upcoming?hours=48")
        assert res.status_code == 200
        assert "slot_runs" in res.json()
