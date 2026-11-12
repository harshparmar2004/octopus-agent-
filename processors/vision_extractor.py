import os
import re
import cv2
import json
import base64
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

from config import settings
from renderers.niche_templates import CORE_NICHE_TEMPLATES, NICHE_TO_TEMPLATE_MAP, get_template_for_niche
from processors.video_vision import VideoVisionInspector
from processors.llm_manager import LLMManager

logger = logging.getLogger("VisionExtractor")

VISION_OUTPUT_DIR = settings.OUTPUT_DIR / "vision_frames"
VISION_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class VisionExtractor:
    """
    Multimodal Vision Engine for Octopus Agent.
    Inspects incoming reel frames, extracts baked-in headlines/captions,
    understands video context, and suggests highlight words and niche templates.
    """

    @staticmethod
    def extract_representative_frames(
        video_path: str,
        count: int = 3,
        output_dir: Optional[Path] = None
    ) -> List[str]:
        """
        Samples equidistant keyframes across the video duration
        and saves them as JPEG thumbnails for vision inspection.
        """
        out_dir = output_dir or VISION_OUTPUT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        vid_path = Path(video_path)
        if not vid_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return []

        cap = cv2.VideoCapture(str(vid_path))
        if not cap.isOpened():
            logger.error(f"Cannot open video for frame extraction: {video_path}")
            return []

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 100)
        saved_paths: List[str] = []

        # Sample at 15%, 50%, 80% or evenly spaced points
        if count == 3:
            ratios = [0.15, 0.50, 0.80]
        else:
            step = 1.0 / (count + 1)
            ratios = [step * (i + 1) for i in range(count)]

        stem = vid_path.stem
        for idx, ratio in enumerate(ratios):
            target_idx = max(0, min(total_frames - 1, int(total_frames * ratio)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            # Scale frame down if too large (keep max dimension <= 1080 for efficient payload)
            h, w = frame.shape[:2]
            max_dim = max(h, w)
            if max_dim > 1080:
                scale = 1080 / max_dim
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

            frame_filename = f"{stem}_frame_{idx + 1}.jpg"
            frame_path = out_dir / frame_filename
            cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            saved_paths.append(str(frame_path))

        cap.release()
        logger.info(f"Extracted {len(saved_paths)} frames from {video_path}")
        return saved_paths

    @staticmethod
    def encode_image_base64(image_path: str) -> str:
        """Reads an image from disk and converts to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @classmethod
    def analyze_with_gemini(
        cls,
        frame_paths: List[str],
        api_key: str,
        model: str = "gemini-1.5-flash"
    ) -> Dict[str, Any]:
        """
        Sends frame images to Google Gemini Vision API to detect text, context,
        and recommend punchy headline/highlight words.
        """
        if not api_key:
            raise ValueError("Gemini API key is required for Gemini Vision analysis.")

        if not frame_paths:
            raise ValueError("No frames provided for vision analysis.")

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        prompt_text = (
            "You are an expert social media computer vision and viral copywriting director. "
            "Analyze these sequential frames from an Instagram Reel and return a strictly valid JSON object.\n\n"
            "CRITICAL INSTRUCTIONS FOR REPOSTS & COMPOSITE REELS:\n"
            "Videos often have multiple headers (e.g. an outer reposter account on top like 'Cult Information', "
            "and an inner catchy headline right above the video like 'The most expensive AI chips in the world are now worth more than $10,000,000,000'). "
            "Always identify the CORE hook headline that directly introduces the actual video subject matter!\n\n"
            "TASKS:\n"
            "1. 'exact_text': Transcribe the EXACT on-screen headline written/baked into the video. "
            "If multiple lines exist, prioritize the punchy hook line directly above the video.\n"
            "2. 'headline': The catchy, eye-grabbing hook headline (8 to 16 words) to write on our re-skinned reel.\n"
            "3. 'highlight_word': The 1 to 3 most impactful or bold words in that headline (e.g. 'expensive AI chips') "
            "that should glow in high-contrast neon yellow (#DDF51A) or hot pink (#FF007F).\n"
            "4. 'context': A concise 1-2 sentence description of what happens in the video.\n"
            "5. 'detected_niche': Pick strictly ONE from: 'ai_tech', 'memes', 'clubbing', 'concerts', 'ai_content', 'girls_dance'.\n"
            "6. 'suggested_caption': A high-retention caption formatted for Instagram.\n"
            "7. 'has_baked_in_text': Boolean true if the video has visible on-screen text.\n"
            "8. 'has_competitor_header': Boolean true if there is a competitor logo, card, or top banner that should be cropped out.\n\n"
            "Return JSON schema only:\n"
            "{\n"
            '  "exact_text": "...",\n'
            '  "headline": "...",\n'
            '  "highlight_word": "...",\n'
            '  "context": "...",\n'
            '  "detected_niche": "ai_tech",\n'
            '  "suggested_caption": "...",\n'
            '  "has_baked_in_text": false,\n'
            '  "has_competitor_header": false,\n'
            '  "confidence": 0.95\n'
            "}"
        )

        parts: List[Dict[str, Any]] = [{"text": prompt_text}]

        for fp in frame_paths:
            b64_data = cls.encode_image_base64(fp)
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64_data
                }
            })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        }

        headers = {"Content-Type": "application/json"}
        response = requests.post(endpoint, json=payload, headers=headers, timeout=25)

        if response.status_code != 200:
            error_msg = f"Gemini API error ({response.status_code}): {response.text[:300]}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini returned empty candidate list.")

        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        clean_text = raw_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:-3].strip()
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:-3].strip()

        parsed = json.loads(clean_text)

        # Normalize niche and template
        niche_key = parsed.get("detected_niche", "ai_tech").lower().strip()
        template_id = NICHE_TO_TEMPLATE_MAP.get(niche_key, "informative_cult")
        template = get_template_for_niche(niche_key)

        headline = parsed.get("headline") or parsed.get("exact_text") or "Viral breakthrough changing how this works"
        highlight = parsed.get("highlight_word") or ""
        if not highlight and headline:
            words = headline.split()
            highlight = words[len(words) // 2] if words else ""

        return {
            "success": True,
            "engine": "gemini_vision",
            "model": model,
            "exact_text": parsed.get("exact_text", "").strip(),
            "headline": headline.strip(),
            "highlight_word": highlight.strip(),
            "context": parsed.get("context", "Reel video content").strip(),
            "detected_niche": niche_key,
            "target_template_id": template_id,
            "template_name": template.name,
            "suggested_caption": parsed.get("suggested_caption", ""),
            "has_baked_in_text": bool(parsed.get("has_baked_in_text", bool(parsed.get("exact_text")))),
            "confidence": float(parsed.get("confidence", 0.9))
        }

    @classmethod
    def analyze_fallback(
        cls,
        video_path: str,
        frame_paths: List[str],
        fallback_title: str = ""
    ) -> Dict[str, Any]:
        """
        Local heuristic & OpenCV stroke-occupancy fallback when Gemini key
        is not provided or offline.
        """
        vision_info = VideoVisionInspector.analyze(video_path)
        has_text = vision_info.get("has_baked_in_text", False)

        # Infer context from path/filename or title
        clean_name = Path(video_path).stem.replace("_", " ").title()
        title_hint = fallback_title or clean_name

        # Detect likely niche based on filename keywords
        lower_name = (video_path + " " + title_hint).lower()
        if any(k in lower_name for k in ["party", "club", "edm", "dance", "dj", "night"]):
            detected_niche = "clubbing"
            headline = f"Weekend vibe and crowd energy that completely took over {title_hint}"
            highlight = "completely"
            context = "Nightlife, music, and clubbing party celebration"
        elif any(k in lower_name for k in ["tech", "ai", "science", "code", "quantum", "robot"]):
            detected_niche = "ai_tech"
            headline = f"The underlying technology behind {title_hint} that changes everything"
            highlight = "changes everything"
            context = "Deep tech and innovative computational workflow demonstration"
        elif any(k in lower_name for k in ["meme", "funny", "lol", "relatable"]):
            detected_niche = "memes"
            headline = f"When you realize what actually happened with {title_hint}"
            highlight = "actually"
            context = "Humorous and relatable social meme"
        elif any(k in lower_name for k in ["concert", "live", "stage", "festival"]):
            detected_niche = "concerts"
            headline = f"Live performance moment from {title_hint}"
            highlight = "Live performance"
            context = "Live music performance and stage energy"
        else:
            detected_niche = "ai_tech"
            headline = f"Two people can experience the exact same thing and see completely different results"
            highlight = "completely"
            context = "Informative visual breakdown and phenomenon observation"

        template_id = NICHE_TO_TEMPLATE_MAP.get(detected_niche, "informative_cult")
        template = get_template_for_niche(detected_niche)

        return {
            "success": True,
            "engine": "local_vision_heuristic",
            "model": "opencv_stroke_inspector",
            "exact_text": title_hint if has_text else "",
            "headline": headline,
            "highlight_word": highlight,
            "context": context,
            "detected_niche": detected_niche,
            "target_template_id": template_id,
            "template_name": template.name,
            "suggested_caption": f"Breaking down {headline.lower()}. Let us know your thoughts in the comments!",
            "has_baked_in_text": has_text,
            "confidence": 0.75,
            "vision_metadata": vision_info
        }

    @classmethod
    def analyze_reel(
        cls,
        source_url_or_path: str,
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified entrypoint: Accepts a reel URL or local file path, extracts frames,
        and returns structured vision analysis with web-accessible thumbnails.
        """
        src = source_url_or_path.strip()
        local_video_path = src

        # 1. Resolve / download URL if remote
        source_caption = ""
        source_title = ""
        if src.startswith("http://") or src.startswith("https://"):
            logger.info(f"Downloading remote video from URL: {src}")
            from scrapers.content_harvester import ContentHarvester
            harvester = ContentHarvester()
            downloaded = harvester.download_video(src)
            if not downloaded:
                return {
                    "success": False,
                    "error": f"Failed to download video from link: {src}"
                }
            if isinstance(downloaded, dict):
                local_video_path = downloaded.get("filepath", "")
                source_caption = downloaded.get("description", "")
                source_title = downloaded.get("title", "")
            else:
                local_video_path = str(downloaded)

        if not local_video_path or not Path(local_video_path).exists():
            return {
                "success": False,
                "error": f"Video file not found at path: {local_video_path}"
            }

        # 2. Extract active video bounds (detects static competitor headers to crop)
        bounds_info = VideoVisionInspector.detect_active_video_bounds(local_video_path)

        # 3. Extract representative keyframes
        frame_paths = cls.extract_representative_frames(local_video_path, count=3)
        if not frame_paths:
            return {
                "success": False,
                "error": f"Failed to extract video frames from: {local_video_path}"
            }

        # 4. Determine Gemini API Key
        effective_key = api_key or os.getenv("GEMINI_API_KEY")
        if not effective_key:
            mgr_cfg = LLMManager().config
            if mgr_cfg.get("provider") == "gemini" and mgr_cfg.get("api_key"):
                effective_key = mgr_cfg["api_key"]

        # 5. Perform analysis
        analysis: Dict[str, Any] = {}
        if effective_key:
            try:
                analysis = cls.analyze_with_gemini(frame_paths, api_key=effective_key)
            except Exception as e:
                logger.warning(f"Gemini Vision call failed, switching to local fallback: {e}")
                analysis = cls.analyze_fallback(local_video_path, frame_paths, fallback_title=source_title)
                analysis["fallback_reason"] = str(e)
        else:
            logger.info("No Gemini API key detected; utilizing intelligent local vision fallback.")
            analysis = cls.analyze_fallback(local_video_path, frame_paths, fallback_title=source_title)

        # 6. Format web thumbnail paths
        frame_web_urls = []
        for fp in frame_paths:
            fname = Path(fp).name
            frame_web_urls.append(f"/output/vision_frames/{fname}")

        analysis["video_path"] = local_video_path
        analysis["frame_paths"] = frame_paths
        analysis["frame_thumbnails"] = frame_web_urls
        analysis["source_caption"] = source_caption or analysis.get("suggested_caption", "")
        analysis["original_bio"] = source_caption or ""
        analysis["active_bounds"] = bounds_info
        analysis["has_competitor_header"] = bounds_info.get("has_header", False)
        analysis["crop_needed"] = bounds_info.get("crop_needed", False)
        analysis["crop_box"] = bounds_info.get("crop_box")
        return analysis
