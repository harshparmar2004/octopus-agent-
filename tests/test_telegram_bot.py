import sys
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from bot.octopus_telegram_bot import OctopusTelegramBot

def test_telegram_conversational_workflow():
    bot = OctopusTelegramBot()
    
    # 1. Status Info
    status = bot.get_status_info()
    assert "mode" in status
    print("[PASS] Status Info verified:", status["mode"])

    # 2. Step 1: Inbound URL
    step1 = bot.handle_inbound_url("https://www.instagram.com/reel/sample_test")
    assert step1["step"] == "awaiting_niche"
    assert len(step1["niches"]) >= 5
    session_id = step1["session_id"]
    print("[PASS] Step 1 (URL -> Prompt Niche) verified")

    # 3. Step 2: Select Niche
    step2 = bot.handle_niche_selection(session_id, "information")
    assert step2["step"] == "awaiting_pages"
    assert step2["total_pages"] >= 10
    print("[PASS] Step 2 (Niche -> Prompt Pages) verified: 10 Connected Pages")

    # 4. Step 3: Execute Fan-out
    step3 = bot.handle_execution(session_id, "information", target="all")
    assert step3["step"] == "completed"
    assert step3["published_count"] >= 10
    print(f"[PASS] Step 3 (Execute -> Fan-Out) verified: {step3['published_count']}/{step3['total_count']} published")

if __name__ == "__main__":
    test_telegram_conversational_workflow()
    print("\nAll Octopus Telegram tests passed successfully!")
