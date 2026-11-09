import os
import sys
import time
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import settings, ChannelProfile
from scrapers.instagram_harvester import InstagramHarvester
from scrapers.content_harvester import ContentHarvester
from processors.ai_enricher import AIEnricher
from renderers.video_compositor import VideoCompositor
from publisher.meta_graph_api import MetaReelsPublisher
from publisher.octopus_fanout import OctopusFanoutEngine
from bot.octopus_telegram_bot import OctopusTelegramBot
from storage.db import (
    init_octopus_db,
    get_all_accounts,
    get_account_by_id,
    get_active_sources_by_type,
    update_source_last_scraped,
    insert_or_update_reel,
    is_source_already_scraped
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("OctopusDaemon")

class Octopus24x7Daemon:
    def __init__(self):
        init_octopus_db()
        self.ig_harvester = InstagramHarvester()
        self.content_harvester = ContentHarvester()
        self.enricher = AIEnricher()
        self.compositor = VideoCompositor()
        self.fanout = OctopusFanoutEngine()
        self.telegram = OctopusTelegramBot()

    def check_monitored_instagram_handles(self, dry_run: bool = True) -> List[Dict[str, Any]]:
        """
        Polls all active monitored Instagram handles:
        1. Checks newest reel
        2. Detects if it is new
        3. Scrapes & re-templates with our logo and typography
        4. Auto-posts to target account or entire Octopus network
        """
        logger.info("?? [DAEMON] Checking monitored Instagram handles for newest reels...")
        sources = get_active_sources_by_type("instagram_handle")
        results = []

        for source in sources:
            source_id = source["id"]
            handle = source["source_value"]
            category = source["category"]
            target_acc_id = source.get("target_account_id") or category
            last_scraped_id = source.get("last_scraped_post_id")
            auto_publish = bool(source.get("auto_publish", 1))

            logger.info(f"Checking @{handle} (Category: {category}, Target Acc: {target_acc_id})...")

            try:
                # 1. Discover newest reel
                latest_reel = self.ig_harvester.get_latest_reel_from_handle(handle)
                if not latest_reel:
                    logger.info(f"No reels currently discoverable for @{handle}.")
                    continue

                reel_id = latest_reel["reel_id"]
                permalink = latest_reel["permalink"]

                # 2. Check if already processed
                if (last_scraped_id and str(reel_id) == str(last_scraped_id)) or is_source_already_scraped(permalink):
                    logger.info(f"Reel {reel_id} from @{handle} already processed. Skipping.")
                    continue

                logger.info(f"? NEW Reel detected from @{handle}: {permalink} (ID: {reel_id})")

                # 3. Download raw video
                task_id = f"ig_{clean_handle(handle)}_{str(uuid.uuid4())[:6]}"
                download_res = self.ig_harvester.download_reel(permalink, custom_id=task_id)
                if not download_res or not download_res.get("filepath"):
                    logger.warning(f"Could not download video for {permalink}. Trying generic harvester...")
                    download_res = self.content_harvester.download_video(permalink, custom_id=task_id)

                if not download_res or not download_res.get("filepath"):
                    logger.error(f"Failed to download media for {permalink}")
                    continue

                raw_video_path = download_res["filepath"]
                orig_title = download_res.get("title") or latest_reel.get("caption", "")[:60]
                orig_desc = download_res.get("description") or latest_reel.get("caption", "")

                # 4. Resolve destination account
                target_account = get_account_by_id(target_acc_id)
                if not target_account:
                    all_accs = get_all_accounts(active_only=True)
                    target_account = all_accs[0] if all_accs else None

                if not target_account:
                    logger.error("No active destination accounts found in database.")
                    continue

                channel_profile = ChannelProfile(
                    handle=target_account["handle"],
                    display_name=target_account["display_name"],
                    niche=target_account["niche"],
                    logo_filename=f"logo_{target_account['id']}.png",
                    subreddits=[],
                    default_hashtags=[],
                    cta_link="bit.ly/free-ai-newsletter"
                )

                # 5. Synthesize AI Hook & Educational Caption with Original Credit
                logger.info(f"Synthesizing AI hook and caption for @{target_account['handle']}...")
                enriched = self.enricher.generate_hook_and_caption(orig_title, orig_desc, channel_profile)
                hook_text = enriched["hook_text"]
                caption = (
                    f"{enriched['full_caption']}\n\n"
                    f"?? Video clip via @{handle}\n"
                    f"? Follow {target_account['handle']} for daily {target_account['niche']}."
                )

                # 6. Composite 9:16 Video with our Template Logo & Branding
                output_filename = f"{task_id}_{target_account['id']}.mp4"
                rendered_path = self.compositor.build_reel(
                    raw_video_path=raw_video_path,
                    hook_text=hook_text,
                    channel=channel_profile,
                    output_filename=output_filename,
                    credit_handle=handle
                )

                if not rendered_path:
                    logger.error(f"Video composition failed for {output_filename}")
                    continue

                # 7. Record in Master Reels Tracker
                insert_or_update_reel({
                    "id": task_id,
                    "source_url": permalink,
                    "original_title": orig_title,
                    "hook_text": hook_text,
                    "caption": caption,
                    "raw_video_path": raw_video_path,
                    "rendered_video_path": rendered_path,
                    "rendered_filename": output_filename,
                    "status": "READY_FOR_PUBLISH"
                })

                # 8. Auto-Post / Publish
                pub_result = None
                if auto_publish:
                    logger.info(f"Auto-publishing {task_id} to {target_account['handle']}...")
                    public_url = f"{settings.PUBLIC_BASE_URL}/output/{output_filename}"
                    publisher = MetaReelsPublisher(
                        ig_user_id=target_account.get("ig_user_id"),
                        access_token=target_account.get("access_token")
                    )
                    pub_result = publisher.publish_reel(
                        video_public_url=public_url,
                        caption=caption,
                        dry_run=dry_run
                    )
                    if pub_result.get("success"):
                        insert_or_update_reel({"id": task_id, "status": "PUBLISHED"})

                # 9. Update last scraped marker in DB
                update_source_last_scraped(source_id, str(reel_id))

                # 10. Send Telegram Alert & Preview
                if self.telegram.is_configured():
                    accounts = get_all_accounts(active_only=True)
                    self.telegram.send_broadcast_preview(
                        video_path=rendered_path,
                        hook_text=f"Scraped from @{handle}: {hook_text}",
                        reel_id=task_id,
                        accounts=accounts
                    )

                results.append({
                    "task_id": task_id,
                    "source_handle": handle,
                    "target_account": target_account["handle"],
                    "rendered_path": rendered_path,
                    "published": auto_publish,
                    "dry_run": dry_run
                })
                logger.info(f"? Successfully finished cycle for @{handle} -> {target_account['handle']}!")

            except Exception as e:
                logger.error(f"Error processing source @{handle}: {e}", exc_info=True)

        return results

    def run_niche_pod_cycle(self, niche_id: str, dry_run: bool = True) -> List[Dict[str, Any]]:
        """Scans sources for a specific niche pod and fans out any fresh reel to all connected destination pages."""
        from storage.db import get_niche_cluster
        cluster = get_niche_cluster(niche_id)
        sources = cluster.get("sources", [])
        results = []
        for s in sources:
            if s.get("source_type") == "instagram_handle":
                handle = s["source_value"]
                logger.info(f"Checking niche [{niche_id}] source @{handle}...")
                res = self.fanout.broadcast_source_reel_to_niche_pages(
                    source_handle=handle,
                    niche_id=niche_id,
                    dry_run=dry_run,
                    source_id=s["id"]
                )
                if res.get("success"):
                    results.append(res)
                    logger.info(f"Broadcasted reel from @{handle} to all pages in [{niche_id}]")
                    break
        return results

    def run_full_cycle(self, dry_run: bool = True):
        logger.info("=== Running Octopus 24/7 Automation Cycle ===")
        # 1. Instagram Handles
        ig_results = self.check_monitored_instagram_handles(dry_run=dry_run)
        logger.info(f"Cycle completed. Processed {len(ig_results)} new Instagram reels.")

def clean_handle(h: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "", h.lstrip("@"))

def start_daemon():
    init_octopus_db()
    daemon = Octopus24x7Daemon()
    scheduler = BlockingScheduler()

    # Schedule run every 2 hours
    scheduler.add_job(
        daemon.run_full_cycle,
        trigger=IntervalTrigger(hours=2),
        args=[True],  # dry_run=True by default; change to False when live
        id="octopus_auto_cycle",
        name="Octopus 24/7 Reels Monitor & Publisher"
    )

    logger.info("?? Octopus 24/7 Automation Daemon started. Scheduled intervals active.")
    # Run first immediate pass
    daemon.run_full_cycle(dry_run=True)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Daemon stopped by operator.")

if __name__ == "__main__":
    start_daemon()
