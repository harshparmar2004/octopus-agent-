import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from processors.vision_extractor import VisionExtractor
from renderers.video_compositor import VideoCompositor
from server import app

client = TestClient(app)
SAMPLE_VIDEO = "storage/reel_Dffuae7ub5N.mp4"


def test_extract_representative_frames(tmp_path):
    assert Path(SAMPLE_VIDEO).exists(), f"Sample video {SAMPLE_VIDEO} must exist."
    frames = VisionExtractor.extract_representative_frames(SAMPLE_VIDEO, count=3, output_dir=tmp_path)
    assert len(frames) == 3
    for fp in frames:
        assert Path(fp).exists()
        assert Path(fp).stat().st_size > 1000


def test_analyze_fallback_heuristic():
    res = VisionExtractor.analyze_fallback(SAMPLE_VIDEO, [])
    assert res["success"] is True
    assert res["engine"] == "local_vision_heuristic"
    assert "headline" in res and len(res["headline"]) > 5
    assert "highlight_word" in res
    assert res["detected_niche"] in ["ai_tech", "clubbing", "memes", "concerts"]


@patch("requests.post")
def test_gemini_vision_mock_response(mock_post, tmp_path):
    # Create fake frames
    dummy_frame = tmp_path / "frame1.jpg"
    dummy_frame.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    fake_json_content = json.dumps({
        "exact_text": "Weekend party vibes with the girls squad",
        "headline": "Weekend party vibes with the girls squad",
        "highlight_word": "girls squad",
        "context": "Girls dance group celebrating at a party",
        "detected_niche": "clubbing",
        "suggested_caption": "Party mode fully activated tonight! Save this for weekend inspiration.",
        "has_baked_in_text": True,
        "confidence": 0.98
    })

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{"text": fake_json_content}]
            }
        }]
    }
    mock_post.return_value = mock_resp

    result = VisionExtractor.analyze_with_gemini([str(dummy_frame)], api_key="dummy_gemini_key")
    assert result["success"] is True
    assert result["engine"] == "gemini_vision"
    assert result["exact_text"] == "Weekend party vibes with the girls squad"
    assert result["highlight_word"] == "girls squad"
    assert result["detected_niche"] == "clubbing"
    assert result["target_template_id"] == "clubbing_branded"


def test_compositor_reskin_informative_tech():
    comp = VideoCompositor()
    res = comp.reskin_reel(
        raw_video_path=SAMPLE_VIDEO,
        headline="Two people can earn the exact same salary and live completely different lives",
        highlight_word="completely different",
        niche_id="ai_tech",
        account_id="info_01",
        output_filename="test_ci_informative_reskin.mp4"
    )
    assert res["success"] is True
    out_path = Path(res["rendered_video_path"])
    assert out_path.exists()
    assert out_path.stat().st_size > 500_000
    assert res["preview_frame_path"] is not None
    assert Path(res["preview_frame_path"]).exists()
    assert res["render_profile"] == "light_template"


def test_compositor_reskin_clubbing_neon():
    comp = VideoCompositor()
    res = comp.reskin_reel(
        raw_video_path=SAMPLE_VIDEO,
        headline="Electric night vibe when the bass drops in the club",
        highlight_word="bass drops",
        niche_id="clubbing",
        account_id="cute_aarohi_007",
        output_filename="test_ci_clubbing_reskin.mp4"
    )
    assert res["success"] is True
    out_path = Path(res["rendered_video_path"])
    assert out_path.exists()
    assert out_path.stat().st_size > 500_000
    assert res["preview_frame_path"] is not None
    assert Path(res["preview_frame_path"]).exists()


def test_server_vision_read_api():
    resp = client.post("/api/vision/read-reel", json={"video_path": SAMPLE_VIDEO})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "analysis" in data
    assert len(data["analysis"]["frame_thumbnails"]) == 3


def test_server_vision_reskin_api():
    payload = {
        "video_path_or_url": SAMPLE_VIDEO,
        "headline": "Testing the AI Vision automated re-skinner engine",
        "highlight_word": "automated",
        "niche_id": "ai_tech",
        "account_id": "info_01",
        "auto_publish": False
    }
    resp = client.post("/api/vision/reskin-reel", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["reskin"]["success"] is True
    assert data["reskin"]["rendered_video_url"].startswith("/output/")
