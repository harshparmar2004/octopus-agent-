import re
import os
import time
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
import requests
import yt_dlp

from config import settings

logger = logging.getLogger("InstagramHarvester")

# AI Curated directory of top-performing viral Instagram accounts by niche
RECOMMENDED_TARGET_HANDLES = {
    "quantum": [
        {"handle": "uncover.quantum", "name": "Uncover Quantum", "niche": "Quantum Computing & Deep Tech", "desc": "Top viral quantum physics demonstrations"},
        {"handle": "physicsfun", "name": "PhysicsFun", "niche": "Quantum & Experimental Physics", "desc": "Sensational physics toys & quantum levitation"},
        {"handle": "ibm_research", "name": "IBM Research", "niche": "Quantum Supercomputers", "desc": "Official IBM quantum hardware announcements"},
        {"handle": "cern", "name": "CERN", "niche": "Particle Physics", "desc": "Large Hadron Collider & antimatter research"},
    ],
    "ai": [
        {"handle": "uncover.ai", "name": "Uncover AI", "niche": "Generative AI & LLMs", "desc": "Fast-paced AI product releases and demos"},
        {"handle": "openai", "name": "OpenAI", "niche": "Frontier AI", "desc": "Sora, GPT, and reasoning model demos"},
        {"handle": "googledeepmind", "name": "Google DeepMind", "niche": "AGI & Scientific AI", "desc": "AlphaFold, Gemini, and robotics intelligence"},
        {"handle": "huggingface", "name": "Hugging Face", "niche": "Open Source AI", "desc": "Trending open source models and papers"},
    ],
    "robotics": [
        {"handle": "uncover.robotics", "name": "Uncover Robotics", "niche": "Humanoid Robotics", "desc": "Viral robotics and embodied AI clips"},
        {"handle": "bostondynamicsofficial", "name": "Boston Dynamics", "niche": "Agile Robotics", "desc": "Atlas and Spot parkour and factory tasks"},
        {"handle": "figure_robot", "name": "Figure AI", "niche": "Commercial Humanoids", "desc": "Autonomous neural-network driven humanoids"},
        {"handle": "1x_technologies", "name": "1X Technologies", "niche": "Androids", "desc": "Bipedal household and warehouse androids"},
    ],
    "space": [
        {"handle": "nasagoddard", "name": "NASA Goddard", "niche": "Space Exploration", "desc": "James Webb 4K deep space imagery"},
        {"handle": "spacex", "name": "SpaceX", "niche": "Rocket Engineering", "desc": "Starship flight tests and booster catches"},
        {"handle": "dailyoverview", "name": "Daily Overview", "niche": "Satellite Imagery", "desc": "Stunning high-res orbital satellite clips"},
    ],
    "biotech": [
        {"handle": "syntheticbioworld", "name": "Synthetic Biology", "niche": "BioTech & Genetics", "desc": "CRISPR gene editing and cellular engineering"},
        {"handle": "naturebiotech", "name": "Nature Biotechnology", "niche": "Biotech Breakthroughs", "desc": "Leading peer-reviewed biotechnology breakthroughs"},
    ]
}

