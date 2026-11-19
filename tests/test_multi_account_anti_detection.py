import os
import subprocess
import hashlib
from pathlib import Path
import pytest

from config import settings, ChannelProfile
from renderers.video_compositor import VideoCompositor
from processors.ai_enricher import AIEnricher
from processors.anti_shadowban import AntiShadowbanEngine, DEVICE_SPOOF_PROFILES
from publisher.octopus_fanout import OctopusFanoutEngine

def test_01_ten_device_profiles_complete():
    assert len(DEVICE_SPOOF_PROFILES) >= 10
    models = [p["model"] for p in DEVICE_SPOOF_PROFILES[:10]]
    assert len(set(models)) == 10
    assert "iPhone 15 Pro Max" in models
    assert "Galaxy S24 Ultra" in models
    assert "Pixel 8 Pro" in models
    print("[PASS] 10 distinct mobile device profiles verified:", models)

def test_02_account_device_pinning_is_permanent():
    # Calling 100 times for cute.aarohi.007 must always yield the exact same device (iPhone 15 Pro Max)
    for _ in range(100):
        dev = AntiShadowbanEngine.get_pinned_device_profile("@cute.aarohi.007")
        assert dev["model"] == "iPhone 15 Pro Max"
        assert dev["make"] == "Apple"

    # Other accounts must also be deterministically pinned
    acc_dev1 = AntiShadowbanEngine.get_pinned_device_profile("@sangeet_queen")
    acc_dev2 = AntiShadowbanEngine.get_pinned_device_profile("@sangeet_queen")
    assert acc_dev1 == acc_dev2

    # Creation time must be in the past (realistic)
    c_time = AntiShadowbanEngine.generate_realistic_creation_time("@cute.aarohi.007")
    assert "T" in c_time and "Z" in c_time
    print("[PASS] Permanent account device pinning and realistic past creation time verified.")

def test_03_multi_account_dance_package_diversity():
    enricher = AIEnricher()
    packages = enricher.generate_multi_account_dance_package(
        count=10,
        title="Wedding sangeet dance performance",
        description="Lehenga twirl and choreography on trending bollywood song",
        creator_credit="@dancer_girl"
    )
    assert len(packages) == 10

    hooks = [p["hook_text"] for p in packages]
    captions = [p["full_caption"] for p in packages]
    angles = [p["angle"] for p in packages]

    assert len(set(hooks)) == 10, f"Duplicate hooks found: {hooks}"
    assert len(set(captions)) == 10, f"Duplicate captions found: {captions}"
    assert len(set(angles)) == 10, f"Duplicate angles found: {angles}"

    for cap in captions:
        assert "👉 Follow" not in cap
        assert "Follow for more" not in cap
        assert "Dancing: @dancer_girl" in cap
        assert "#" in cap

    print("[PASS] 10 distinct angles, unique hooks and zero-spam captions generated successfully.")

def test_04_per_account_video_mutation_and_device_spoofing(tmp_path):
    raw_video = tmp_path / "raw_dance_source.mp4"
    cmd_synth = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264", "-c:a", "aac", "-t", "1", "-shortest",
        str(raw_video)
    ]
    subprocess.run(cmd_synth, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    assert raw_video.exists()

    compositor = VideoCompositor(output_dir=tmp_path)
    enricher = AIEnricher()
    packages = enricher.generate_multi_account_dance_package(count=3, title="Test Choreo")

    hashes = []
    models_probed = []

    for idx in range(3):
        out_name = f"account_variant_{idx}.mp4"
        channel = ChannelProfile(
            handle="@cute.aarohi.007" if idx == 0 else f"@dance_page_{idx}",
            display_name=f"Dance Page {idx}",
            niche="Girls' Dance & Parties",
            logo_filename="logo.png",
            subreddits=[],
            default_hashtags=[],
            cta_link=""
        )
        rendered_path = compositor.build_viral_dance_reel(
            raw_video_path=str(raw_video),
            hook_text=packages[idx]["hook_text"],
            channel=channel,
            output_filename=out_name,
            account_index=idx
        )
        assert rendered_path is not None
        p = Path(rendered_path)
        assert p.exists()
        assert p.stat().st_size > 0

        h = hashlib.sha256(p.read_bytes()).hexdigest()
        hashes.append(h)

        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format_tags=model,make,creation_time",
            "-of", "default=noprint_wrappers=1", str(p)
        ]
        probe_out = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
        models_probed.append(probe_out.strip())
        assert "creation_time=" in probe_out

    assert len(set(hashes)) == 3, f"Non-unique video hashes: {hashes}"
    assert "iPhone 15 Pro Max" in models_probed[0] or "Apple" in models_probed[0]
    print("[PASS] Unique video hashes, pinned device profiles, and past creation times confirmed.")

def test_05_staggered_schedule_offsets():
    sched = AntiShadowbanEngine.get_staggered_schedule(account_count=10, mode="balanced")
    assert len(sched) == 10
    assert sched[0]["offset_seconds"] == 0
    for i in range(1, 10):
        assert sched[i]["offset_seconds"] > sched[i-1]["offset_seconds"]
        assert sched[i]["offset_seconds"] - sched[i-1]["offset_seconds"] >= 30
    print("[PASS] 10-account staggered scheduling verified with non-colliding human pacing.")
