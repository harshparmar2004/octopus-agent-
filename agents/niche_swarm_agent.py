import os
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor

from config import settings, ChannelProfile
from scrapers.instagram_harvester import InstagramHarvester
from scrapers.content_harvester import ContentHarvester
from processors.ai_enricher import AIEnricher
from renderers.video_compositor import VideoCompositor
from publisher.octopus_fanout import OctopusFanoutEngine
from storage.db import (
    get_niche_by_id,
    get_niche_cluster,
    get_account_by_id,
    insert_or_update_reel,
    update_source_last_scraped,
    is_source_already_scraped
)

logger = logging.getLogger("NichePodAgent")

class NichePodAgent:
    """
    Autonomous Agent dedicated to an individual Niche Pod.
    Executes in parallel with all other niche agents across the swarm.
    """
    def __init__(self, niche_id: str):
        self.niche_id = niche_id
        self.cluster = get_niche_cluster(niche_id)
        self.niche_meta = self.cluster.get("niche") or {"id": niche_id, "name": niche_id.capitalize()}
        self.name = self.niche_meta.get("name", niche_id.capitalize())
        self.brand_color = self.niche_meta.get("brand_color", "#ea580c")
        self.avatar_icon = self.niche_meta.get("avatar_icon", "📁")
        self.accounts = self.cluster.get("accounts", [])
        self.sources = self.cluster.get("sources", [])
        self.automation_config = self.cluster.get("automation_config", {})

        # Subsystems
        self.harvester = InstagramHarvester()
        self.content_harvester = ContentHarvester()
        self.enricher = AIEnricher()
        self.compositor = VideoCompositor()
        self.fanout = OctopusFanoutEngine()

        # Telemetry & Status
        self.status = "IDLE"  # IDLE, SCANNING, PROCESSING, PUBLISHING, COMPLETED, ERROR
        self.last_run_time = None
        self.last_stats = {}

    def scan_sources_concurrently(self, max_threads: int = 5) -> List[Dict[str, Any]]:
        """
        Scans all 20-30 source handles in this niche pod concurrently using a thread pool.
        """
        if not self.sources:
            return []

        discovered_reels = []

        def check_source(source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            handle = source.get("source_value", "").strip()
            if not handle:
                return None
            try:
                latest_reel = self.harvester.get_latest_reel_from_handle(handle)
                if not latest_reel:
                    return None

                reel_id = latest_reel.get("reel_id")
                permalink = latest_reel.get("permalink")
                last_scraped = source.get("last_scraped_post_id")

                if (last_scraped and str(reel_id) == str(last_scraped)) or is_source_already_scraped(permalink):
                    return None

                return {
                    "source": source,
                    "handle": handle,
                    "latest_reel": latest_reel
                }
            except Exception as e:
                logger.error(f"[{self.name}] Error checking source @{handle}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            results = list(executor.map(check_source, self.sources))

        for r in results:
            if r:
                discovered_reels.append(r)

        return discovered_reels

    def run_cycle(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Executes one full autonomous cycle for this niche:
        Scan Sources ➔ Deduplicate ➔ Download ➔ Compose ➔ LLM Copy ➔ Multi-Page Fan-Out.
        """
        start_time = time.time()
        self.status = "SCANNING"
        logger.info(f"🐙 [{self.name}] Agent cycle started with {len(self.sources)} sources and {len(self.accounts)} accounts.")

        stats = {
            "niche_id": self.niche_id,
            "niche_name": self.name,
            "sources_scanned": len(self.sources),
            "new_reels_found": 0,
            "processed_reels": [],
            "published_posts_count": 0,
            "duration_seconds": 0.0,
            "status": "SUCCESS"
        }

        try:
            # 1. Scan sources
            new_items = self.scan_sources_concurrently(max_threads=5)
            stats["new_reels_found"] = len(new_items)

            if not new_items:
                logger.info(f"[{self.name}] No new reels detected across {len(self.sources)} sources.")
                self.status = "IDLE"
                stats["duration_seconds"] = round(time.time() - start_time, 2)
                self.last_stats = stats
                return stats

            self.status = "PROCESSING"
            # Process up to 2 newest viral reels per cycle to prevent rate-limit flooding
            for item in new_items[:2]:
                source = item["source"]
                handle = item["handle"]
                reel_meta = item["latest_reel"]
                permalink = reel_meta["permalink"]
                reel_id = reel_meta["reel_id"]

                logger.info(f"[{self.name}] Ingesting new reel: {permalink} from @{handle}")
                task_id = f"swarm_{self.niche_id}_{str(uuid.uuid4())[:6]}"

                # Download media (yt-dlp with proxy & cookie support)
                dl_res = self.harvester.download_reel(permalink, custom_id=task_id)
                if not dl_res or not dl_res.get("filepath"):
                    dl_res = self.content_harvester.download_video(permalink, custom_id=task_id)

                if not dl_res or not dl_res.get("filepath"):
                    logger.warning(f"[{self.name}] Media download failed for {permalink}")
                    continue

                raw_video_path = dl_res["filepath"]
                orig_title = dl_res.get("title") or reel_meta.get("caption", "")[:60]
                orig_desc = dl_res.get("description") or reel_meta.get("caption", "")

                # Destination branding channel
                primary_acc = self.accounts[0] if self.accounts else {
                    "id": self.niche_id,
                    "handle": f"@{self.niche_id}.hub",
                    "display_name": self.name,
                    "niche": self.name
                }

                ch = ChannelProfile(
                    handle=primary_acc.get("handle", f"@{self.niche_id}"),
                    display_name=primary_acc.get("display_name", self.name),
                    niche=self.name,
                    logo_filename=f"logo_{primary_acc.get('id', self.niche_id)}.png",
                    subreddits=[], default_hashtags=[], cta_link="bit.ly/free-ai-newsletter"
                )

                # Gemini AI Copywriting
                enriched = self.enricher.generate_hook_and_caption(orig_title, orig_desc, ch)
                hook_text = enriched.get("hook_text", orig_title)
                hashtags_str = self.niche_meta.get("default_hashtags") or "#viral #reels #trending"
                cta_str = self.niche_meta.get("cta_text") or f"Follow for daily {self.name}!"
                full_caption = f"{hook_text}\n\n{enriched.get('full_caption', '')}\n\n{cta_str}\n\n{hashtags_str}\n\nCredit: @{handle.lstrip('@')}"

                # VideoToolbox / FFmpeg Rendering
                rendered_filename = f"{task_id}.mp4"
                rendered_path = self.compositor.build_reel(
                    raw_video_path=raw_video_path,
                    hook_text=hook_text,
                    channel=ch,
                    output_filename=rendered_filename,
                    credit_handle=handle
                )

                if not rendered_path:
                    logger.warning(f"[{self.name}] FFmpeg rendering failed for {task_id}")
                    continue

                # Save in master tracker
                insert_or_update_reel({
                    "id": task_id,
                    "source_url": permalink,
                    "original_title": orig_title,
                    "hook_text": hook_text,
                    "caption": full_caption,
                    "raw_video_path": raw_video_path,
                    "rendered_video_path": rendered_path,
                    "rendered_filename": rendered_filename,
                    "status": "READY_FOR_PUBLISH"
                })

                # Multi-Page Fan-Out Broadcast across all accounts in this niche
                self.status = "PUBLISHING"
                target_acc_ids = [a["id"] for a in self.accounts]
                fanout_res = self.fanout.broadcast_to_all_accounts(
                    reel_id=task_id,
                    account_ids=target_acc_ids if target_acc_ids else None,
                    dry_run=dry_run
                )

                pub_count = fanout_res.get("successful_posts_count", 0)
                stats["published_posts_count"] += pub_count
                stats["processed_reels"].append({
                    "reel_id": task_id,
                    "source_url": permalink,
                    "hook": hook_text,
                    "published_count": pub_count,
                    "fanout_result": fanout_res
                })

                update_source_last_scraped(source.get("id"), str(reel_id))

            self.status = "COMPLETED"
        except Exception as e:
            logger.error(f"[{self.name}] Agent cycle exception: {e}", exc_info=True)
            self.status = "ERROR"
            stats["status"] = f"ERROR: {str(e)}"

        stats["duration_seconds"] = round(time.time() - start_time, 2)
        self.last_run_time = time.time()
        self.last_stats = stats
        logger.info(f"✅ [{self.name}] Cycle finished in {stats['duration_seconds']}s. Published: {stats['published_posts_count']} posts.")
        return stats