class InstagramHarvester:
    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir = download_dir or settings.STORAGE_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }

    def get_recommended_handles(self, niche: Optional[str] = None) -> List[Dict]:
        """Returns AI-recommended target handles for a given niche or all niches."""
        if niche and niche.lower() in RECOMMENDED_TARGET_HANDLES:
            return RECOMMENDED_TARGET_HANDLES[niche.lower()]
        all_handles = []
        for n, handles in RECOMMENDED_TARGET_HANDLES.items():
            all_handles.extend(handles)
        return all_handles

    def get_latest_reel_from_handle(
        self,
        username: str,
        meta_ig_user_id: Optional[str] = None,
        meta_access_token: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Discovers the newest Reel for any target Instagram username.
        Tries:
        1. Meta Business Discovery API (Official, reliable)
        2. Web-based public parser fallback
        """
        clean_handle = username.lstrip("@").strip().lower()
        logger.info(f"Checking for latest reel from @{clean_handle}...")

        # 1. Official Meta Business Discovery API
        ig_user_id = meta_ig_user_id or getattr(settings, "INSTAGRAM_USER_ID", getattr(settings, "IG_USER_ID", ""))
        access_token = meta_access_token or getattr(settings, "META_GRAPH_ACCESS_TOKEN", getattr(settings, "META_ACCESS_TOKEN", ""))

        if ig_user_id and access_token:
            result = self._fetch_via_business_discovery(clean_handle, ig_user_id, access_token)
            if result:
                return result

        # 2. Public Fallback
        logger.info(f"Falling back to public discovery for @{clean_handle}...")
        return self._fetch_via_public_fallback(clean_handle)

    def _fetch_via_business_discovery(self, target_username: str, ig_user_id: str, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Queries official Meta Graph API Business Discovery for competitor / target handle.
        """
        endpoint = f"https://graph.facebook.com/v27.0/{ig_user_id}"
        params = {
            "fields": f"business_discovery.username({target_username}){{media.limit(5){{id,caption,media_type,permalink,timestamp,media_url}}}}",
            "access_token": access_token
        }
        try:
            res = requests.get(endpoint, params=params, timeout=12)
            if res.status_code == 200:
                data = res.json()
                media_list = data.get("business_discovery", {}).get("media", {}).get("data", [])
                # Find the most recent VIDEO (Reel)
                for item in media_list:
                    if item.get("media_type") == "VIDEO":
                        shortcode = item.get("id")
                        permalink = item.get("permalink") or f"https://www.instagram.com/reel/{shortcode}/"
                        logger.info(f"Found Reel from @{target_username} via Business Discovery: {permalink}")
                        return {
                            "reel_id": shortcode,
                            "permalink": permalink,
                            "caption": item.get("caption", ""),
                            "timestamp": item.get("timestamp", ""),
                            "author": target_username,
                            "source_type": "meta_business_discovery"
                        }
            else:
                logger.warning(f"Business discovery for {target_username} failed with status {res.status_code}: {res.text[:150]}")
        except Exception as e:
            logger.error(f"Error querying Business Discovery for @{target_username}: {e}")
        return None

    def _fetch_via_public_fallback(self, target_username: str) -> Optional[Dict[str, Any]]:
        """
        Scrapes public profile web mirror (e.g. imginn / picuki) to extract the newest reel shortcode.
        """
        # Mirror: imginn
        try:
            url = f"https://imginn.com/{target_username}/"
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                # Look for video / reel links: /p/SHORTCODE/
                matches = re.findall(r'/p/([A-Za-z0-9_-]{10,12})/', res.text)
                if matches:
                    newest_shortcode = matches[0]
                    permalink = f"https://www.instagram.com/reel/{newest_shortcode}/"
                    logger.info(f"Extracted latest reel shortcode {newest_shortcode} via public mirror")
                    return {
                        "reel_id": newest_shortcode,
                        "permalink": permalink,
                        "caption": f"Latest video clip from @{target_username}",
                        "timestamp": str(int(time.time())),
                        "author": target_username,
                        "source_type": "public_mirror"
                    }
        except Exception as e:
            logger.debug(f"Imginn mirror attempt error: {e}")

        # Mirror: dumpor
        try:
            url = f"https://dumpor.io/v/{target_username}"
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                matches = re.findall(r'https?://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]{10,12})', res.text)
                if matches:
                    newest_shortcode = matches[0]
                    permalink = f"https://www.instagram.com/reel/{newest_shortcode}/"
                    logger.info(f"Extracted latest reel shortcode {newest_shortcode} via dumpor mirror")
                    return {
                        "reel_id": newest_shortcode,
                        "permalink": permalink,
                        "caption": f"Trending video from @{target_username}",
                        "timestamp": str(int(time.time())),
                        "author": target_username,
                        "source_type": "public_mirror"
                    }
        except Exception as e:
            logger.debug(f"Dumpor mirror attempt error: {e}")

        return None

    def download_reel(self, permalink: str, custom_id: str) -> Optional[Dict[str, Any]]:
        """
        Downloads high-res MP4 video from an Instagram Reel permalink using yt-dlp.
        """
        out_template = str(self.download_dir / f"{custom_id}_raw.%(ext)s")
        ydl_opts = {
            "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "match_filter": yt_dlp.utils.match_filter_func("duration <= 90"),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(permalink, download=True)
                if not info:
                    logger.warning(f"Could not extract info for {permalink}")
                    return None

                filepath = Path(ydl.prepare_filename(info))
                if not filepath.exists():
                    mp4_candidate = filepath.with_suffix(".mp4")
                    if mp4_candidate.exists():
                        filepath = mp4_candidate

                return {
                    "filepath": str(filepath),
                    "title": info.get("title") or info.get("description", "")[:60],
                    "description": info.get("description", ""),
                    "duration": info.get("duration", 0),
                    "author": info.get("uploader") or info.get("channel", "")
                }
        except Exception as e:
            logger.error(f"yt-dlp failed downloading {permalink}: {e}")
            return None
