import os
import sys
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import pytest
from fastapi.testclient import TestClient
from server import app
from processors.anti_shadowban import AntiShadowbanEngine

client = TestClient(app)

class TestAntiShadowbanSuite:
    """Verifies that the anti-shadowban engine prevents duplicate detection and bot footprint."""

    def test_01_video_mutation_params_divergence(self):
        """Verifies that different account indices receive distinct perceptual mutation parameters."""
        p0 = AntiShadowbanEngine.get_video_mutation_params(0)
        p1 = AntiShadowbanEngine.get_video_mutation_params(1)
        p2 = AntiShadowbanEngine.get_video_mutation_params(2)

        assert p0["contrast"] != p1["contrast"] or p0["brightness"] != p1["brightness"]
        assert p0["video_filters"] != p1["video_filters"]
        assert p0["device_profile"]["model"] != ""
        assert len(p0["metadata_args"]) > 0
        assert "-map_metadata" in p0["metadata_args"]

    def test_02_hashtag_shuffling_zero_collision(self):
        """Verifies that across 20 accounts in a niche pod, zero identical hashtag sets are generated."""
        niches = ["information", "quantum", "robotics", "ai", "space", "biotech", "parties", "organizing", "fashion"]
        for niche in niches:
            sets = [tuple(AntiShadowbanEngine.generate_niche_hashtags(niche, i, count=7)) for i in range(20)]
            # All 20 sets must be unique
            assert len(sets) == len(set(sets)), f"Hashtag collision detected in niche {niche}!"

    def test_03_caption_mutation_preserves_niche_while_varying_syntax(self):
        """Verifies that caption mutation varies hook sentence, CTA and synonyms while keeping niche facts."""
        base_headline = "Two people can earn the exact same salary and end up living completely different lives"
        base_body = (
            "Two people can earn the exact same salary and end up living completely different lives.\n\n"
            "Furthermore, the difference isn't how much you make. It is your financial thermostat. "
            "Interestingly, small daily habits compound into colossal financial divides."
        )

        c0 = AntiShadowbanEngine.mutate_caption(base_body, base_headline, "@info.daily", "information", 0)
        c1 = AntiShadowbanEngine.mutate_caption(base_body, base_headline, "@info.pulse", "information", 1)
        c2 = AntiShadowbanEngine.mutate_caption(base_body, base_headline, "@info.nexus", "information", 2)

        assert c0 != c1
        assert c1 != c2
        assert c0 != c2
        # Niche keywords preserved
        for cap in [c0, c1, c2]:
            assert "salary" in cap.lower() or "financial" in cap.lower()

    def test_04_staggered_jitter_scheduling_non_colliding(self):
        """Verifies that publish offsets are sequential, with non-zero natural gaps (Balanced 30-45s by default)."""
        # 1. Test Default Balanced Mode (30-45s jitter, ~5-8 mins for 20 accounts)
        schedule = AntiShadowbanEngine.get_staggered_schedule(account_count=10)
        assert len(schedule) == 10
        assert schedule[0]["offset_seconds"] == 0
        assert schedule[0]["mode"] == "balanced"

        for i in range(1, len(schedule)):
            prev = schedule[i-1]["offset_seconds"]
            curr = schedule[i]["offset_seconds"]
            diff = curr - prev
            # Balanced mode: gaps should be between 30s and 60s
            assert 30 <= diff <= 60, f"Gap out of balanced bounds between account {i-1} and {i}: {diff}s"

        # 2. Test Turbo Mode (12-20s)
        turbo_sched = AntiShadowbanEngine.get_staggered_schedule(account_count=5, mode="turbo")
        for i in range(1, len(turbo_sched)):
            diff = turbo_sched[i]["offset_seconds"] - turbo_sched[i-1]["offset_seconds"]
            assert 10 <= diff <= 25

        # 3. Test Stealth Mode (120-210s)
        stealth_sched = AntiShadowbanEngine.get_staggered_schedule(account_count=5, mode="stealth")
        for i in range(1, len(stealth_sched)):
            diff = stealth_sched[i]["offset_seconds"] - stealth_sched[i-1]["offset_seconds"]
            assert diff >= 120

    def test_05_anti_shadowban_api_preview_endpoint(self):
        """Verifies /api/anti-shadowban/preview returns valid JSON with 3 simulated variants."""
        res = client.get("/api/anti-shadowban/preview?niche=quantum&handle=physicsfun")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["shield_active"] is True
        assert len(data["variations"]) == 3

        v0 = data["variations"][0]
        v1 = data["variations"][1]
        assert v0["caption"] != v1["caption"]
        assert v0["hashtags"] != v1["hashtags"]
        assert v0["scheduled_offset"] != v1["scheduled_offset"]
