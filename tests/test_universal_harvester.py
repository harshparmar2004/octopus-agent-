import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from scrapers.universal_harvester import UniversalContentHarvester
from bot.octopus_telegram_bot import OctopusTelegramBot

def test_classify_all_platforms():
    test_cases = [
        ("https://www.instagram.com/reel/C7x9_science/?igsh=123", "instagram", "Instagram Reel", "📸", "C7x9_science"),
        ("https://www.instagram.com/p/C99ABCdef/", "instagram", "Instagram Reel", "📸", "C99ABCdef"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "youtube", "YouTube Shorts", "▶️", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "youtube", "YouTube Video", "▶️", "dQw4w9WgXcQ"),
        ("https://www.snapchat.com/spotlight/W7_EDzX3SR68888", "snapchat", "Snapchat Spotlight", "👻", "W7_EDzX3SR68888"),
        ("https://x.com/tech_insider/status/17849102938472910", "twitter", "Twitter / X", "🐦", "17849102938472910"),
        ("https://twitter.com/OpenAI/status/1758229880193495379", "twitter", "Twitter / X", "🐦", "1758229880193495379"),
        ("https://www.reddit.com/r/technology/comments/1c3x4y/breakthrough_ai_robot/", "reddit", "Reddit Video", "🤖", "1c3x4y"),
        ("https://v.redd.it/9q8w7e6r5t", "reddit", "Reddit Video", "🤖", "9q8w7e6r5t"),
        ("https://www.tiktok.com/@creator/video/734891029384719283", "tiktok", "TikTok", "🎵", "734891029384719283"),
        ("https://assets.mixkit.co/videos/preview/mixkit-robot-dance-large.mp4", "direct", "Direct Video Stream", "🎥", "mixkit-robot-dance-large"),
    ]

    for url, exp_plat, exp_name, exp_emoji, exp_id in test_cases:
        c = UniversalContentHarvester.classify_url(url)
        assert c["platform"] == exp_plat, f"Failed platform for {url}: got {c['platform']}"
        assert c["platform_name"] == exp_name, f"Failed name for {url}: got {c['platform_name']}"
        assert c["platform_emoji"] == exp_emoji, f"Failed emoji for {url}: got {c['platform_emoji']}"
        assert c["content_id"] == exp_id, f"Failed content_id for {url}: got {c['content_id']}"

def test_telegram_inbound_url_multi_platform_detection():
    bot = OctopusTelegramBot()
    bot.chat_id = "123456"

    yt_res = bot.handle_inbound_url("https://www.youtube.com/shorts/dQw4w9WgXcQ", chat_id="123456")
    assert "YouTube Shorts" in yt_res["prompt_text"]
    assert "dQw4w9WgXcQ" in yt_res["reel_id"]

    snap_res = bot.handle_inbound_url("https://www.snapchat.com/spotlight/W7_EDzX3SR68888", chat_id="123456")
    assert "Snapchat Spotlight" in snap_res["prompt_text"]
    assert "W7_EDzX3SR68888" in snap_res["reel_id"]

    tw_res = bot.handle_inbound_url("https://x.com/tech_insider/status/17849102938472910", chat_id="123456")
    assert "Twitter / X" in tw_res["prompt_text"]
    assert "17849102938472910" in tw_res["reel_id"]

    rd_res = bot.handle_inbound_url("https://www.reddit.com/r/technology/comments/1c3x4y/breakthrough_ai_robot/", chat_id="123456")
    assert "Reddit Video" in rd_res["prompt_text"]
    assert "1c3x4y" in rd_res["reel_id"]

def test_universal_harvester_fallback_local_cache(tmp_path):
    harvester = UniversalContentHarvester(download_dir=tmp_path)
    sample_file = tmp_path / "test_yt_raw.mp4"
    sample_file.write_bytes(b"0" * 60000)

    res = harvester.harvest("https://www.youtube.com/shorts/sample123", "test_yt")
    assert res is not None
    assert res["filepath"] == str(sample_file)
    assert res["platform"] == "YouTube Shorts"
