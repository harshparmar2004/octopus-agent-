import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from server import app
from bot.octopus_telegram_bot import OctopusTelegramBot
from publisher.meta_graph_api import MetaReelsPublisher
from scheduler.peak_scheduler import PeakTimeScheduler
from storage.scheduler_db import create_slot_run, get_slot_run

client = TestClient(app)

class TestTelegramCompletionNotificationSuite:

    def test_01_send_broadcast_completion_summary_formatting(self):
        bot = OctopusTelegramBot(bot_token="fake_token", chat_id="12345678")
        with patch.object(bot, "send_text_message") as mock_send:
            res = bot.send_broadcast_completion_summary(
                niche_id="information",
                niche_name="Information & Infotainment",
                slot_time="18:00 IST",
                accounts_posted=20,
                accounts_total=20,
                accounts_skipped=0,
                source_handle="@dailyfacts",
                hook_text="Two people can earn the exact same salary and live different lives",
                completed_at_ist="2026-11-11 18:04:12 IST",
                dry_run=True
            )
            assert res is True
            assert mock_send.called
            sent_text = mock_send.call_args[0][0]
            
            # Verify concise required fields
            assert "Octopus Automation Broadcast Completed" in sent_text
            assert "Information & Infotainment" in sent_text
            assert "18:00 IST" in sent_text
            assert "2026-11-11 18:04:12 IST" in sent_text
            assert "20/20 Accounts" in sent_text
            assert "0 skipped" in sent_text
            assert "@dailyfacts" in sent_text
            assert "Anti-Shadowban" in sent_text
            
            # Check internal dispatch log entry
            assert len(bot.dispatch_logs) > 0
            latest = bot.dispatch_logs[0]
            assert latest["niche_id"] == "information"
            assert latest["pages_count"] == 20
            assert latest["status"] == "COMPLETED"

    def test_02_publish_slot_triggers_telegram_summary(self):
        bot = OctopusTelegramBot(bot_token="fake_token", chat_id="12345678")
        sched = PeakTimeScheduler(dry_run=True, telegram=bot)
        
        # Create a mock slot run with prepared tasks
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        run = create_slot_run("information", "18:00", now.date().isoformat(), now, dry_run=True)
        
        # Attach dummy payload
        import json
        from storage.scheduler_db import update_slot_run
        payload = {
            "tasks": [
                {"account": {"id": "acc_1", "handle": "@info.one"}, "log_id": 1, "filename": "v1.mp4", "caption": "c1"},
                {"account": {"id": "acc_2", "handle": "@info.two"}, "log_id": 2, "filename": "v2.mp4", "caption": "c2"}
            ]
        }
        update_slot_run(run["id"], {
            "status": "APPROVED",
            "reel_id": "test_reel_123",
            "prepared_payload": payload,
            "accounts_total": 2
        })
        
        with patch.object(sched.fanout, "execute_broadcast", return_value={"successful_posts_count": 2, "skipped_accounts": []}):
            with patch.object(bot, "send_broadcast_completion_summary") as mock_summary:
                res = sched.publish_slot(run["id"], now=now)
                assert res["status"] == "DONE"
                assert res["accounts_posted"] == 2
                assert mock_summary.called
                kwargs = mock_summary.call_args[1]
                assert kwargs["niche_id"] == "information"
                assert kwargs["accounts_posted"] == 2
                assert kwargs["accounts_total"] == 2

    def test_03_meta_graph_api_token_validity_and_publisher(self):
        # Test token validity with empty token
        res_empty = MetaReelsPublisher.test_token_validity("")
        assert res_empty["valid"] is False
        assert "No token provided" in res_empty["error"]

        # Test dry-run publish reel
        pub = MetaReelsPublisher(ig_user_id="", access_token="")
        pub_res = pub.publish_reel(
            video_public_url="https://domain.com/output/test.mp4",
            caption="Test Caption",
            dry_run=True
        )
        assert pub_res["success"] is True
        assert pub_res["mode"] == "dry_run"
        assert "simulated_media_id" in pub_res

    def test_04_meta_graph_api_endpoints(self):
        # 1. Test Meta connection test endpoint
        res = client.post("/api/meta/test-connection", json={"access_token": ""})
        assert res.status_code == 200
        data = res.json()
        assert data.get("valid") is False

        # 2. Test Meta discovery endpoint
        res2 = client.post("/api/meta/discover", json={"access_token": ""})
        assert res2.status_code == 200
        data2 = res2.json()
        assert "discovered" in data2
        assert isinstance(data2["discovered"], list)

    def test_05_telegram_endpoints_and_bot_ping(self):
        # 1. Telegram status
        res = client.get("/api/telegram/status")
        assert res.status_code == 200
        assert "configured" in res.json()
        assert "mode" in res.json()

        # 2. Telegram test ping (simulated when no tokens)
        res_ping = client.post("/api/telegram/test_ping", json={"chat_id": ""})
        assert res_ping.status_code == 200
        assert "success" in res_ping.json()

        # 3. Telegram logs
        res_logs = client.get("/api/telegram/logs")
        assert res_logs.status_code == 200
        assert isinstance(res_logs.json(), list)

    def test_06_manual_slot_run_end_to_end_telegram_flow(self):
        # Trigger an on-demand slot execution and verify it triggers properly
        res = client.post("/api/schedule/information/run-slot-now?dry_run=true")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "slot_run" in data
        assert data["slot_run"]["niche_id"] == "information"
