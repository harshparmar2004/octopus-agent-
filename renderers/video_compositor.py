import uuid
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer
from renderers.niche_templates import NicheTemplate, get_template_for_niche, get_template_by_id
from processors.video_vision import VideoVisionInspector

logger = logging.getLogger("Compositor")

CANVAS_W, CANVAS_H = 1080, 1920
# Sources whose aspect ratio is within this band are treated as native 9:16 and
# cover-cropped edge-to-edge; anything else gets a blurred fill behind the fitted video.
NATIVE_VERTICAL_AR = (0.50, 0.62)


def _probe_dims(path: str) -> Tuple[int, int]:
    """Returns (width, height) of a video, falling back to 1080x1920."""
    try:
        import cv2
        cap = cv2.VideoCapture(path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20,
        ).stdout.strip()
        w, h = (int(x) for x in out.split("x")[:2])
        return w, h
    except Exception:
        return CANVAS_W, CANVAS_H


def _even(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


class VideoCompositor:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.card_renderer = CardRenderer()

    @staticmethod
    def _vcodec_args():
        if platform.system() == "Darwin":
            return ["-c:v", "h264_videotoolbox", "-b:v", "6500k"]
        return ["-c:v", "libx264", "-preset", "fast", "-crf", "22"]

    @staticmethod
    def full_bleed_filter(vid_w: int, vid_h: int, src: str = "0:v", out: str = "base") -> str:
        """FFmpeg filter that turns any aspect ratio into a 1080x1920 full-screen base layer."""
        ar = vid_w / max(1, vid_h)
        if NATIVE_VERTICAL_AR[0] <= ar <= NATIVE_VERTICAL_AR[1]:
            return (
                f"[{src}]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
                f"crop={CANVAS_W}:{CANVAS_H},setsar=1[{out}]"
            )
        return (
            f"[{src}]split=2[fb_a][fb_b];"
            f"[fb_a]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
            f"crop={CANVAS_W}:{CANVAS_H},boxblur=24:2,eq=brightness=-0.08[fb_bg];"
            f"[fb_b]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,setsar=1[fb_fg];"
            f"[fb_bg][fb_fg]overlay=(W-w)/2:(H-h)/2[{out}]"
        )

    @staticmethod
    def meme_geometry(vid_w: int, vid_h: int, bar_h: int) -> Tuple[int, int, int, int]:
        """Returns (video_w, video_h, bar_y, video_y) for a centred caption-bar + video stack."""
        vw = CANVAS_W
        vh = _even(CANVAS_W * vid_h / max(1, vid_w))
        if bar_h + vh > CANVAS_H:
            vh = _even(CANVAS_H - bar_h)
            vw = _even(vh * vid_w / max(1, vid_h))
        total = bar_h + vh
        bar_y = max(0, (CANVAS_H - total) // 2)
        return vw, vh, bar_y, bar_y + bar_h

    def build_reel(
        self,
        raw_video_path: str,
        hook_text: str,
        channel: ChannelProfile,
        output_filename: str,
        credit_handle: Optional[str] = None,
        highlight_word: Optional[str] = None,
        account_index: int = 0,
        apply_anti_shadowban: bool = False,  # Deprecated: ignored (no media mutation / metadata spoofing)
        template: Optional[NicheTemplate] = None,
        template_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Composites a raw video into a 1080x1920 Reel according to the niche's render profile:
        - 'full_template' + layout 'full_screen_neon_hud' : aspect-adaptive neon frame (clubbing brand)
        - 'full_template' (other layouts)                  : editorial top card (informative tech)
        - 'light_brand'                                     : full-bleed + corner handle + optional short hook
        - 'concert_tag'                                     : full-bleed + lower-third artist/city/venue + filmer credit
        - 'raw_watermark'                                   : full-bleed raw video + micro watermark
        - 'meme_native'                                     : white caption bar above the video
        """
        input_path = Path(raw_video_path)
        if not input_path.exists():
            logger.error(f"Input video not found: {raw_video_path}")
            return None

        output_path = self.output_dir / output_filename
        stem = f"{input_path.stem}_{account_index}"
        overlay_png = self.output_dir / f"temp_overlay_{stem}.png"
        bg_png = self.output_dir / f"temp_bg_{stem}.png"
        fg_png = self.output_dir / f"temp_fg_{stem}.png"

        try:
            if template is None:
                if template_id:
                    template = get_template_by_id(template_id)
                if template is None:
                    niche_val = getattr(channel, "niche", "information") or "information"
                    template = get_template_for_niche(niche_val)

            profile = getattr(template, "render_profile", "full_template")
            layout = getattr(template, "overlay_layout", "top_card_cult")
            audio_args = ["-c:a", "aac", "-b:a", "192k"]
            common_tail = ["-pix_fmt", "yuv420p"] + audio_args + ["-movflags", "+faststart"] + self._vcodec_args()

            if profile in ("light_brand", "concert_tag", "raw_watermark", "logo_only", "raw_full_bleed"):
                vid_w, vid_h = _probe_dims(str(input_path))
                self.card_renderer.render_minimal_overlay(
                    profile=profile,
                    channel=channel,
                    output_path=overlay_png,
                    hook_text=hook_text,
                    credit_handle=credit_handle,
                    template=template,
                )
                filter_complex = (
                    self.full_bleed_filter(vid_w, vid_h, "0:v", "base") + ";"
                    "[base][1:v]overlay=0:0:shortest=1[outv]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-loop", "1", "-i", str(overlay_png),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "0:a?", "-shortest",
                ] + common_tail + [str(output_path)]

            elif profile == "meme_native":
                vid_w, vid_h = _probe_dims(str(input_path))
                bar_h = self.card_renderer.measure_meme_bar(hook_text)
                vw, vh, bar_y, vid_y = self.meme_geometry(vid_w, vid_h, bar_h)
                self.card_renderer.render_minimal_overlay(
                    profile="meme_native",
                    channel=channel,
                    output_path=overlay_png,
                    hook_text=hook_text,
                    template=template,
                    meme_bar_y=bar_y,
                    meme_bar_h=bar_h,
                )
                filter_complex = (
                    f"color=c=black:s={CANVAS_W}x{CANVAS_H}[bg];"
                    f"[0:v]scale={vw}:{vh},setsar=1[v];"
                    f"[bg][v]overlay=(W-w)/2:{vid_y}:shortest=1[wv];"
                    "[wv][1:v]overlay=0:0:shortest=1[outv]"
                )
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-loop", "1", "-i", str(overlay_png),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "0:a?", "-shortest",
                ] + common_tail + [str(output_path)]

            elif layout == "full_screen_neon_hud":
                # Aspect-ratio adaptive neon frame (clubbing network brand)
                vision = VideoVisionInspector.analyze(str(input_path))
                vid_w = vision.get("width", 720)
                vid_h = vision.get("height", 1280)
                placement = vision.get("recommended_placement", "bottom")

                y_top_limit, y_bot_limit, max_w = 210, 1750, 960
                max_h = y_bot_limit - y_top_limit
                scale = min(max_w / vid_w, max_h / vid_h)
                box_w = (int(vid_w * scale) // 2) * 2
                box_h = (int(vid_h * scale) // 2) * 2
                box_x = ((CANVAS_W - box_w) // 4) * 2
                box_y = ((y_top_limit + (max_h - box_h) // 2) // 2) * 2

                self.card_renderer.render_adaptive_box_layers(
                    box_coords=(box_x, box_y, box_w, box_h),
                    channel=channel,
                    hook_text=hook_text,
                    hook_placement=placement,
                    template=template,
                    bg_output_path=bg_png,
                    fg_output_path=fg_png
                )
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
                    "-map", "[outv]", "-map", "1:a?", "-shortest",
                ] + common_tail + [str(output_path)]

            else:
                # Editorial informative top card
                self.card_renderer.render_header_overlay(
                    hook_text=hook_text,
                    channel=channel,
                    output_path=overlay_png,
                    credit_handle=credit_handle,
                    highlight_word=highlight_word,
                    template=template
                )
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
                    "-map", "[outv]", "-map", "0:a?",
                ] + common_tail + [str(output_path)]

            logger.info(f"Running FFmpeg composition [{profile}/{layout}]: {output_filename}")
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr[-2000:]}")
                return None

            logger.info(f"Successfully generated reel: {output_path}")
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

    def reskin_reel(
        self,
        raw_video_path: str,
        headline: str,
        highlight_word: Optional[str] = None,
        niche_id: str = "ai_tech",
        account_id: Optional[str] = None,
        credit_handle: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Re-skins an incoming reel with our brand theme (custom font, neon highlight colors,
        channel logo badge, and niche-specific visual layout).
        Extracts a preview frame and returns web URLs for both video and poster frame.
        """
        template = get_template_for_niche(niche_id)
        
        # 1. Resolve Channel Profile
        channel_data = None
        if account_id:
            try:
                from storage.db import get_account_by_id
                channel_data = get_account_by_id(account_id)
            except Exception as e:
                logger.warning(f"Could not load account {account_id}: {e}")

        if channel_data:
            channel = ChannelProfile(
                handle=channel_data.get("handle") or f"@{account_id}",
                display_name=channel_data.get("display_name") or account_id.title(),
                brand_color=channel_data.get("brand_color") or template.highlight_color,
                avatar_initials=channel_data.get("avatar_initials") or "OC",
                profile_pic_url=channel_data.get("profile_pic_url"),
                niche=channel_data.get("niche") or niche_id
            )
        else:
            # Default brand profiles per niche
            if niche_id in ("clubbing", "clubbing_branded", "parties", "girls_party"):
                channel = ChannelProfile(
                    handle="@cute.aarohi007",
                    display_name="Cute Aarohi",
                    brand_color="#FF007F",
                    avatar_initials="AR",
                    niche="clubbing"
                )
            elif niche_id in ("memes", "meme_native"):
                channel = ChannelProfile(
                    handle="@octopus_memes",
                    display_name="Octopus Memes",
                    brand_color="#FFFFFF",
                    avatar_initials="OM",
                    niche="memes"
                )
            elif niche_id in ("concerts", "concert_tag"):
                channel = ChannelProfile(
                    handle="@live_vibes",
                    display_name="Live Concerts",
                    brand_color="#FFFFFF",
                    avatar_initials="LC",
                    niche="concerts"
                )
            else:
                channel = ChannelProfile(
                    handle="@ai_tech_pulse",
                    display_name="AI Tech Pulse",
                    brand_color="#DDF51A",
                    avatar_initials="AI",
                    niche="informative"
                )

        # 2. Prepare output filename
        out_name = output_filename or f"reskinned_{niche_id}_{uuid.uuid4().hex[:8]}.mp4"
        
        # 3. Build reel
        res_path = self.build_reel(
            raw_video_path=raw_video_path,
            hook_text=headline,
            channel=channel,
            output_filename=out_name,
            credit_handle=credit_handle,
            highlight_word=highlight_word,
            template=template
        )

        if not res_path or not Path(res_path).exists():
            return {
                "success": False,
                "error": "Video composition failed during rendering."
            }

        # 4. Extract preview poster frame
        preview_filename = f"{Path(out_name).stem}_preview.png"
        preview_path = self.output_dir / preview_filename
        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", "00:00:01",
                "-i", str(res_path),
                "-vframes", "1",
                "-q:v", "2",
                str(preview_path)
            ]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        except Exception as e:
            logger.warning(f"Failed to extract preview frame: {e}")

        has_preview = preview_path.exists()

        return {
            "success": True,
            "rendered_video_path": str(res_path),
            "rendered_video_url": f"/output/{out_name}",
            "preview_frame_path": str(preview_path) if has_preview else None,
            "preview_frame_url": f"/output/{preview_filename}" if has_preview else None,
            "template_id": template.id,
            "template_name": template.name,
            "render_profile": template.render_profile,
            "channel_handle": channel.handle,
            "headline": headline,
            "highlight_word": highlight_word or template.sample_highlight,
            "niche_id": niche_id
        }

