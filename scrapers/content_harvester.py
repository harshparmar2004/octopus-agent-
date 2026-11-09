import os
import re
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List
import requests
import yt_dlp

from config import settings

logger = logging.getLogger("Harvester")

class ContentHarvester:
    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir = download_dir or settings.STORAGE_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

    def fetch_reddit_candidates(self, subreddit: str, limit: int = 10, time_filter: str = "day") -> List[Dict]:
        """
        Fetches top video candidates from a subreddit using public JSON endpoint.
        No Reddit API credentials required.
        """
        url = f"https://www.reddit.com/r/{subreddit}/top.json?t={time_filter}&limit={limit}"
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code != 200:
                logger.warning(f"Reddit r/{subreddit} returned status {res.status_code}")
                return []
            
            data = res.json()
            posts = data.get("data", {}).get("children", [])
            candidates = []

            for post in posts:
                p = post.get("data", {})
                title = p.get("title", "")
                author = p.get("author", "unknown")
                permalink = f"https://reddit.com{p.get('permalink', '')}"
                is_video = p.get("is_video", False)
                post_url = p.get("url", "")
                over_18 = p.get("over_18", False)

                if over_18:
                    continue

                # Check if it has direct video media or is a link to supported platforms
                if is_video or any(domain in post_url for domain in ["v.redd.it", "youtube.com", "youtu.be", "gfycat.com", "imgur.com"]):
                    candidates.append({
                        "id": p.get("id"),
                        "title": title,
                        "author": author,
                        "source_url": permalink if is_video else post_url,
                        "ups": p.get("ups", 0),
                        "subreddit": subreddit
                    })

            logger.info(f"Found {len(candidates)} candidate videos in r/{subreddit}")
            return candidates

        except Exception as e:
            logger.error(f"Error fetching r/{subreddit}: {e}")
            return []

    def download_video(self, source_url: str, custom_id: Optional[str] = None) -> Optional[Dict]:
        """
        Downloads the best MP4 video under 60 seconds from any URL using yt-dlp.
        Returns metadata including local file path.
        """
        out_template = str(self.download_dir / f"%(id)s_raw.%(ext)s")
        if custom_id:
            out_template = str(self.download_dir / f"{custom_id}_raw.%(ext)s")

        ydl_opts = {
            "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            # Ensure duration is max 90 seconds
            "match_filter": yt_dlp.utils.match_filter_func("duration <= 90"),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=True)
                if not info:
                    logger.warning("No video information extracted.")
                    return None

                video_id = info.get("id")
                filepath = Path(ydl.prepare_filename(info))
                # Ensure .mp4 extension
                if not filepath.exists():
                    mp4_candidate = filepath.with_suffix(".mp4")
                    if mp4_candidate.exists():
                        filepath = mp4_candidate

                return {
                    "video_id": video_id,
                    "filepath": str(filepath),
                    "title": info.get("title", ""),
                    "description": info.get("description", ""),
                    "duration": info.get("duration", 0),
                    "uploader": info.get("uploader", ""),
                    "source_url": source_url
                }

        except Exception as e:
            logger.error(f"Failed to download video from {source_url}: {e}")
            return None
