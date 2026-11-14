import pytest
from bot.octopus_telegram_bot import OctopusTelegramBot
from storage.db import (
    create_or_update_niche,
    delete_niche,
    add_or_update_account,
    delete_account,
    get_niche_cluster,
    get_all_niches
)

class DummyTelegramBot(OctopusTelegramBot):
    def __init__(self):
        super().__init__(bot_token="dummy_token", chat_id="12345678")
        self.sent_messages = []

    def send_text_message(self, text, reply_markup=None, target_chat_id=None):
        self.sent_messages.append({"text": text, "reply_markup": reply_markup, "chat_id": target_chat_id})
        return {"message_id": 99999}

def test_dynamic_niche_inline_keyboard():
    bot = DummyTelegramBot()
    res = bot.handle_inbound_url("https://www.instagram.com/reel/C8xyz123/", chat_id=12345678)
    assert res["step"] == "awaiting_niche"
    assert res["reel_id"] == "C8xyz123"
    
    assert len(bot.sent_messages) > 0
    msg = bot.sent_messages[-1]
    keyboard = msg["reply_markup"]["inline_keyboard"]
    flat_buttons = [btn for row in keyboard for btn in row]
    
    # girls_dance has cute_aarohi_007 configured with Meta credentials, so it must display (1 Account)
    girls_btn = next((b for b in flat_buttons if "girls_dance" in b.get("callback_data", "")), None)
    assert girls_btn is not None
    assert "(1 Account)" in girls_btn["text"]

    # Verify that girls_dance appears among the first niche choices because it has active accounts
    niche_buttons = [b for b in flat_buttons if b.get("callback_data", "").startswith("tg_niche:")]
    assert girls_btn in niche_buttons[:2]

def test_create_custom_niche_and_attach_account():
    test_niche_id = "dyn_robotics_lab"
    test_acc_id = "dyn_bot_01"

    try:
        # 1. Create a custom niche in the database (simulating Dashboard Create Niche)
        create_or_update_niche({
            "id": test_niche_id,
            "name": "Dynamic Robotics Lab",
            "avatar_icon": "🤖",
            "description": "Autonomous Robotics Lab",
            "brand_color": "#10b981",
            "default_hashtags": "#robotics #ai #future",
            "cta_text": "Follow for robotics innovations!"
        })

        bot = DummyTelegramBot()
        res1 = bot.handle_inbound_url("https://www.youtube.com/shorts/test_robot_99", chat_id=12345678)
        msg1 = bot.sent_messages[-1]
        buttons1 = [btn for row in msg1["reply_markup"]["inline_keyboard"] for btn in row]

        dyn_btn1 = next((b for b in buttons1 if test_niche_id in b.get("callback_data", "")), None)
        assert dyn_btn1 is not None
        assert "Dynamic Robotics Lab" in dyn_btn1["text"]
        assert "(0 Accounts)" in dyn_btn1["text"]

        # 2. Select this 0-account niche
        sel1 = bot.handle_niche_selection(res1["session_id"], test_niche_id, chat_id=12345678)
        assert sel1["total_pages"] == 0
        assert len(sel1["accounts"]) == 0
        assert "0 accounts" in sel1["prompt_text"]

        # 3. Now connect an Instagram account with real Meta Graph API credentials
        add_or_update_account({
            "id": test_acc_id,
            "handle": "@dyn.bot.lab",
            "display_name": "Dyn Bot Lab",
            "niche_id": test_niche_id,
            "niche": "Dynamic Robotics Lab",
            "access_token": "EAAB" + "m" * 50,
            "ig_user_id": "17841400099887766",
            "is_active": 1
        })

        # 4. Trigger inbound URL again - should now show (1 Account) and bubble up!
        res2 = bot.handle_inbound_url("https://www.youtube.com/shorts/test_robot_99", chat_id=12345678)
        msg2 = bot.sent_messages[-1]
        buttons2 = [btn for row in msg2["reply_markup"]["inline_keyboard"] for btn in row]

        dyn_btn2 = next((b for b in buttons2 if test_niche_id in b.get("callback_data", "")), None)
        assert dyn_btn2 is not None
        assert "(1 Account)" in dyn_btn2["text"]

        # 5. Select this niche now - should offer to publish to that 1 account
        sel2 = bot.handle_niche_selection(res2["session_id"], test_niche_id, chat_id=12345678)
        assert sel2["total_pages"] == 1
        assert sel2["accounts"][0]["handle"] == "@dyn.bot.lab"

    finally:
        delete_account(test_acc_id)
        delete_niche(test_niche_id)
