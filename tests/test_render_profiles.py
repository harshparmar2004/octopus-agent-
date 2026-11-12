import os
import subprocess
from pathlib import Path
import pytest
from config import ChannelProfile
from renderers.card_renderer import CardRenderer
from renderers.niche_templates import get_template_for_niche, get_template_by_id
from renderers.video_compositor import VideoCompositor

@pytest.fixture
def sample_video(tmp_path):
    video_path = tmp_path / "test_input.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=1",
        "-pix_fmt", "yuv420p", str(video_path)
    ], check=True, capture_output=True)
    return str(video_path)

@pytest.fixture
def test_channel():
    return ChannelProfile(
        handle="@test.channel.007",
        display_name="Test Channel",
        niche="ai_tech",
        logo_filename="logo.png",
        subreddits=[],
        default_hashtags=[],
        cta_link="bit.ly/test"
    )

def test_01_core_niche_template_resolution():
    """Verifies that all 6 core niches resolve to their respective tailored templates."""
    # 1. AI content (raw video, no template)
    t_ai = get_template_for_niche("ai_content")
    assert t_ai.id == "ai_showcase"
    assert t_ai.render_profile == "raw_full_bleed"

    # 2. Memes (top caption bar)
    t_meme = get_template_for_niche("memes")
    assert t_meme.id == "meme_native"
    assert t_meme.render_profile == "meme_native"

    # 3. Concerts (logo only)
    t_concert = get_template_for_niche("concerts")
    assert t_concert.id == "concert_tag"
    assert t_concert.render_profile == "logo_only"

    # 4. Girls dance (raw video, no template)
    t_girls = get_template_for_niche("girls_dance")
    assert t_girls.id == "girls_raw"
    assert t_girls.render_profile == "raw_full_bleed"

    # 5. Clubbing (end-to-end neon template)
    t_club = get_template_for_niche("clubbing")
    assert t_club.id == "clubbing_branded"
    assert t_club.render_profile == "full_template"
    assert t_club.overlay_layout == "full_screen_neon_hud"

    # 6. Informative AI tech (light template: logo + hook + center video)
    t_tech = get_template_for_niche("ai_tech")
    assert t_tech.id == "informative_cult"
    assert t_tech.render_profile == "light_template"
    assert t_tech.overlay_layout == "top_card_cult"

def test_02_meme_native_rendering(tmp_path, test_channel, sample_video):
    """Verifies that the meme native profile renders with a white top caption bar."""
    compositor = VideoCompositor(output_dir=tmp_path)
    t_meme = get_template_by_id("meme_native")
    out = compositor.build_reel(
        raw_video_path=sample_video,
        hook_text="when the wifi drops for 2 seconds during the zoom meeting",
        channel=test_channel,
        output_filename="test_meme.mp4",
        template=t_meme
    )
    assert out is not None
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000

def test_03_concert_logo_only_rendering(tmp_path, test_channel, sample_video):
    """Verifies that the concerts profile renders full-screen with logo only (no frames/lower-thirds)."""
    compositor = VideoCompositor(output_dir=tmp_path)
    t_concert = get_template_by_id("concert_tag")
    out = compositor.build_reel(
        raw_video_path=sample_video,
        hook_text="",
        channel=test_channel,
        output_filename="test_concert.mp4",
        template=t_concert
    )
    assert out is not None
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000

def test_04_ai_content_raw_rendering(tmp_path, test_channel, sample_video):
    """Verifies that the AI content profile renders 100% raw video without templates or framework."""
    compositor = VideoCompositor(output_dir=tmp_path)
    t_ai = get_template_by_id("ai_showcase")
    out = compositor.build_reel(
        raw_video_path=sample_video,
        hook_text="",
        channel=test_channel,
        output_filename="test_ai_raw.mp4",
        template=t_ai
    )
    assert out is not None
    assert Path(out).exists()
    assert Path(out).stat().st_size > 1000

def test_05_informative_light_template_rendering(tmp_path, test_channel, sample_video):
    """Verifies that Informative AI tech renders the light template with top logo + hook."""
    compositor = VideoCompositor(output_dir=tmp_path)
    t_tech = get_template_by_id("informative_cult")
    out = compositor.build_reel(
        raw_video_path=sample_video,
        hook_text="Two people can earn the exact same salary and end up living completely different lives",
        highlight_word="completely",
        channel=test_channel,
        output_filename="test_tech_light.mp4",
        template=t_tech
    )
    assert out is not None
    assert Path(out).exists()
    assert Path(out).stat().st_size > 5000
