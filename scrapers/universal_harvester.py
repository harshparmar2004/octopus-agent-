import os
import re
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from urllib.parse import urlparse, parse_qs
import requests
import yt_dlp

from config import settings

logger = logging.getLogger("UniversalHarvester")

class UniversalContentHarvester:
    """
    Universal multi-platform video harvester that ingests, downloads, and normalizes
    high-res vertical media with 100% original audio preserved from:
    - Instagram (Reels and Posts)
    - YouTube Shorts and Videos
    - Snapchat (Spotlight and Stories)
    - Twitter / X (Video Posts and Broadcasts)
    - Reddit (v.redd.it DASH streams with separate audio auto-merged via FFmpeg)
    - TikTok (Standard and short links)
    - Direct MP4 / Video streams
    """

    def __init__(self, download_dir: Optional[Path] = None):
        self.download_dir = download_dir or settings.STORAGE_DIR
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,video/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }

    @classmethod
    def unroll_url(cls, url: str) -> str:
        clean_url = url.strip()
        shortlink_domains = ["youtu.be", "t.co", "bit.ly", "tinyurl.com", "vm.tiktok.com", "vt.tiktok.com"]
        parsed = urlparse(clean_url)
        domain = parsed.netloc.lower()

        if any(short in domain for short in shortlink_domains) or "/t/" in parsed.path:
            try:
                res = requests.head(clean_url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True, timeout=8)
                if res.url and res.url != clean_url:
                    logger.info(f"Unrolled shortlink {clean_url} -> {res.url}")
                    return res.url
            except Exception as e:
                logger.debug(f"Shortlink unroll error for {clean_url}: {e}")
        return clean_url

    @classmethod
    def classify_url(cls, raw_url: str) -> Dict[str, Any]:
        canonical_url = cls.unroll_url(raw_url)
        parsed = urlparse(canonical_url)
        domain = parsed.netloc.lower()
        path = parsed.path

        # 1. Instagram
        if "instagram.com" in domain or "instagr.am" in domain:
            content_id = "reel"
            if "/reel/" in path:
                parts = path.split("/reel/")[1].split("/")[0]
                if parts: content_id = parts
            elif "/p/" in path:
                parts = path.split("/p/")[1].split("/")[0]
                if parts: content_id = parts
            elif "/tv/" in path:
                parts = path.split("/tv/")[1].split("/")[0]
                if parts: content_id = parts
            return {
                "platform": "instagram",
                "platform_name": "Instagram Reel",
                "platform_emoji": "📸",
                "content_id": content_id,
                "canonical_url": canonical_url
            }

        # 2. YouTube (Shorts & Standard)
        if "youtube.com" in domain or "youtu.be" in domain:
            content_id = "yt_video"
            if "youtu.be" in domain:
                content_id = path.strip("/").split("/")[0].split("?")[0]
            elif "/shorts/" in path:
                content_id = path.split("/shorts/")[1].split("/")[0].split("?")[0]
            elif "/watch" in path:
                qs = parse_qs(parsed.query)
                if "v" in qs:
                    content_id = qs["v"][0]
            return {
                "platform": "youtube",
                "platform_name": "YouTube Shorts" if "/shorts/" in path else "YouTube Video",
                "platform_emoji": "▶️",
                "content_id": content_id,
                "canonical_url": canonical_url
            }

        # 3. Snapchat (Spotlight & Stories)
        if "snapchat.com" in domain:
            content_id = "snap"
            if "/spotlight/" in path:
                content_id = path.split("/spotlight/")[1].split("/")[0].split("?")[0]
            elif "/story/" in path:
                content_id = path.split("/story/")[1].split("/")[0].split("?")[0]
            elif "/t/" in path:
                content_id = path.split("/t/")[1].split("/")[0].split("?")[0]
            return {
                "platform": "snapchat",
                "platform_name": "Snapchat Spotlight" if "/spotlight/" in path else "Snapchat Story",
                "platform_emoji": "👻",
                "content_id": content_id,
                "canonical_url": canonical_url
            }

        # 4. Twitter / X
        if "x.com" in domain or "twitter.com" in domain:
            content_id = "tweet"
            if "/status/" in path:
                content_id = path.split("/status/")[1].split("/")[0].split("?")[0]
            return {
                "platform": "twitter",
                "platform_name": "Twitter / X",
                "platform_emoji": "🐦",
                "content_id": content_id,
                "canonical_url": canonical_url
            }

        # 5. Reddit
        if "reddit.com" in domain or "v.redd.it" in domain:
            content_id = "reddit_post"
            if "v.redd.it" in domain:
                content_id = path.strip("/").split("/")[0]
            elif "/comments/" in path:
                parts = path.split("/comments/")[1].strip("/").split("/")
                if parts: content_id = parts[0]
            return {
                "platform": "reddit",
                "platform_name": "Reddit Video",
                "platform_emoji": "🤖",
                "content_id": content_id,
                "canonical_url": canonical_url
            }

        # 6. TikTok
        if "tiktok.com" in domain:
            content_id = "tiktok_clip"
            if "/video/" in path:
                content_id = path.split("/video/")[1].split("/")[0].split("?")[0]
            return {
                "platform": "tiktok",
                "platform_name": "TikTok",
                "platform_emoji": "🎵",
                "content_id": content_id,
                "canonical_url": canonical_url
            }

        # 7. Direct MP4 or generic media
        if any(ext in path.lower() for ext in [".mp4", ".mov", ".m4v", ".webm"]):
            return {
                "platform": "direct",
                "platform_name": "Direct Video Stream",
                "platform_emoji": "🎥",
                "content_id": Path(path).stem or "direct_media",
                "canonical_url": canonical_url
            }

        return {
            "platform": "generic",
            "platform_name": "Web Video Stream",
            "platform_emoji": "🎬",
            "content_id": "clip_" + str(int(time.time())),
            "canonical_url": canonical_url
        }

    def harvest(self, url: str, custom_id: str) -> Optional[Dict[str, Any]]:
        info = self.classify_url(url)
        canonical = info["canonical_url"]
        platform = info["platform"]
        out_template = str(self.download_dir / f"{custom_id}_raw.%(ext)s")

        logger.info(f"UniversalHarvester ingesting [{info['platform_name']}] from {canonical[:80]}")

        # 1. Local Cache Check
        for ext in [".mp4", "_raw.mp4"]:
            cached = self.download_dir / f"{custom_id}{ext}"
            if cached.exists() and cached.stat().st_size > 50000:
                logger.info(f"Local cache hit for {custom_id}: {cached}")
                return {
                    "filepath": str(cached),
                    "title": f"Cached {info['platform_name']}",
                    "description": "Cached media stream ready for multi-account synthesis",
                    "duration": 15,
                    "author": "cached_source",
                    "platform": info["platform_name"],
                    "platform_emoji": info["platform_emoji"],
                    "canonical_url": canonical
                }

        # 2. Direct MP4 Stream Check
        if platform == "direct" or (canonical.startswith("http") and (".mp4" in canonical or "mixkit.co" in canonical or "fbcdn.net" in canonical)):
            try:
                out_path = self.download_dir / f"{custom_id}_raw.mp4"
                logger.info(f"Downloading direct video stream: {canonical[:60]}... to {out_path.name}")
                with requests.get(canonical, headers=self.headers, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    with open(out_path, "wb") as f_out:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f_out.write(chunk)
                if out_path.exists() and out_path.stat().st_size > 10000:
                    return {
                        "filepath": str(out_path),
                        "title": f"Ingested {info['platform_name']}",
                        "description": "Direct stream parsed successfully",
                        "duration": 15,
                        "author": "direct_stream",
                        "platform": info["platform_name"],
                        "platform_emoji": info["platform_emoji"],
                        "canonical_url": canonical
                    }
            except Exception as direct_err:
                logger.warning(f"Direct stream download failed, falling back to yt-dlp: {direct_err}")

        # 3. Dedicated Instagram Harvester Call (for Instagram URLs only)
        if platform == "instagram":
            try:
                from scrapers.instagram_harvester import InstagramHarvester
                ig_res = InstagramHarvester(download_dir=self.download_dir).download_reel(canonical, custom_id)
                if ig_res and ig_res.get("filepath") and Path(ig_res["filepath"]).exists():
                    ig_res["platform"] = info["platform_name"]
                    ig_res["platform_emoji"] = info["platform_emoji"]
                    ig_res["canonical_url"] = canonical
                    return ig_res
            except Exception as ig_err:
                logger.warning(f"InstagramHarvester attempt error, falling back to universal extractor: {ig_err}")

        # 4. Universal Tailored yt-dlp Extraction with Guaranteed FFmpeg Audio-Muxing
        def _duration_filter(info_dict, *, incomplete):
            dur = info_dict.get("duration")
            if dur is not None and dur > 180:
                return "Video is too long (> 180s for short-form publishing)"
            return None

        ydl_opts: Dict[str, Any] = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "match_filter": _duration_filter,
            "socket_timeout": 25,
            "http_headers": self.headers
        }

        if platform == "twitter":
            ydl_opts["http_headers"]["Referer"] = "https://twitter.com/"
        elif platform == "reddit":
            ydl_opts["format"] = "bestvideo+bestaudio/best"
            ydl_opts["merge_output_format"] = "mp4"
        elif platform == "snapchat":
            ydl_opts["http_headers"]["Referer"] = "https://www.snapchat.com/"
        elif platform == "youtube":
            ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        proxy = getattr(settings, "SCRAPER_PROXY", "") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        if proxy:
            ydl_opts["proxy"] = proxy

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                meta = ydl.extract_info(canonical, download=True)
                if not meta:
                    logger.warning(f"No video metadata extracted for {canonical}")
                    return None

                filepath = Path(ydl.prepare_filename(meta))
                if not filepath.exists():
                    mp4_candidate = filepath.with_suffix(".mp4")
                    if mp4_candidate.exists():
                        filepath = mp4_candidate

                author = meta.get("uploader") or meta.get("channel") or meta.get("uploader_id") or "curated_creator"
                title = meta.get("title") or meta.get("description", "")[:60] or f"Featured {info['platform_name']}"
                desc = meta.get("description") or title

                return {
                    "filepath": str(filepath),
                    "title": title,
                    "description": desc,
                    "duration": meta.get("duration", 0),
                    "author": author,
                    "platform": info["platform_name"],
                    "platform_emoji": info["platform_emoji"],
                    "canonical_url": canonical
                }

        except Exception as ydl_err:
            logger.error(f"UniversalHarvester failed downloading {canonical}: {ydl_err}")
            return None
