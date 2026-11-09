import os
import sys
import subprocess
from pathlib import Path

# Force UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer
from renderers.video_compositor import VideoCompositor

def test_cult_aesthetic_render():
    print("=" * 70)
    print("[TEST] RENDERING CULT AESTHETIC REEL (EXACT MATCH TO REFERENCE SCREENSHOT)")
    print("=" * 70)

    # 1. Setup channel profile for 'Octopus Information'
    channel = ChannelProfile(
        handle="@octopus_information",
        display_name="Octopus Information",
        niche="Curated Facts & High-Retention Knowledge",
        logo_filename="master_network_badge.png",
        subreddits=[], default_hashtags=[], cta_link="bit.ly/newsletter"
    )

    # 2. Exact hook text matching user reference
    hook_text = "Two people can earn the exact same salary and end up living completely different lives"
    highlight_word = "completely"

    sample_video = Path(settings.STORAGE_DIR) / "test_sample.mp4"
    output_filename = "cult_aesthetic_sample_reel.mp4"
    output_path = Path(settings.OUTPUT_DIR) / output_filename

    compositor = VideoCompositor()

    print(f"1. Source Video: {sample_video}")
    print(f"2. Page Title:   {channel.display_name}")
    print(f"3. Handle:       {channel.handle}")
    print(f"4. Headline:     \"{hook_text}\"")
    print(f"5. Highlight:    [{highlight_word}] in Neon Yellow (#DDF51A)")

    rendered = compositor.build_reel(
        raw_video_path=str(sample_video),
        hook_text=hook_text,
        channel=channel,
        output_filename=output_filename,
        credit_handle="@cult_information",
        highlight_word=highlight_word
    )

    if not rendered or not Path(rendered).exists():
        print("[FAIL] Video rendering failed!")
        return False

    print(f"\n[PASS] Successfully generated reel: {rendered}")
    size_mb = Path(rendered).stat().st_size / (1024 * 1024)
    print(f"   -> File Size: {size_mb:.2f} MB")

    # Extract screenshot frame at t=1.0s to artifact directory for visual inspection
    frame_artifact_path = Path(r"C:\Users\harsh parmar\.gemini\antigravity\brain\774a7df9-ab5a-4865-8ba5-a42753b13222") / "rendered_cult_aesthetic_frame.png"
    extract_cmd = [
        "ffmpeg", "-y",
        "-ss", "00:00:01",
        "-i", str(rendered),
        "-vframes", "1",
        "-q:v", "2",
        str(frame_artifact_path)
    ]
    subprocess.run(extract_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if frame_artifact_path.exists():
        print(f"[PASS] Extracted preview frame: {frame_artifact_path}")
    else:
        print("[WARN] Could not extract preview frame.")

    print("\n[OK] Test completed successfully!")
    return True

if __name__ == "__main__":
    test_cult_aesthetic_render()
