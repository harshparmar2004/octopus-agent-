import os
import pytest
from pathlib import Path
from PIL import Image

from config import ChannelProfile, settings
from renderers.card_renderer import CardRenderer
from renderers.niche_templates import get_template_for_niche
from renderers.video_compositor import VideoCompositor
from publisher.octopus_fanout import OctopusFanoutEngine
from storage.db import init_octopus_db, insert_or_update_reel, get_reel

def test_cult_badge_assets_exist():
    """Verify that circular CULT badge assets are present in assets/logos/ and assets/."""
    expected_paths = [
        Path("assets/logos/logo_cult_badge.png"),
        Path("assets/logos/logo_cult_information.png"),
        Path("assets/logos/logo_ai_tech.png"),
        Path("assets/logo_cult_badge.png"),
        Path("assets/logo_cult_information.png"),
    ]
    for p in expected_paths:
        assert p.exists(), f"Missing required asset: {p}"
        img = Image.open(p)
        assert img.width == 512 and img.height == 512
        assert img.mode in ("RGBA", "RGB")

def test_card_renderer_finds_cult_logo():
    """Verify that CardRenderer locates the circular CULT badge."""
    renderer = CardRenderer()
    channel = ChannelProfile(
        handle="@cult_information",
        display_name="Cult Information",
        niche="Informative AI & Tech",
        logo_filename="logo_cult_badge.png",
        subreddits=[],
        default_hashtags=[],
        cta_link=""
    )
    logo_path = renderer._find_logo_path(channel)
    assert logo_path is not None
    assert Path(logo_path).exists()
    assert "cult" in Path(logo_path).name.lower() or "ai_tech" in Path(logo_path).name.lower()

def test_render_top_card_cult_dimensions_and_alpha():
    """Verify _render_top_card_cult renders full 1080x1920 overlay with solid black header box."""
    renderer = CardRenderer()
    template = get_template_for_niche("ai_tech")
    assert "Cult Information" in template.name
    assert template.highlight_color.upper() in ("#C1F02A", "#DDF51A")

    channel = ChannelProfile(
        handle="@cult_information",
        display_name="Cult Information",
        niche="Informative AI & Tech",
        logo_filename="logo_cult_badge.png",
        subreddits=[],
        default_hashtags=[],
        cta_link=""
    )

    hook_text = "The most expensive AI chips in the world are now worth more than $10,000,000,000"
    highlight_word = "expensive AI chips"
    out_overlay = settings.OUTPUT_DIR / "test_cult_overlay.png"

    card_path = renderer.render_header_overlay(
        hook_text=hook_text,
        channel=channel,
        output_path=out_overlay,
        credit_handle="@techinsider",
        highlight_word=highlight_word,
        template=template
    )

    assert Path(card_path).exists()
    img = Image.open(card_path)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"

    # Top header (e.g. y=100) must be solid black (alpha=255, rgb near 0)
    pixel_top = img.getpixel((540, 100))
    assert pixel_top[3] == 255
    assert pixel_top[0] <= 10 and pixel_top[1] <= 10 and pixel_top[2] <= 10

    # Video area (y=800) must be transparent (alpha=0) in the card overlay so video shows through
    pixel_video_area = img.getpixel((540, 800))
    assert pixel_video_area[3] == 0

def test_video_compositor_cult_integration(tmp_path):
    """Verify build_reel composites a video with Cult Information header template."""
    compositor = VideoCompositor()
    channel = ChannelProfile(
        handle="@cult_information",
        display_name="Cult Information",
        niche="Informative AI & Tech",
        logo_filename="logo_cult_badge.png",
        subreddits=[],
        default_hashtags=[],
        cta_link=""
    )

    # Use existing candidate or fallback video
    candidates = [
        Path("storage/temp/raw_scraped_clip.mp4"),
        Path("output/benchmark_rendered_reel.mp4"),
        Path("output/cult_aesthetic_sample_reel.mp4")
    ]
    raw_video = next((p for p in candidates if p.exists()), None)
    if not raw_video:
        pytest.skip("No sample raw video available for full encode test")

    out_name = "test_cult_reel_rendered.mp4"
    rendered = compositor.build_reel(
        raw_video_path=str(raw_video),
        hook_text="Two people can experience the exact same thing and see completely different results",
        channel=channel,
        output_filename=out_name,
        account_index=0,
        apply_anti_shadowban=False,
        highlight_word="completely"
    )

    assert Path(rendered).exists()
    assert Path(rendered).stat().st_size > 50000

def test_fanout_and_db_highlight_word_persistence():
    """Verify that highlight_word is persisted in reels_tracker and accepted by Fanout."""
    init_octopus_db()
    test_reel_id = "test_cult_pipeline_001"
    insert_or_update_reel({
        "id": test_reel_id,
        "source_url": "https://instagram.com/reel/test_cult",
        "original_title": "AI Chip Revolution",
        "hook_text": "The most expensive AI chips in the world",
        "highlight_word": "expensive AI chips",
        "caption": "Full test breakdown",
        "status": "READY"
    })

    record = get_reel(test_reel_id)
    assert record is not None
    assert record["hook_text"] == "The most expensive AI chips in the world"
    assert record["highlight_word"] == "expensive AI chips"

    # Verify OctopusFanoutEngine signature accepts highlight_word
    fanout = OctopusFanoutEngine()
    import inspect
    sig = inspect.signature(fanout.generate_account_customized_reel)
    assert "highlight_word" in sig.parameters
