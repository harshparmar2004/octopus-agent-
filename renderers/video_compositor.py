import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer
from renderers.niche_templates import NicheTemplate, get_template_for_niche, get_template_by_id
from processors.anti_shadowban import AntiShadowbanEngine
from processors.video_vision import VideoVisionInspector

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
        apply_anti_shadowban: bool = True,
        template: Optional[NicheTemplate] = None,
        template_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Takes a raw video and composits it into a 9:16 Instagram Reel:
        - For 'full_screen_neon_hud': Uses an aspect-ratio adaptive container box (fits 1:1, 9:16, 16:9),
          renders outer diffuse pink glow shadow outside the box, places brand name strictly on top,
          and uses computer vision to avoid collisions with baked-in text.
        - For 'top_card_cult': Uses classic informational top card letterbox.
        - Applies anti-shadowban perceptual mutation and spoofed mobile metadata.
        """
        input_path = Path(raw_video_path)
        if not input_path.exists():
            logger.error(f"Input video not found: {raw_video_path}")
            return None

        output_path = self.output_dir / output_filename
        overlay_png = self.output_dir / f"temp_overlay_{input_path.stem}_{account_index}.png"
        bg_png = self.output_dir / f"temp_bg_{input_path.stem}_{account_index}.png"
        fg_png = self.output_dir / f"temp_fg_{input_path.stem}_{account_index}.png"

        try:
            # 0. Resolve Niche Template
            if template is None:
                if template_id:
                    template = get_template_by_id(template_id)
                if template is None:
                    niche_val = getattr(channel, "niche", "information") or "information"
                    template = get_template_for_niche(niche_val)

            layout = getattr(template, "overlay_layout", "top_card_cult")

            import platform
            if platform.system() == "Darwin":
                vcodec_args = ["-c:v", "h264_videotoolbox", "-b:v", "6500k"]
            else:
                vcodec_args = ["-c:v", "libx264", "-preset", "fast", "-crf", "22"]

            if layout == "full_screen_neon_hud":
                # 1. Computer Vision Inspection for dimensions & baked-in text
                vision = VideoVisionInspector.analyze(str(input_path))
                vid_w = vision.get("width", 720)
                vid_h = vision.get("height", 1280)
                placement = vision.get("recommended_placement", "bottom")

                # 2. Geometric Aspect-Ratio Adaptive Box Fitting (1:1, 9:16, 16:9)
                y_top_limit = 210
                y_bot_limit = 1750
                max_w = 960
                max_h = y_bot_limit - y_top_limit

                scale = min(max_w / vid_w, max_h / vid_h)
                box_w = (int(vid_w * scale) // 2) * 2
                box_h = (int(vid_h * scale) // 2) * 2
                box_x = ((1080 - box_w) // 4) * 2
                box_y = ((y_top_limit + (max_h - box_h) // 2) // 2) * 2
                box_coords = (box_x, box_y, box_w, box_h)

                # 3. Render 3-Layer Container (Outer Pink Glow Shadow + Foreground HUD)
                self.card_renderer.render_adaptive_box_layers(
                    box_coords=box_coords,
                    channel=channel,
                    hook_text=hook_text,
                    hook_placement=placement,
                    template=template,
                    bg_output_path=bg_png,
                    fg_output_path=fg_png
                )

                # 4. FFmpeg 3-Layer Composition
                if apply_anti_shadowban:
                    mut_params = AntiShadowbanEngine.get_video_mutation_params(account_index)
                    v_eq_filter = mut_params["video_filters"]
                    metadata_args = mut_params["metadata_args"]
                    filter_complex = (
                        f"[1:v]{v_eq_filter},scale={box_w}:{box_h}[vid];"
                        f"[0:v][vid]overlay={box_x}:{box_y}:shortest=1[with_vid];"
                        f"[with_vid][2:v]overlay=0:0:shortest=1[outv]"
                    )
                else:
                    metadata_args = []
                    filter_complex = (
                        f"[1:v]scale={box_w}:{box_h}[vid];"
                        f"[0:v][vid]overlay={box_x}:{box_y}:shortest=1[with_vid];"
                        f"[with_vid][2:v]overlay=0:0:shortest=1[outv]"
                    )

                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(bg_png),
                    "-i", str(input_path),
                    "-loop", "1", "-i", str(fg_png),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]",
                    "-map", "1:a?",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                    "-movflags", "+faststart"
                ] + vcodec_args + metadata_args + [str(output_path)]

            else:
                # Classic Informative Top Card layout
                self.card_renderer.render_header_overlay(
                    hook_text=hook_text,
                    channel=channel,
                    output_path=overlay_png,
                    credit_handle=credit_handle,
                    highlight_word=highlight_word,
                    template=template
                )

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
            for p in [overlay_png, bg_png, fg_png]:
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
