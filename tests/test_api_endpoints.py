import os
import sys
import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from server import app

client = TestClient(app)

class TestOctopusAPI:
    """Comprehensive end-to-end API verification suite."""

    def test_01_dashboard_root_html(self):
        """Verify the web UI dashboard loads with 200 OK and includes Octopus branding."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Octopus Agent" in response.text or "Cloud Control Center" in response.text
        assert "text/html" in response.headers.get("content-type", "")

    def test_02_niches_api(self):
        """Verify listing and creating niches."""
        # 1. List niches
        res = client.get("/api/niches")
        assert res.status_code == 200
        niches = res.json()
        assert isinstance(niches, list)

        # 2. Create / Update test niche
        test_niche = {
            "id": "api_test_niche",
            "name": "API Test BioTech",
            "description": "Biotechnology and Synthetic Biology",
            "brand_color": "#10B981",
            "avatar_icon": "🧬",
            "default_hashtags": "#biotech #syntheticbio #dna",
            "cta_text": "Follow for daily biotech discoveries!"
        }
        res_post = client.post("/api/niches", json=test_niche)
        assert res_post.status_code == 200
        assert res_post.json()["status"] == "success"

        # 3. Retrieve cluster
        res_cluster = client.get("/api/niches/api_test_niche/cluster")
        assert res_cluster.status_code == 200
        cluster = res_cluster.json()
        assert cluster["niche"]["name"] == "API Test BioTech"

        # 4. Save automation config
        cfg_payload = {
            "source_mode": "all_sources",
            "ai_caption_mode": "smart_adapt",
            "hook_style": "curiosity"
        }
        res_cfg = client.post("/api/niches/api_test_niche/automation-config", json=cfg_payload)
        assert res_cfg.status_code == 200
        assert res_cfg.json()["status"] == "success"

    def test_03_stats_and_metrics_api(self):
        """Verify network stats endpoint returns complete infrastructure metrics."""
        res = client.get("/api/stats")
        assert res.status_code == 200
        stats = res.json()
        assert "total_accounts" in stats
        assert "active_accounts" in stats
        assert "total_reels" in stats
        assert "total_broadcasts" in stats

    def test_04_accounts_api(self):
        """Verify listing, filtering, and creating accounts."""
        # List accounts
        res = client.get("/api/accounts")
        assert res.status_code == 200
        accounts = res.json()
        assert isinstance(accounts, list)

        # Create single account
        test_acc = {
            "id": "test_acc_001",
            "handle": "@test.curiosity.daily",
            "display_name": "Test Curiosity Daily",
            "niche": "science",
            "brand_color": "#ea580c"
        }
        res_add = client.post("/api/accounts", json=test_acc)
        assert res_add.status_code == 200
        assert res_add.json()["status"] == "success"

        # Filter by niche
        res_filter = client.get("/api/accounts?niche=science")
        assert res_filter.status_code == 200
        assert any(a["id"] == "test_acc_001" for a in res_filter.json())

    def test_05_sources_and_suggestions_api(self):
        """Verify source monitors and handle suggestion queries."""
        # List sources
        res = client.get("/api/sources")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

        # Handle suggestions
        res_sugg = client.get("/api/suggestions/handles?niche=quantum")
        assert res_sugg.status_code == 200
        handles = res_sugg.json()
        assert isinstance(handles, list)
        assert len(handles) > 0

    def test_06_llm_brain_settings_and_handshake(self):
        """Verify LLM config retrieval, saving, and Groq handshake test."""
        # 1. Get public config
        res = client.get("/api/settings/llm")
        assert res.status_code == 200
        cfg = res.json()
        assert "provider" in cfg
        assert "providers_info" in cfg
        assert "groq" in cfg["providers_info"]
        assert "ollama" in cfg["providers_info"]

        # 2. Update config to Groq
        update_payload = {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.7
        }
        res_update = client.post("/api/settings/llm", json=update_payload)
        assert res_update.status_code == 200
        assert res_update.json()["status"] == "success"

        # 3. Test Groq handshake with test/demo key
        test_payload = {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "api_key": "demo"
        }
        res_test = client.post("/api/settings/llm/test", json=test_payload)
        assert res_test.status_code == 200
        handshake = res_test.json()
        assert handshake["success"] is True
        assert handshake["status"] == "connected"
        assert handshake["provider"] == "groq"
        assert "latency_ms" in handshake
        assert "sample_hook" in handshake

    def test_07_pipeline_state_and_step_execution(self):
        """Verify the 5-step internal pipeline trace endpoints."""
        # 1. Get pipeline state
        res = client.get("/api/pipeline/state")
        assert res.status_code == 200
        state = res.json()
        assert "step1_scrape" in state
        assert "step2_media" in state
        assert "step3_llm" in state
        assert "step4_compositor" in state
        assert "step5_fanout" in state

        # 2. Run single pipeline pass
        run_payload = {
            "source_handle": "@physicsfun",
            "niche_id": "quantum",
            "aspect_mode": "pillarbox",
            "dry_run": True
        }
        res_run = client.post("/api/pipeline/run", json=run_payload)
        assert res_run.status_code == 200
        run_data = res_run.json()
        assert run_data["success"] is True
        assert "@physicsfun" in run_data["state"]["step1_scrape"]["handle"]

        # 3. Update pipeline step copy manually
        update_copy_payload = {
            "headline": "Quantum Levitation Defies Friction at -196°C",
            "caption_paragraphs": [
                "Under liquid nitrogen cooling, type-II superconductors exhibit flux pinning.",
                "This phenomenon locks magnetic flux lines inside tiny crystal defects.",
                "Follow @uncover.quantum for daily breakthroughs in physics!"
            ],
            "credit": "via @physicsfun",
            "hashtags": ["#quantum", "#physics", "#science"]
        }
        res_step = client.post("/api/pipeline/update-step", json=update_copy_payload)
        assert res_step.status_code == 200
        assert res_step.json()["success"] is True

        # 4. Regenerate copy via AI enricher
        regen_payload = {
            "source_handle": "@physicsfun",
            "topic": "Superconductivity and Zero Electrical Resistance",
            "voice_tone": "curiosity"
        }
        res_regen = client.post("/api/pipeline/regenerate-copy", json=regen_payload)
        assert res_regen.status_code == 200
        assert res_regen.json()["success"] is True
        assert len(res_regen.json()["headline"]) > 10

    def test_08_swarm_coordinator_api(self):
        """Verify multi-agent swarm status and parallel trigger."""
        # 1. Get swarm status
        res = client.get("/api/swarm/status")
        assert res.status_code == 200
        status = res.json()
        assert "total_niches" in status
        assert "total_destination_accounts" in status
        assert "total_sources_monitored" in status

        # 2. Trigger swarm cycle (dry-run background task)
        from unittest.mock import patch
        with patch("agents.swarm_coordinator.OctopusSwarmCoordinator.run_swarm_parallel") as mock_run:
            mock_run.return_value = {"status": "SUCCESS", "message": "Mocked test pass"}
            res_trigger = client.post("/api/swarm/trigger")
            assert res_trigger.status_code == 200
            assert res_trigger.json()["status"] == "started"

    def test_09_telegram_bot_api(self):
        """Verify Telegram remote control and dispatch endpoints."""
        # 1. Status
        res_status = client.get("/api/telegram/status")
        assert res_status.status_code == 200
        assert "configured" in res_status.json()

        # 2. Dispatch interactive step
        dispatch_payload = {
            "step": "start",
            "url": "https://www.instagram.com/reel/C8_science_test/",
            "chat_id": "test_chat_123"
        }
        res_dispatch = client.post("/api/telegram/dispatch_step", json=dispatch_payload)
        assert res_dispatch.status_code == 200
        session_info = res_dispatch.json()
        assert session_info["step"] == "awaiting_niche"
        assert "session_id" in session_info

        # 3. Dispatch select_niche step
        niche_dispatch = {
            "step": "select_niche",
            "session_id": session_info["session_id"],
            "niche_id": "quantum",
            "chat_id": "test_chat_123"
        }
        res_niche = client.post("/api/telegram/dispatch_step", json=niche_dispatch)
        assert res_niche.status_code == 200
        assert res_niche.json()["step"] == "awaiting_pages"

        # 4. Logs endpoint
        res_logs = client.get("/api/telegram/logs")
        assert res_logs.status_code == 200
        assert isinstance(res_logs.json(), list)

    def test_10_meta_connection_test(self):
        """Verify Meta Graph API token test endpoint rejects invalid tokens gracefully."""
        res = client.post("/api/meta/test-connection", json={"access_token": "invalid_test_token"})
        assert res.status_code == 200
        result = res.json()
        assert result["valid"] is False
        assert "error" in result

if __name__ == "__main__":
    pytest.main(["-v", "-s", "-p", "no:libtmux", __file__])
