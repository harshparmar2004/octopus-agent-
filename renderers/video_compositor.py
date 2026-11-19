import uuid
import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

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

_DETECTED_VCODEC_ARGS: Optional[List[str]] = None

def get_best_vcodec_args() -> List[str]:
    """
    Auto-detects the fastest available H.264 video encoder:
    1. macOS: h264_videotoolbox
    2. Windows/Linux: NVIDIA NVENC (h264_nvenc) - hardware accelerated GPU encoding (up to 10x faster)
    3. Windows/Linux: Intel QuickSync (h264_qsv)
    4. Fallback: CPU libx264 (preset=fast)
    """
    global _DETECTED_VCODEC_ARGS
    if _DETECTED_VCODEC_ARGS is not None:
        return list(_DETECTED_VCODEC_ARGS)

    if platform.system() == "Darwin":
        _DETECTED_VCODEC_ARGS = ["-c:v", "h264_videotoolbox", "-b:v", "6500k"]
        return list(_DETECTED_VCODEC_ARGS)

    # 1. Probe NVIDIA NVENC
    try:
        test_cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=duration=1:size=320x240:rate=10",
            "-c:v", "h264_nvenc", "-preset", "p4",
            "-f", "null", "-"
        ]
        res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
        if res.returncode == 0:
            logger.info("VideoCompositor: Activated NVIDIA NVENC GPU hardware acceleration (h264_nvenc)")
            _DETECTED_VCODEC_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-b:v", "6500k"]
            return list(_DETECTED_VCODEC_ARGS)
    except Exception as e:
        logger.debug(f"NVENC probe error: {e}")

    # 2. Probe Intel QuickSync
    try:
        test_cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=duration=1:size=320x240:rate=10",
            "-c:v", "h264_qsv",
            "-f", "null", "-"
        ]
        res = subprocess.run(test_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
        if res.returncode == 0:
            logger.info("VideoCompositor: Activated Intel QuickSync GPU acceleration (h264_qsv)")
            _DETECTED_VCODEC_ARGS = ["-c:v", "h264_qsv", "-b:v", "6500k"]
            return list(_DETECTED_VCODEC_ARGS)
    except Exception as e:
        logger.debug(f"QSV probe error: {e}")

    # 3. CPU Fallback
    logger.info("VideoCompositor: Hardware acceleration not found, using CPU libx264")
    _DETECTED_VCODEC_ARGS = ["-c:v", "libx264", "-preset", "fast", "-crf", "22"]
    return list(_DETECTED_VCODEC_ARGS)


class VideoCompositor:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or settings.OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.card_renderer = CardRenderer()

    @staticmethod
    def _vcodec_args():
        return get_best_vcodec_args()

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
        template_id: Optional[str] = None,
        auto_crop_header: bool = True,
        crop_box: Optional[Dict[str, int]] = None
    ) -> Optional[str]:
        """
        Composites a raw video into a 1080x1920 Reel according to the niche's render profile:
        - 'full_template' + layout 'full_screen_neon_hud' : aspect-adaptive neon frame (clubbing brand)
        - 'full_template' (other layouts)                  : editorial top card (Cult Information)
        - 'light_brand'                                     : full-bleed + corner handle + optional short hook
        - 'concert_tag'                                     : full-bleed + lower-third artist/city/venue + filmer credit
        - 'raw_watermark'                                   : full-bleed raw video + micro watermark
        - 'meme_native'                                     : white caption bar above the video
        """
        input_path = Path(raw_video_path)
        if not input_path.exists():
            logger.error(f"Input video not found: {raw_video_path}")
            return None

        # 0. Active middle video extraction / bounds detection
        effective_crop = crop_box
        if auto_crop_header and not effective_crop:
            try:
                from processors.video_vision import VideoVisionInspector
                bounds = VideoVisionInspector.detect_active_video_bounds(str(input_path))
                if bounds.get("crop_needed") and bounds.get("crop_box"):
                    effective_crop = bounds["crop_box"]
            except Exception as be:
                logger.warning(f"Auto-crop bounds detection skipped: {be}")

        temp_crop_file: Optional[Path] = None
        crop_prefix = ""
        src_v = "0:v"
        if effective_crop:
            cx = effective_crop.get("x", 0)
            cy = effective_crop.get("y", 0)
            cw = (effective_crop.get("w", 1080) // 2) * 2
            ch = (effective_crop.get("h", 1920) // 2) * 2
            crop_prefix = f"[0:v]crop={cw}:{ch}:{cx}:{cy}[v_cropped];"
            src_v = "v_cropped"
            vid_w, vid_h = cw, ch
            logger.info(f"Fusing single-pass active crop: crop={cw}:{ch}:{cx}:{cy}")
        else:
            vid_w, vid_h = _probe_dims(str(input_path))

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
                self.card_renderer.render_minimal_overlay(
                    profile=profile,
                    channel=channel,
                    output_path=overlay_png,
                    hook_text=hook_text,
                    credit_handle=credit_handle,
                    template=template,
                )
                filter_complex = (
                    crop_prefix +
                    self.full_bleed_filter(vid_w, vid_h, src_v, "base") + ";"
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
                    crop_prefix +
                    f"color=c=black:s={CANVAS_W}x{CANVAS_H}[bg];"
                    f"[{src_v}]scale={vw}:{vh},setsar=1[v];"
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
                v_w = vision.get("width", vid_w)
                v_h = vision.get("height", vid_h)
                placement = vision.get("recommended_placement", "bottom")

                y_top_limit, y_bot_limit, max_w = 210, 1750, 960
                max_h = y_bot_limit - y_top_limit
                scale = min(max_w / v_w, max_h / v_h)
                box_w = (int(v_w * scale) // 2) * 2
                box_h = (int(v_h * scale) // 2) * 2
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
                hud_crop_prefix = f"[1:v]crop={cw}:{ch}:{cx}:{cy}[hud_cropped];" if effective_crop else ""
                hud_src = "hud_cropped" if effective_crop else "1:v"
                filter_complex = (
                    hud_crop_prefix +
                    f"[{hud_src}]scale={box_w}:{box_h}[vid];"
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
                v_ar = vid_w / max(1, vid_h)
                vh_target = 1480
                vy_offset = 440

                # Editorial informative top card (Cult Information)
                self.card_renderer.render_header_overlay(
                    hook_text=hook_text,
                    channel=channel,
                    output_path=overlay_png,
                    credit_handle=credit_handle,
                    highlight_word=highlight_word,
                    template=template,
                    aspect_ratio=v_ar,
                    show_credit=False
                )

                if NATIVE_VERTICAL_AR[0] <= v_ar <= NATIVE_VERTICAL_AR[1]:
                    # Vertical 9:16 video covers the available area cleanly
                    filter_complex = (
                        crop_prefix +
                        f"color=c=black:s={CANVAS_W}x{CANVAS_H}[bg];"
                        f"[{src_v}]scale={CANVAS_W}:{vh_target}:force_original_aspect_ratio=increase,crop={CANVAS_W}:{vh_target},setsar=1[vid];"
                        f"[bg][vid]overlay=0:{vy_offset}:shortest=1[with_vid];"
                        "[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                    )
                else:
                    # Non-vertical video:
                    # For top_card_cult, informative reels (Cult Information, Pubity) use clean pure black canvas
                    if layout == "top_card_cult":
                        if 0.85 <= v_ar <= 1.25:
                            # 1:1 Square video: Shift video upward to y=500 so it leaves comfortable bottom margin
                            filter_complex = (
                                crop_prefix +
                                f"color=c=black:s={CANVAS_W}x{CANVAS_H}[bg];"
                                f"[{src_v}]scale={CANVAS_W}:-2:force_original_aspect_ratio=decrease,setsar=1[sharp_vid];"
                                f"[bg][sharp_vid]overlay=(W-w)/2:500:shortest=1[with_vid];"
                                "[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                            )
                        else:
                            # 16:9 Landscape / cropped: center video at (H-h)/2, balancing downward header
                            filter_complex = (
                                crop_prefix +
                                f"color=c=black:s={CANVAS_W}x{CANVAS_H}[bg];"
                                f"[{src_v}]scale={CANVAS_W}:-2:force_original_aspect_ratio=decrease,setsar=1[sharp_vid];"
                                f"[bg][sharp_vid]overlay=(W-w)/2:(H-h)/2:shortest=1[with_vid];"
                                "[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                            )
                    else:
                        # Other layouts: blurred ambient fill + centered video below header
                        filter_complex = (
                            crop_prefix +
                            f"color=c=black:s={CANVAS_W}x{CANVAS_H}[bg];"
                            f"[{src_v}]split=2[v_bg][v_fg];"
                            f"[v_bg]scale={CANVAS_W}:{vh_target}:force_original_aspect_ratio=increase,crop={CANVAS_W}:{vh_target},boxblur=24:2,eq=brightness=-0.08[blur_bg];"
                            f"[v_fg]scale={CANVAS_W}:{vh_target}:force_original_aspect_ratio=decrease,setsar=1[sharp_vid];"
                            f"[blur_bg][sharp_vid]overlay=(W-w)/2:(H-h)/2[fitted_vid];"
                            f"[bg][fitted_vid]overlay=0:{vy_offset}:shortest=1[with_vid];"
                            "[with_vid][1:v]overlay=0:0:shortest=1[outv]"
                        )

                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-loop", "1", "-i", str(overlay_png),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "0:a?", "-shortest",
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
            for p in [overlay_png, bg_png, fg_png, temp_crop_file]:
                if p and p.exists():
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
        auto_crop_header: bool = True,
        crop_box: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        Re-skins an incoming reel with our brand theme (custom font, neon highlight colors,
        channel logo badge, and niche-specific visual layout).
        If auto_crop_header is enabled and a competitor repost header or card is detected,
        it automatically slices out the top header so only the clean raw video is used.
        """
        template = get_template_for_niche(niche_id)
        
        # 0. Surgical Auto-Crop of Competitor Repost Headers / Top Banners
        working_video = raw_video_path
        temp_cropped_path = None
        if auto_crop_header or crop_box:
            effective_crop = crop_box
            if not effective_crop:
                try:
                    bounds = VideoVisionInspector.detect_active_video_bounds(raw_video_path)
                    if bounds.get("crop_needed") and bounds.get("crop_box"):
                        effective_crop = bounds["crop_box"]
                except Exception as be:
                    logger.warning(f"Bounds detection skipped: {be}")

            if effective_crop:
                cx = effective_crop.get("x", 0)
                cy = effective_crop.get("y", 0)
                cw = (effective_crop.get("w", 1080) // 2) * 2
                ch = (effective_crop.get("h", 1920) // 2) * 2
                
                temp_cropped_path = self.output_dir / f"clean_crop_{uuid.uuid4().hex[:8]}.mp4"
                crop_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(raw_video_path),
                    "-vf", f"crop={cw}:{ch}:{cx}:{cy}",
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "copy",
                    str(temp_cropped_path)
                ]
                logger.info(f"Slicing competitor header: crop={cw}:{ch}:{cx}:{cy}")
                crop_res = subprocess.run(crop_cmd, capture_output=True, text=True, timeout=30)
                if crop_res.returncode == 0 and temp_cropped_path.exists():
                    working_video = str(temp_cropped_path)

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
                    handle="@cult_information",
                    display_name="Cult Information",
                    brand_color="#C1F02A",
                    avatar_initials="CI",
                    niche="ai_tech"
                )

        # 2. Prepare output filename
        out_name = output_filename or f"reskinned_{niche_id}_{uuid.uuid4().hex[:8]}.mp4"
        
        # 3. Build reel using working_video (cropped or raw)
        res_path = self.build_reel(
            raw_video_path=working_video,
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
            "niche_id": niche_id,
            "cropped": bool(temp_cropped_path and temp_cropped_path.exists())
        }

    def batch_reskin_network(
        self,
        raw_video_path: str,
        headline: str,
        highlight_word: Optional[str] = None,
        niche_id: str = "ai_tech",
        account_ids: Optional[List[str]] = None,
        auto_crop_header: bool = True,
        crop_box: Optional[Dict[str, int]] = None,
        original_bio: Optional[str] = None,
        cta_template: Optional[str] = None,
        max_accounts: int = 20,
    ) -> Dict[str, Any]:
        """
        Scales the reel across the entire network (e.g. 20 accounts) in a single pass.
        The video is cleaned and cropped ONCE, and then re-skinned for each account
        with its unique logo, handle, and bio CTA attribution.
        """
        from storage.db import get_all_accounts

        working_video = raw_video_path
        if auto_crop_header or crop_box:
            effective_crop = crop_box
            if not effective_crop:
                try:
                    bounds = VideoVisionInspector.detect_active_video_bounds(raw_video_path)
                    if bounds.get("crop_needed") and bounds.get("crop_box"):
                        effective_crop = bounds["crop_box"]
                except Exception as be:
                    logger.warning(f"Bounds detection skipped: {be}")

            if effective_crop:
                cx = effective_crop.get("x", 0)
                cy = effective_crop.get("y", 0)
                cw = (effective_crop.get("w", 1080) // 2) * 2
                ch = (effective_crop.get("h", 1920) // 2) * 2
                
                clean_video_path = self.output_dir / f"clean_master_{uuid.uuid4().hex[:8]}.mp4"
                crop_cmd = [
                    "ffmpeg", "-y",
                    "-i", str(raw_video_path),
                    "-vf", f"crop={cw}:{ch}:{cx}:{cy}",
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "copy",
                    str(clean_video_path)
                ]
                crop_res = subprocess.run(crop_cmd, capture_output=True, text=True, timeout=30)
                if crop_res.returncode == 0 and clean_video_path.exists():
                    working_video = str(clean_video_path)

        all_accs = get_all_accounts(active_only=True)
        if account_ids and len(account_ids) > 0:
            target_accs = [a for a in all_accs if a["id"] in account_ids]
        else:
            n_clean = niche_id.lower().replace("ai_", "").replace("_tech", "").replace("_cult", "")
            target_accs = [a for a in all_accs if n_clean in (a.get("niche") or "").lower() or a.get("niche_id") == niche_id]
            if not target_accs:
                target_accs = all_accs
            target_accs = target_accs[:max_accounts]

        results = []
        cta = cta_template or "Follow @{handle} for daily deep tech breakdowns!"
        bio_text = original_bio or ""

        for idx, acc in enumerate(target_accs):
            acc_handle = acc.get("handle") or f"@{acc['id']}"
            out_filename = f"batch_{niche_id}_{acc['id']}_{uuid.uuid4().hex[:6]}.mp4"
            
            reskin_res = self.reskin_reel(
                raw_video_path=working_video,
                headline=headline,
                highlight_word=highlight_word,
                niche_id=niche_id,
                account_id=acc["id"],
                output_filename=out_filename,
                auto_crop_header=False
            )

            per_acc_cta = cta.replace("{handle}", acc_handle.lstrip("@")).replace("{niche}", "tech" if "tech" in niche_id else niche_id)
            full_caption = f"{bio_text}\n\n{per_acc_cta}".strip()

            reskin_res["account_id"] = acc["id"]
            reskin_res["account_handle"] = acc_handle
            reskin_res["display_name"] = acc.get("display_name", acc_handle)
            reskin_res["bio_caption"] = full_caption
            results.append(reskin_res)

        return {
            "success": True,
            "total_accounts": len(results),
            "niche_id": niche_id,
            "headline": headline,
            "clean_video_path": working_video,
            "results": results
        }

    def build_viral_dance_reel(
        self,
        raw_video_path: str,
        hook_text: str,
        channel: ChannelProfile,
        output_filename: str,
        credit_handle: Optional[str] = None,
        account_index: int = 0,
        template: Optional[NicheTemplate] = None
    ) -> Optional[str]:
        """
        Transforms raw dance/entertainment video into an algorithmically unique, viral-ready Reel:
        1. 1.02x Micro-Zoom & Center Crop: Alters all pixel coordinates and motion vectors (defeats duplicate perceptual hash)
        2. Color & Vibrance Curve: +3% contrast, +6% saturation, 0.99 gamma (rich party/stage lighting)
        3. Audio Resampling & Micro-Pitch Dither: 48kHz resample with 0.15% pitch shift (bypasses audio fingerprinting while keeping music pristine)
        4. Modern Floating Frosted Hook: High-retention curiosity hook in safe top area (no clunky black cards)
        5. Apple iPhone 15 Pro Max Metadata Injection: Strips scraper headers and writes genuine iOS camera metadata
        6. Hardware NVENC GPU Acceleration: Renders in ~2 seconds
        """
        input_path = Path(raw_video_path)
        if not input_path.exists():
            logger.error(f"Input video not found: {raw_video_path}")
            return None

        output_path = self.output_dir / output_filename
        overlay_png = self.output_dir / f"temp_viral_overlay_{input_path.stem}_{account_index}.png"

        try:
            # 1. Render modern floating hook overlay
            self.card_renderer.render_viral_floating_hook(
                hook_text=hook_text,
                channel=channel,
                output_path=overlay_png,
                credit_handle=credit_handle,
                template=template
            )

            # 2. Filter complex:
            # - Zoom in 1.02x to strip borders/watermarks and alter spatial hash
            # - Scale to 1080x1920 full bleed
            # - Color enhancement curve
            # - Overlay floating hook
            filter_complex = (
                "[0:v]crop=in_w*0.98:in_h*0.98:in_w*0.01:in_h*0.01,"
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,setsar=1,"
                "eq=contrast=1.03:brightness=0.01:saturation=1.06:gamma=0.99[base];"
                "[base][1:v]overlay=0:0:shortest=1[outv]"
            )

            # 3. Audio filter: micro-pitch dither (0.15% shift) & 48kHz resampling
            audio_filter = "aresample=48000,asetrate=44166,aresample=48000"

            # 4. Device metadata: Apple iPhone 15 Pro Max iOS 17.5
            meta_args = [
                "-map_metadata", "-1",
                "-metadata", "make=Apple",
                "-metadata", "model=iPhone 15 Pro Max",
                "-metadata", "encoder=QuickTime / Apple iOS 17.5.1",
                "-metadata:s:v:0", "handler_name=Apple Video Media Handler",
                "-metadata", "comment=Shot on iPhone 15 Pro Max"
            ]

            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_path),
                "-loop", "1", "-i", str(overlay_png),
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "0:a?",
                "-filter:a", audio_filter,
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-shortest"
            ] + self._vcodec_args() + meta_args + [str(output_path)]

            logger.info(f"Rendering viral transformed reel with GPU NVENC: {output_filename}")
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            if res.returncode != 0 or not output_path.exists():
                logger.warning(f"FFmpeg viral transform with audio filter returned {res.returncode}, trying fallback: {res.stderr[:200]}")
                cmd_fallback = [
                    "ffmpeg", "-y",
                    "-i", str(input_path),
                    "-loop", "1", "-i", str(overlay_png),
                    "-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "0:a?",
                    "-c:a", "aac", "-b:a", "192k",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    "-shortest"
                ] + self._vcodec_args() + meta_args + [str(output_path)]
                subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

            return str(output_path) if output_path.exists() else str(input_path)
        except Exception as e:
            logger.error(f"build_viral_dance_reel error: {e}")
            return str(input_path)
        finally:
            if overlay_png.exists():
                try:
                    overlay_png.unlink()
                except Exception:
                    pass


