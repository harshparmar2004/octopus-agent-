import pytest
import subprocess
from pathlib import Path
from PIL import Image

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer
from renderers.video_compositor import VideoCompositor
from processors.ai_enricher import AIEnricher
from publisher.octopus_fanout import OctopusFanoutEngine

def test_01_card_renderer_viral_floating_hook(tmp_path):
    renderer = CardRenderer()
    overlay_path = tmp_path / "test_overlay.png"
    channel = ChannelProfile(
        handle="@cute.aarohi.007",
        display_name="Cute Aarohi",
        niche="Girls' Dance & Parties",
        logo_filename="logo_cute_aarohi_007.png",
        subreddits=[],
        default_hashtags=[],
        cta_link=""
    )
    res = renderer.render_viral_floating_hook(
        hook_text="Wait for her expressions at the drop ✨",
        channel=channel,
        output_path=overlay_path
    )
    assert overlay_path.exists()
    img = Image.open(overlay_path)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"
    print("[PASS] render_viral_floating_hook generated 1080x1920 transparent overlay")

def test_02_build_viral_dance_reel_with_metadata(tmp_path):
    # 1. Create a 1-second synthetic video
    raw_video = tmp_path / "raw_input.mp4"
    cmd_synth = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=720x1280:rate=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264", "-c:a", "aac", "-t", "1", "-shortest",
        str(raw_video)
    ]
    subprocess.run(cmd_synth, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    assert raw_video.exists()

    # 2. Render through VideoCompositor.build_viral_dance_reel
    compositor = VideoCompositor(output_dir=tmp_path)
    channel = ChannelProfile(
        handle="@cute.aarohi.007",
        display_name="Cute Aarohi",
        niche="Girls' Dance & Parties",
        logo_filename="logo_cute_aarohi_007.png",
        subreddits=[],
        default_hashtags=[],
        cta_link=""
    )
    out_file = "viral_output.mp4"
    rendered_path = compositor.build_viral_dance_reel(
        raw_video_path=str(raw_video),
        hook_text="Wait for the drop ✨",
        channel=channel,
        output_filename=out_file
    )
    assert rendered_path is not None
    rendered = Path(rendered_path)
    assert rendered.exists()
    assert rendered.stat().st_size > 0

    # 3. Verify Apple iPhone 15 Pro Max metadata was injected
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format_tags=comment",
        "-of", "default=noprint_wrappers=1", str(rendered)
    ]
    probe_out = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
    assert "iPhone 15 Pro Max" in probe_out
    print("[PASS] build_viral_dance_reel successfully injected Apple iPhone metadata")

def test_03_ai_enricher_dance_viral_package():
    enricher = AIEnricher()
    package = enricher.generate_dance_viral_package(
        title="Epic sangeet choreo",
        description="Dancing to trending bollywood track with lehenga twirl #dance",
        channel_handle="@cute.aarohi.007",
        creator_credit="@dancer_girl"
    )
    assert "hook_text" in package
    assert len(package["hook_text"]) > 3
    assert "full_caption" in package
    assert "Dancing: @dancer_girl" in package["full_caption"]
    assert "#" in package["full_caption"]
    assert "👉 Follow" not in package["full_caption"]  # Zero spam verified
    print("[PASS] generate_dance_viral_package generated authentic non-spam caption:", package["full_caption"])

def test_04_fanout_integration_viral_dance(tmp_path):
    fanout = OctopusFanoutEngine()
    fanout.compositor.output_dir = tmp_path
    
    # Create sample video
    raw_video = tmp_path / "raw_dance.mp4"
    cmd_synth = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=720x1280:rate=30",
        "-c:v", "libx264", "-t", "1",
        str(raw_video)
    ]
    subprocess.run(cmd_synth, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    acc = {
        "id": "cute_aarohi_007",
        "handle": "@cute.aarohi.007",
        "display_name": "Cute Aarohi",
        "niche": "Girls' Dance & Parties",
        "niche_id": "girls_dance"
    }

    out_path = fanout.generate_account_customized_reel(
        raw_video_path=str(raw_video),
        hook_text="Can we talk about this twirl? 🤌",
        account=acc,
        task_id="test_viral_task",
        account_index=0
    )
    assert Path(out_path).exists()
    # Ensure it's not simply a raw identical file copy
    assert Path(out_path).stat().st_size != raw_video.stat().st_size
    print("[PASS] Fanout successfully applied viral transformation instead of raw copy")
