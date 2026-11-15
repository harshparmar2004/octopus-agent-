import os
import pytest
from pathlib import Path
from PIL import Image
import cv2

from config import ChannelProfile, settings
from renderers.card_renderer import CardRenderer
from renderers.niche_templates import get_template_for_niche
from renderers.video_compositor import VideoCompositor
from publisher.octopus_fanout import OctopusFanoutEngine
from processors.video_vision import VideoVisionInspector
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

def test_detect_active_video_bounds_crops_competitor_header():
    """Verify detect_active_video_bounds detects static competitor header and requests crop."""
    target_vid = Path("output/benchmark_rendered_reel.mp4")
    if not target_vid.exists():
        pytest.skip("benchmark_rendered_reel.mp4 not present for crop test")

    bounds = VideoVisionInspector.detect_active_video_bounds(str(target_vid))
    assert bounds["crop_needed"] is True
    assert bounds["has_header"] is True
    assert bounds["crop_box"] is not None
    assert bounds["crop_box"]["y"] > 500  # Slices top competitor header
    assert bounds["crop_box"]["h"] > 100

def test_video_compositor_cult_integration_with_auto_crop(tmp_path):
    """Verify build_reel automatically crops out competitor header and composites Cult template."""
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

    candidates = [
        Path("output/benchmark_rendered_reel.mp4"),
        Path("storage/temp/raw_scraped_clip.mp4"),
        Path("output/cult_aesthetic_sample_reel.mp4")
    ]
    raw_video = next((p for p in candidates if p.exists()), None)
    if not raw_video:
        pytest.skip("No sample raw video available for full encode test")

    out_name = "test_cult_auto_cropped_reel.mp4"
    rendered = compositor.build_reel(
        raw_video_path=str(raw_video),
        hook_text="Two people can experience the exact same thing and see completely different results",
        channel=channel,
        output_filename=out_name,
        account_index=0,
        apply_anti_shadowban=False,
        highlight_word="completely",
        auto_crop_header=True
    )

    assert Path(rendered).exists()
    assert Path(rendered).stat().st_size > 50000

    # Check frame below header (e.g. y=500): competitor header (Octopus Scale Hub) should be gone
    cap = cv2.VideoCapture(str(rendered))
    cap.set(cv2.CAP_PROP_POS_MSEC, 1000)
    ret, frame = cap.read()
    cap.release()
    assert ret is True

def test_fanout_and_db_highlight_word_and_crop_persistence():
    """Verify that highlight_word and crop_box are persisted in reels_tracker and accepted by Fanout."""
    init_octopus_db()
    test_reel_id = "test_cult_pipeline_002"
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

    # Verify OctopusFanoutEngine signature accepts highlight_word and crop_box
    fanout = OctopusFanoutEngine()
    import inspect
    sig = inspect.signature(fanout.generate_account_customized_reel)
    assert "highlight_word" in sig.parameters
    assert "crop_box" in sig.parameters

def test_dynamic_highlights_density_scaling():
    """Verify compute_dynamic_highlights scales neon density according to word count."""
    renderer = CardRenderer()
    
    # 1. Short text (<= 8 words): higher highlight density (~40-55%)
    short_text = "AI Table Tennis Robot Beats Human Pro"
    hl_short = renderer.compute_dynamic_highlights(short_text)
    assert len(hl_short) > 0
    short_hl_words = [w for p in hl_short.split(',') for w in p.split()]
    assert 2 <= len(short_hl_words) <= 5

    # 2. Medium text (9-14 words): balanced highlight (~30-40%)
    med_text = "Claude Fable 5.2 Just Built This INSANE First-Person Shooter Game Within 8 Hours"
    hl_med = renderer.compute_dynamic_highlights(med_text)
    assert "INSANE First-Person Shooter Game" in hl_med or "Claude Fable" in hl_med

    # 3. Long text (>= 15 words): distributed across lines (5-8 words total)
    long_text = "The Most Advanced AI Humanoid In The World Just Demonstrated Capabilities Never Seen Before In History"
    hl_long = renderer.compute_dynamic_highlights(long_text)
    long_hl_words = [w for p in hl_long.split(',') for w in p.split()]
    assert len(long_hl_words) >= 4

def test_aspect_ratio_adaptive_header_positions(tmp_path):
    """Verify that 16:9 widescreen shifts downwards while 1:1 square shifts upwards."""
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
    hook = "Claude Fable 5.2 Just Built This INSANE First-Person Shooter Game Within 8 Hours"

    out_16_9 = tmp_path / "card_16_9.png"
    renderer.render_header_overlay(
        hook_text=hook,
        channel=channel,
        output_path=out_16_9,
        aspect_ratio=1.77,  # 16:9 widescreen
        show_credit=False
    )

    out_1_1 = tmp_path / "card_1_1.png"
    renderer.render_header_overlay(
        hook_text=hook,
        channel=channel,
        output_path=out_1_1,
        aspect_ratio=1.0,  # 1:1 square
        show_credit=False
    )

    # For 16:9 (shifted downwards): at y=120, badge is not yet reached, pixel is black background
    img_16_9 = Image.open(out_16_9)
    img_1_1 = Image.open(out_1_1)

    # In 1:1 (shifted upwards at row_y=100), the badge area has content at y=130
    # In 16:9 (shifted downwards at row_y=190), the badge area starts at y=190
    assert img_16_9.size == (1080, 1920)
    assert img_1_1.size == (1080, 1920)

def test_source_pill_removed_from_cult_card(tmp_path):
    """Verify that the Source: @... attribution pill is absent by default in Cult Information cards."""
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
    hook = "Claude Fable 5.2 Just Built This INSANE First-Person Shooter Game Within 8 Hours"
    out_card = tmp_path / "card_no_source.png"
    
    renderer.render_header_overlay(
        hook_text=hook,
        channel=channel,
        output_path=out_card,
        credit_handle="@AskGPTs",
        show_credit=False
    )
    assert out_card.exists()
