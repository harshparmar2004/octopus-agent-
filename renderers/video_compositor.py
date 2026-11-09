import os
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer

logger = logging.getLogger("Compositor")

class VideoCompositor:
    """
    Adaptive Dynamic Aspect Ratio Video Compositor:
    - Automatically probes source video geometry (16:9, 1:1, 4:5, 9:16).
    - Solves vertical layout dynamically to keep video centered between the header text zone
      and bottom Instagram engagement area.
    - Uses Apple Silicon VideoToolbox (Mac) or libx264 (Windows/Linux).
    """
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.card_renderer = CardRenderer()

    def probe_video_dimensions(self, video_path: str) -> Tuple[int, int]:
        """Probes native video stream width and height using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                str(video_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode == 0 and "x" in res.stdout:
                parts = res.stdout.strip().split("x")
                return int(parts[0]), int(parts[1])
        except Exception as e:
            logger.debug(f"ffprobe geometry probe error: {e}")
        # Default fallback to 16:9 landscape
        return 1280, 720

    def build_reel(
        self,
        raw_video_path: str,
        hook_text: str,
        channel: ChannelProfile,
        output_filename: str,
        credit_handle: Optional[str] = None,
        highlight_word: Optional[str] = None
    ) -> Optional[str]:
        """
        Composites raw video into a pixel-perfect 1080x1920 Instagram Reel:
        1. Pure pitch-black background
        2. Cult-style header card + verified badge + dual-tone headline
        3. Dynamically centered source video matching native aspect ratio
        """
        input_path = Path(raw_video_path)
        if not input_path.exists():
            logger.error(f"Input video not found: {raw_video_path}")
            return None

        output_path = self.output_dir / output_filename
        overlay_png = self.output_dir / f"temp_overlay_{input_path.stem}.png"

        try:
            # 1. Render the header overlay and obtain exact text block bottom Y
            card_meta = self.card_renderer.render_header_overlay(
                hook_text=hook_text,
                channel=channel,
                output_path=overlay_png,
                credit_handle=credit_handle,
                highlight_word=highlight_word
            )
            text_bottom_y = card_meta.get("text_bottom_y", 520)

            # 2. Probe native source video geometry
            native_w, native_h = self.probe_video_dimensions(str(input_path))
            aspect_ratio = native_w / max(1, native_h)
            logger.info(f"Source video dimensions: {native_w}x{native_h} (AR: {aspect_ratio:.2f})")

            # 3. Dynamic Safe-Zone Layout Calculation
            # Safe top: below the text block with breathing room
            safe_top = max(480, text_bottom_y + 30)
            # Safe bottom: above Instagram engagement overlay (heart, comment, audio, caption)
            safe_bottom = 1600
            available_height = safe_bottom - safe_top

            if aspect_ratio >= 1.3:
                # Landscape / Horizontal video (e.g. 16:9 widescreen interview/podcast)
                target_w = 1080
                target_h = int(target_w / aspect_ratio)
                # Ensure even dimensions
                target_h = (target_h // 2) * 2
                # Center vertically within the viewing window
                center_y = safe_top + int((available_height - target_h) / 2)
                
                filter_complex = (
                    f"[0:v]scale=1080:{target_h}[scaled];"
                    f"color=c=black:s=1080x1920[bg];"
                    f"[bg][scaled]overlay=0:{center_y}:shortest=1[with_vid];"
                    f"[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                )
            else:
                # Square (1:1) or Vertical (4:5 / 9:16) video
                filter_complex = (
                    f"[0:v]scale=1080:{available_height}:force_original_aspect_ratio=decrease,"
                    f"pad=ceil(iw/2)*2:ceil(ih/2)*2[scaled];"
                    f"color=c=black:s=1080x1920[bg];"
                    f"[bg][scaled]overlay=(W-w)/2:{safe_top}+({available_height}-h)/2:shortest=1[with_vid];"
                    f"[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                )

            # 4. Encoder selection (VideoToolbox on macOS Apple Silicon, libx264 on Windows/Linux)
            if platform.system() == "Darwin":
                vcodec_args = ["-c:v", "h264_videotoolbox", "-b:v", "6500k"]
            else:
                vcodec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "22"]

            # 5. Build and execute FFmpeg composition
            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-loop", "1", "-i", str(overlay_png),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "0:a?"
            ] + vcodec_args + [
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_path)
            ]

            logger.info(f"Running adaptive layout composition: {output_filename}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg composition error: {result.stderr}")
                return None

            logger.info(f"Successfully generated reel: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"Error during video composition: {e}")
            return None
        finally:
            if overlay_png.exists():
                try:
                    overlay_png.unlink()
                except Exception:
                    pass
