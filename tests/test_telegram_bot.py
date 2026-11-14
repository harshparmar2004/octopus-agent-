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

    # 3. Step 2: Select Niche with Live Account (girls_dance has cute_aarohi_007)
    step2 = bot.handle_niche_selection(session_id, "girls_dance")
    assert step2["step"] == "awaiting_pages"
    assert step2["total_pages"] == 1
    assert step2["accounts"][0]["handle"] == "@cute.aarohi.007"
    print("[PASS] Step 2 (Niche -> Prompt Pages) verified: 1 Connected Page (@cute.aarohi.007)")

    # 4. Step 3: Execute Fan-out for girls_dance
    step3 = bot.handle_execution(session_id, "girls_dance", target="all", dry_run=True)
    assert step3["step"] == "completed"
    assert step3["published_count"] == 1
    print(f"[PASS] Step 3 (Execute -> Fan-Out) verified: {step3['published_count']}/{step3['total_count']} published")

    # 5. Verify 0-account niche state handling
    step2_zero = bot.handle_niche_selection(session_id, "information")
    assert step2_zero["total_pages"] == 0
    assert "0 accounts" in step2_zero["prompt_text"]
    print("[PASS] Step 2 (0-account niche) verified: Clean warning and no placeholder fallback")

def test_girls_dance_single_account_pipeline():
    bot = OctopusTelegramBot()
    step1 = bot.handle_inbound_url("https://www.instagram.com/reel/C8yDanceTest")
    session_id = step1["session_id"]
    
    # Execute for girls_dance
    result = bot.handle_execution(session_id, "girls_dance", target="all", dry_run=True)
    assert result["step"] == "completed"
    # Must target ONLY 1 account (@cute.aarohi.007)
    assert result["total_count"] == 1
    assert result["published_count"] == 1
    item = result["published_items"][0]
    assert item["handle"] == "@cute.aarohi.007"
    assert item["status"] == "PUBLISHED"
    assert "instagram.com" in item["url"]
    print("[PASS] Girls Dance single authenticated account (@cute.aarohi.007) verified with link:", item["url"])

if __name__ == "__main__":
    test_telegram_conversational_workflow()
    test_girls_dance_single_account_pipeline()
    print("\nAll Octopus Telegram tests passed successfully!")
