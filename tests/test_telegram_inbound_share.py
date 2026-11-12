import pytest
from unittest.mock import MagicMock, patch

from bot.octopus_telegram_bot import OctopusTelegramBot
from storage.db import get_niche_cluster, get_all_niches

class TestTelegramInboundShareSuite:

    def test_01_url_extracted_from_shared_message_text(self):
        bot = OctopusTelegramBot(bot_token="fake_token", chat_id="12345678")
        
        # Test direct URL
        with patch.object(bot, "handle_inbound_url") as mock_inbound:
            bot._handle_inbound_message({"text": "https://www.instagram.com/reel/C7x9_science", "chat": {"id": 12345678}})
            assert mock_inbound.called
            assert mock_inbound.call_args[1]["url"] == "https://www.instagram.com/reel/C7x9_science"

        # Test embedded URL in message text (e.g. shared from Instagram App)
        with patch.object(bot, "handle_inbound_url") as mock_inbound2:
            msg_text = "Watch this reel by @dailyfacts: https://www.instagram.com/reel/C8ABC_xyz/?igsh=123"
            bot._handle_inbound_message({"text": msg_text, "chat": {"id": 12345678}})
            assert mock_inbound2.called
            extracted_url = mock_inbound2.call_args[1]["url"]
            assert "https://www.instagram.com/reel/C8ABC_xyz/?igsh=123" in extracted_url

    def test_02_inbound_url_prompts_niche_selection(self):
        bot = OctopusTelegramBot(bot_token="fake_token", chat_id="12345678")
        with patch.object(bot, "send_text_message") as mock_send:
            res = bot.handle_inbound_url("https://www.instagram.com/reel/C7x9_science", chat_id=12345678)
            assert res["step"] == "awaiting_niche"
            assert "session_id" in res
            assert len(res["niches"]) >= 5
            assert mock_send.called
            call_text = mock_send.call_args[0][0]
            assert "Which niche do you want to publish on?" in call_text
            reply_markup = mock_send.call_args[1]["reply_markup"]
            assert "inline_keyboard" in reply_markup
            assert len(reply_markup["inline_keyboard"]) >= 5

    def test_03_niche_click_triggers_instant_pipeline_execution(self):
        bot = OctopusTelegramBot(bot_token="fake_token", chat_id="12345678")
        # Step 1: Ingest URL
        inbound = bot.handle_inbound_url("https://www.instagram.com/reel/C7x9_science", chat_id=12345678)
        session_id = inbound["session_id"]
        
        # Step 2: Simulate callback query from tapping niche with connected account (girls_dance)
        cb_payload = {
            "id": "cb_123",
            "data": f"tg_niche:{session_id}:girls_dance",
            "message": {"chat": {"id": 12345678}}
        }
        
        with patch("requests.post"):
            with patch.object(bot, "send_text_message") as mock_send_text:
                with patch.object(bot, "handle_execution") as mock_exec:
                    bot._handle_callback_query(cb_payload, async_exec=False)
                    # Verify immediate pipeline acknowledgment was sent to user
                    assert mock_send_text.called
                    messages_sent = [call[0][0] for call in mock_send_text.call_args_list]
                    assert any("Inbound Reel Ingested into" in m for m in messages_sent)
                    assert any("AI Pipeline running automated processing" in m for m in messages_sent)
                    assert mock_exec.called

    def test_04_niche_click_with_zero_accounts_halts_with_alert(self):
        bot = OctopusTelegramBot(bot_token="fake_token", chat_id="12345678")
        inbound = bot.handle_inbound_url("https://www.instagram.com/reel/C7x9_science", chat_id=12345678)
        session_id = inbound["session_id"]
        
        # Click niche with 0 connected accounts (ai_tech)
        cb_payload = {
            "id": "cb_456",
            "data": f"tg_niche:{session_id}:ai_tech",
            "message": {"chat": {"id": 12345678}}
        }
        
        with patch("requests.post"):
            with patch.object(bot, "send_text_message") as mock_send_text:
                with patch.object(bot, "handle_execution") as mock_exec:
                    bot._handle_callback_query(cb_payload, async_exec=False)
                    assert mock_send_text.called
                    messages_sent = [call[0][0] for call in mock_send_text.call_args_list]
                    assert any("No Accounts Connected" in m for m in messages_sent)
                    # Pipeline execution MUST NOT be triggered
                    assert not mock_exec.called
