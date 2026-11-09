import os
import sys
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from config import settings, ChannelProfile
from scrapers.content_harvester import ContentHarvester
from processors.ai_enricher import AIEnricher
from renderers.video_compositor import VideoCompositor
from publisher.meta_graph_api import MetaReelsPublisher
from bot.telegram_reviewer import TelegramReviewer
from storage.db import (
    init_tracker_db,
    insert_or_update_reel,
    is_source_already_scraped,
    get_reel_by_id
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Pipeline")

class ReelsAutomationPipeline:
    def __init__(self, channel_key: str = "quantum"):
        init_tracker_db()
        self.channel_key = channel_key
        self.channel = settings.get_channel(channel_key)
        self.harvester = ContentHarvester()
        self.enricher = AIEnricher()
        self.compositor = VideoCompositor()
        self.publisher = MetaReelsPublisher()
        self.reviewer = TelegramReviewer()

    def process_url(self, source_url: str, auto_publish: bool = False, dry_run: bool = True) -> Optional[Dict[str, Any]]:
        """
        Full tracked execution for any media link:
        1. Download raw video via yt-dlp -> records status 'HARVESTED'
        2. Synthesize AI hook & caption
        3. Composite 9:16 card reel -> records status 'RENDERED'
        4. Optional Telegram review push
        5. Optional Meta Graph API publication -> records status 'PUBLISHED'
        """
        task_id = f"reel_{str(uuid.uuid4())[:8]}"
        logger.info(f"[{task_id}] Ingesting source: {source_url} for {self.channel.handle}")

        # Record initial ingest
        tracker_record = {
            "id": task_id,
            "channel": self.channel_key,
            "source_url": source_url,
            "original_title": None,
            "hook_text": None,
            "caption": None,
            "raw_video_path": None,
            "rendered_video_path": None,
            "rendered_filename": None,
            "status": "HARVESTING",
            "instagram_media_id": None,
            "instagram_post_url": None,
            "error_message": None,
            "published_at": None
        }
        insert_or_update_reel(tracker_record)

        # 1. Download
        download_meta = self.harvester.download_video(source_url, custom_id=task_id)
        if not download_meta:
            tracker_record["status"] = "FAILED"
            tracker_record["error_message"] = "yt-dlp failed to download or duration exceeded 90s."
            insert_or_update_reel(tracker_record)
            return None

        raw_filepath = download_meta["filepath"]
        title = download_meta["title"]
        desc = download_meta["description"]
        
        tracker_record.update({
            "original_title": title,
            "raw_video_path": raw_filepath,
            "status": "HARVESTED"
        })
        insert_or_update_reel(tracker_record)

        # 2. AI Hook & Caption Generation
        logger.info(f"[{task_id}] Synthesizing AI hook and caption...")
        enriched = self.enricher.generate_hook_and_caption(title, desc, self.channel)
        hook_text = enriched["hook_text"]
        full_caption = enriched["full_caption"]

        tracker_record.update({
            "hook_text": hook_text,
            "caption": full_caption,
            "status": "ENRICHED"
        })
        insert_or_update_reel(tracker_record)

        # 3. Video Composition
        output_filename = f"{task_id}_{self.channel.display_name.lower()}.mp4"
        logger.info(f"[{task_id}] Compositing 9:16 card template...")
        rendered_reel_path = self.compositor.build_reel(
            raw_video_path=raw_filepath,
            hook_text=hook_text,
            channel=self.channel,
            output_filename=output_filename
        )

        if not rendered_reel_path:
            tracker_record["status"] = "FAILED"
            tracker_record["error_message"] = "FFmpeg composition failed."
            insert_or_update_reel(tracker_record)
            return None

        tracker_record.update({
            "rendered_video_path": rendered_reel_path,
            "rendered_filename": output_filename,
            "status": "READY_FOR_PUBLISH"
        })
        insert_or_update_reel(tracker_record)

        # 4. Telegram Interactive Review
        if self.reviewer.is_configured():
            self.reviewer.send_for_review(
                video_path=rendered_reel_path,
                caption=full_caption,
                hook_text=hook_text,
                candidate_id=task_id
            )

        # 5. Meta Publishing
        publish_result = None
        if auto_publish:
            publish_result = self.publish_existing_reel(task_id, dry_run=dry_run)

        return tracker_record

    def publish_existing_reel(self, task_id: str, dry_run: bool = False) -> Dict[str, Any]:
        """Publishes an already rendered reel to Meta Graph API and updates tracker."""
        reel = get_reel_by_id(task_id)
        if not reel:
            return {"success": False, "error": "Reel ID not found."}

        filename = reel.get("rendered_filename")
        caption = reel.get("caption")
        public_url = f"{settings.PUBLIC_BASE_URL}/output/{filename}"

        pub_res = self.publisher.publish_reel(
            video_public_url=public_url,
            caption=caption,
            dry_run=dry_run
        )

        if pub_res.get("success"):
            media_id = pub_res.get("media_id") or pub_res.get("simulated_media_id")
            post_url = f"https://www.instagram.com/reel/{media_id}/"
            reel.update({
                "status": "PUBLISHED",
                "instagram_media_id": media_id,
                "instagram_post_url": post_url,
                "published_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
            insert_or_update_reel(reel)
        else:
            reel["status"] = "PUBLISH_FAILED"
            reel["error_message"] = pub_res.get("error", "Unknown Meta Graph API error.")
            insert_or_update_reel(reel)

        return pub_res

    def run_harvest_and_process(self, subreddit: Optional[str] = None, limit: int = 3, auto_publish: bool = False, dry_run: bool = True):
        """Scrapes candidates from a subreddit or all channel subreddits."""
        subs_to_scan = [subreddit] if subreddit else self.channel.subreddits

        for sub in subs_to_scan:
            logger.info(f"Scanning r/{sub} for {self.channel.handle}...")
            candidates = self.harvester.fetch_reddit_candidates(sub, limit=limit)
            for c in candidates:
                url = c["source_url"]
                if is_source_already_scraped(url):
                    logger.info(f"Skipping already-tracked source: {url}")
                    continue

                logger.info(f"Processing candidate: {c['title']} ({url})")
                res = self.process_url(source_url=url, auto_publish=auto_publish, dry_run=dry_run)
                if res and res["status"] in ["READY_FOR_PUBLISH", "PUBLISHED"]:
                    return res

        return None

if __name__ == "__main__":
    channel_arg = sys.argv[1] if len(sys.argv) > 1 else "quantum"
    pipeline = ReelsAutomationPipeline(channel_key=channel_arg)
    
    if len(sys.argv) > 2:
        target_url = sys.argv[2]
        result = pipeline.process_url(target_url, auto_publish=True, dry_run=True)
    else:
        result = pipeline.run_harvest_and_process(limit=3, auto_publish=True, dry_run=True)
        
    print("\n--- Pipeline Result ---")
    print(result)
