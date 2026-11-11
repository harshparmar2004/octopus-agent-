import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer
from processors.anti_shadowban import AntiShadowbanEngine

logger = logging.getLogger("Compositor")

class VideoCompositor:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.card_renderer = CardRenderer()

    def build_reel(
        self,
        raw_video_path: str,
        hook_text: str,
        channel: ChannelProfile,
        output_filename: str,
        credit_handle: Optional[str] = None,
        highlight_word: Optional[str] = None,
        account_index: int = 0,
        apply_anti_shadowban: bool = True
    ) -> Optional[str]:
        """
        Takes a raw video and composits it into a 9:16 Instagram Reel with:
        1. Pure black 1080x1920 background
        2. Uncover-style header card + hook headline + template logo
        3. Centered source video in lower portion
        4. Anti-shadowban perceptual mutation (color EQ, noise dithering, metadata stripping & device spoofing)
        """
        input_path = Path(raw_video_path)
        if not input_path.exists():
            logger.error(f"Input video not found: {raw_video_path}")
            return None

        output_path = self.output_dir / output_filename
        overlay_png = self.output_dir / f"temp_overlay_{input_path.stem}_{account_index}.png"

        try:
            # 1. Render the header, template logo & hook overlay PNG
            self.card_renderer.render_header_overlay(
                hook_text=hook_text,
                channel=channel,
                output_path=overlay_png,
                credit_handle=credit_handle,
                highlight_word=highlight_word
            )

            # 2. Run FFmpeg composition with anti-shadowban filters
            import platform

            # Dynamic encoder selection
            if platform.system() == "Darwin":
                vcodec_args = ["-c:v", "h264_videotoolbox", "-b:v", "6500k"]
            else:
                vcodec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "22"]

            if apply_anti_shadowban:
                mut_params = AntiShadowbanEngine.get_video_mutation_params(account_index)
                v_eq_filter = mut_params["video_filters"]
                metadata_args = mut_params["metadata_args"]
                filter_complex = (
                    f"[0:v]{v_eq_filter},"
                    f"scale=1080:1180:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2[scaled];"
                    f"color=c=black:s=1080x1920[bg];"
                    f"[bg][scaled]overlay=(W-w)/2:680+(1180-h)/2:shortest=1[with_vid];"
                    f"[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                )
            else:
                metadata_args = []
                filter_complex = (
                    "[0:v]scale=1080:1180:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2[scaled];"
                    "color=c=black:s=1080x1920[bg];"
                    "[bg][scaled]overlay=(W-w)/2:680+(1180-h)/2:shortest=1[with_vid];"
                    "[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                )

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
                "-movflags", "+faststart"
            ] + metadata_args + [
                str(output_path)
            ]

            logger.info(f"Running FFmpeg composition (Variant {account_index}): {output_filename}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return None

            logger.info(f"Successfully generated reel variant: {output_path}")
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
