import cv2
import numpy as np
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("VideoVision")

class VideoVisionInspector:
    """
    Intelligent computer vision inspector for incoming social media videos.
    Extracts geometric dimensions, detects aspect ratios, and scans frames
    for baked-in on-screen text to prevent ugly subtitle collisions.
    """

    @staticmethod
    def get_video_metadata(video_path: str) -> Dict[str, Any]:
        """Extracts resolution, duration, and aspect ratio via ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", video_path
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    w = int(stream.get("width", 720))
                    h = int(stream.get("height", 1280))
                    tags = stream.get("tags", {})
                    side_data = stream.get("side_data_list", [])
                    rotate = 0
                    if "rotate" in tags:
                        rotate = int(tags["rotate"])
                    for sd in side_data:
                        if "rotation" in sd:
                            rotate = int(sd["rotation"])
                    if abs(rotate) in (90, 270):
                        w, h = h, w

                    duration = float(stream.get("duration") or data.get("format", {}).get("duration", 15.0))
                    return {
                        "width": w,
                        "height": h,
                        "aspect_ratio": w / h if h > 0 else 0.5625,
                        "duration": duration,
                        "codec": stream.get("codec_name", "h264")
                    }
        except Exception as e:
            logger.warning(f"ffprobe extraction failed for {video_path}: {e}")

        # Fallback via cv2
        cap = cv2.VideoCapture(video_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 720)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1280)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 450
        duration = frame_count / fps if fps > 0 else 15.0
        cap.release()
        return {
            "width": w,
            "height": h,
            "aspect_ratio": w / h if h > 0 else 0.5625,
            "duration": duration,
            "codec": "unknown"
        }

    @staticmethod
    def inspect_text_occupancy(video_path: str, sample_points: List[float] = [0.25, 0.50, 0.75]) -> Dict[str, Any]:
        """
        Samples video frames to detect if on-screen text, baked-in captions,
        or lyric overlays exist in top, middle, or bottom regions.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {
                "has_baked_in_text": False,
                "occupied_regions": [],
                "recommended_placement": "bottom"
            }

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
        region_scores = {"top": [], "middle": [], "bottom": []}

        for pt in sample_points:
            target_frame = int(total_frames * pt)
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            h, w = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            slices = {
                "top": gray[:int(h * 0.33), :],
                "middle": gray[int(h * 0.33):int(h * 0.67), :],
                "bottom": gray[int(h * 0.67):, :]
            }

            for r_name, reg in slices.items():
                if reg.size == 0:
                    continue
                # Canny edge density (text has dense horizontal character strokes)
                edges = cv2.Canny(reg, 120, 220)
                edge_density = float(np.sum(edges > 0) / edges.size)

                # Morphological stroke gradient with horizontal kernel
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
                grad = cv2.morphologyEx(reg, cv2.MORPH_GRADIENT, kernel)
                grad_mean = float(np.mean(grad))

                # Text signature metric: high localized stroke transitions
                score = (edge_density * 100) + (grad_mean * 0.7)
                region_scores[r_name].append(score)

        cap.release()

        occupied = []
        for r_name, scores in region_scores.items():
            avg_score = float(np.mean(scores)) if scores else 0.0
            # Threshold calibrated for high-contrast on-screen text overlays
            if avg_score > 22.0:
                occupied.append(r_name)

        has_text = len(occupied) > 0

        # Smart placement rule requested by user:
        # "If the video has already written something, do not write on this.
        # But if the video doesn't have written, write over in bottom/middle."
        if has_text:
            placement = "none"
        else:
            placement = "bottom"

        return {
            "has_baked_in_text": has_text,
            "occupied_regions": occupied,
            "recommended_placement": placement
        }

    @staticmethod
    def detect_active_video_bounds(video_path: str) -> Dict[str, Any]:
        """
        Detects if an incoming video has static top headers (like competitor repost cards),
        watermark bars, or letterbox black bars, and returns the bounding box of the active
        moving video content for automatic surgical cropping.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return {
                "has_header": False,
                "has_footer": False,
                "crop_needed": False,
                "crop_box": None,
                "active_y_range": (0, 1920)
            }

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
        vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1080)
        vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1920)

        frames = []
        for r in [0.15, 0.30, 0.45, 0.60, 0.75, 0.90]:
            target_idx = max(0, min(total_frames - 1, int(total_frames * r)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                small = cv2.resize(frame, (360, 640), interpolation=cv2.INTER_AREA)
                frames.append(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY))
        cap.release()

        if len(frames) < 3:
            return {
                "has_header": False,
                "has_footer": False,
                "crop_needed": False,
                "crop_box": None,
                "active_y_range": (0, vid_h)
            }

        diffs = [cv2.absdiff(frames[i], frames[i+1]) for i in range(len(frames) - 1)]
        avg_diff = np.mean(diffs, axis=0)

        row_motion = np.mean(avg_diff, axis=1)
        max_motion = float(np.max(row_motion)) if np.max(row_motion) > 0 else 1.0

        avg_gray = np.mean(frames, axis=0)
        row_bright = np.mean(avg_gray, axis=1)

        active_rows = np.where((row_motion > max_motion * 0.12) & (row_bright > 12.0))[0]

        if len(active_rows) == 0:
            return {
                "has_header": False,
                "has_footer": False,
                "crop_needed": False,
                "crop_box": None,
                "active_y_range": (0, vid_h)
            }

        scale_y = vid_h / 640.0
        y_min = int(active_rows[0] * scale_y)
        y_max = int(active_rows[-1] * scale_y)

        y_min = (max(0, y_min) // 2) * 2
        y_max = (min(vid_h, y_max) // 2) * 2

        has_header = (y_min / vid_h) > 0.08
        has_footer = ((vid_h - y_max) / vid_h) > 0.08
        crop_needed = has_header or has_footer

        crop_h = max(100, y_max - y_min)
        crop_w = vid_w

        return {
            "has_header": has_header,
            "has_footer": has_footer,
            "crop_needed": crop_needed,
            "crop_box": {
                "x": 0,
                "y": y_min,
                "w": crop_w,
                "h": crop_h
            } if crop_needed else None,
            "header_height": y_min,
            "footer_offset": vid_h - y_max,
            "active_y_range": (y_min, y_max),
            "original_dims": (vid_w, vid_h)
        }

    @classmethod
    def analyze(cls, video_path: str) -> Dict[str, Any]:
        """Complete unified analysis of incoming video."""
        meta = cls.get_video_metadata(video_path)
        text_info = cls.inspect_text_occupancy(video_path)
        bounds_info = cls.detect_active_video_bounds(video_path)
        return {
            **meta,
            **text_info,
            "active_bounds": bounds_info
        }
