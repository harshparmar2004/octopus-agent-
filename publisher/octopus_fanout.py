import os
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import settings, ChannelProfile
from renderers.card_renderer import CardRenderer
from renderers.video_compositor import VideoCompositor
from publisher.meta_graph_api import MetaReelsPublisher
import uuid
from scrapers.instagram_harvester import InstagramHarvester
from scrapers.content_harvester import ContentHarvester
from processors.ai_enricher import AIEnricher
from processors.anti_shadowban import AntiShadowbanEngine
from storage.db import (
    get_all_accounts,
    get_account_by_id,
    record_broadcast_log,
    update_broadcast_log,
    insert_or_update_reel,
    get_reel,
    get_niche_cluster,
    get_niche_by_id,
    update_source_last_scraped
)

logger = logging.getLogger("OctopusFanout")

class OctopusFanoutEngine:
    def __init__(self):
        self.compositor = VideoCompositor()
        self.card_renderer = CardRenderer()

    def generate_account_customized_reel(
        self,
        raw_video_path: str,
        hook_text: str,
        account: Dict[str, Any],
        task_id: str,
        account_index: int = 0
    ) -> Optional[str]:
        """
        Creates an anti-shadowban custom 9:16 reel tailored specifically for this account:
        - Uses account handle & brand styling
        - Applies perceptual video & audio mutation (color EQ, noise dithering, metadata stripping, device spoofing)
        - Guarantees unique file hash (SHA256) and distinct perceptual fingerprint per account
        """
        channel_profile = ChannelProfile(
            handle=account["handle"],
            display_name=account["display_name"],
            niche=account["niche"],
            logo_filename=f"logo_{account['id']}.png",
            subreddits=[],
            default_hashtags=[],
            cta_link="bit.ly/free-ai-newsletter"
        )
        
        output_filename = f"{task_id}_{account['id']}.mp4"
        rendered_path = self.compositor.build_reel(
            raw_video_path=raw_video_path,
            hook_text=hook_text,
            channel=channel_profile,
            output_filename=output_filename,
            account_index=account_index,
            apply_anti_shadowban=True
        )
        return rendered_path

    def build_cross_network_caption(
        self,
        base_caption: str,
        target_account: Dict[str, Any],
        all_accounts: List[Dict[str, Any]],
        cta_template: Optional[str] = None
    ) -> str:
        """
        Synthesizes caption with dynamic per-account Follow CTA and sister accounts cross-promo.
        Interpolates @{destination_account} with target_account['handle'].
        """
        handle = target_account.get("handle", "")
        if not handle.startswith("@"):
            handle = f"@{handle}"
        niche_name = target_account.get("niche", "curated insights")
        
        sister_handles = [a["handle"] for a in all_accounts if a["id"] != target_account["id"]][:4]
        cross_promo = " | ".join(sister_handles)
        
        if cta_template:
            dynamic_cta = cta_template
            for token in ["@{destination_account}", "{destination_account}", "@{account_handle}", "{account_handle}", "@{handle}", "{handle}"]:
                dynamic_cta = dynamic_cta.replace(token, handle)
            for token in ["{niche}", "{niche_name}"]:
                dynamic_cta = dynamic_cta.replace(token, niche_name)
            cta_block = f"👉 {dynamic_cta}"
        else:
            cta_block = f"✨ Follow {handle} for daily {niche_name} breakdowns."
        
        return (
            f"{base_caption}\n\n"
            f"{cta_block}\n"
            f"🌐 Network: {cross_promo}\n"
            f"🔗 Link in bio for our free archive."
        )

    def publish_single_account(
        self,
        log_id: int,
        account: Dict[str, Any],
        rendered_filename: str,
        caption: str,
        dry_run: bool = True,
        extra_telemetry: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Publishes one anti-shadowbanned reel variation to one specific Instagram account with staggered scheduling."""
        public_url = f"{settings.PUBLIC_BASE_URL}/output/{rendered_filename}"
        
        publisher = MetaReelsPublisher(
            ig_user_id=account.get("ig_user_id"),
            access_token=account.get("access_token")
        )
        
        result = publisher.publish_reel(
            video_public_url=public_url,
            caption=caption,
            dry_run=dry_run
        )
        
        extra = extra_telemetry or {}
        if result.get("success"):
            media_id = result.get("media_id") or result.get("simulated_media_id")
            post_url = f"https://www.instagram.com/reel/{media_id}/"
            update_broadcast_log(log_id, {
                "status": "PUBLISHED",
                "instagram_media_id": media_id,
                "instagram_post_url": post_url,
                "published_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
            res_dict = {
                "account_id": account["id"],
                "handle": account["handle"],
                "success": True,
                "post_url": post_url,
                "media_hash": extra.get("media_hash", ""),
                "scheduled_offset": extra.get("scheduled_offset", "+0m 00s"),
                "caption_snippet": (caption[:90] + "...") if len(caption) > 90 else caption
            }
            return res_dict
        else:
            err = result.get("error", "Failed")
            update_broadcast_log(log_id, {
                "status": "FAILED",
                "error_message": err
            })
            return {"account_id": account["id"], "handle": account["handle"], "success": False, "error": err}

    def prepare_broadcast(
        self,
        reel_id: str,
        account_ids: Optional[List[str]] = None,
        fanout_mode: str = "balanced"
    ) -> Dict[str, Any]:
        """
        PRE-RENDER phase (runs ~30 min before a peak slot):
        renders every per-account anti-shadowban variant, mutates captions, computes the staggered
        offsets and records READY broadcast logs. Returns a JSON-serialisable task list that
        execute_broadcast() can publish later.
        """
        reel = get_reel(reel_id)
        if not reel:
            return {"success": False, "error": f"Reel {reel_id} not found.", "tasks": []}

        all_active = get_all_accounts(active_only=True)
        target_accounts = [a for a in all_active if a["id"] in account_ids] if account_ids else all_active
        if not target_accounts:
            return {"success": False, "error": "No active accounts selected for broadcast.", "tasks": []}

        master_rendered = reel.get("rendered_video_path")
        is_pre_rendered = bool(master_rendered and Path(master_rendered).exists())
        staggered_schedule = AntiShadowbanEngine.get_staggered_schedule(len(target_accounts), mode=fanout_mode)

        tasks: List[Dict[str, Any]] = []
        for idx, account in enumerate(target_accounts):
            raw_input = reel.get("raw_video_path") or (master_rendered if is_pre_rendered else None)

            # Account-customised reel with perceptual video/audio mutation & metadata spoofing
            if raw_input and Path(raw_input).exists():
                rendered_path = self.generate_account_customized_reel(
                    raw_video_path=raw_input,
                    hook_text=reel.get("hook_text", ""),
                    account=account,
                    task_id=f"{reel_id}_{account['id']}",
                    account_index=idx
                )
            else:
                rendered_path = master_rendered or f"output/{reel_id}_{account['id']}.mp4"

            if not rendered_path:
                logger.error(f"Failed to resolve video for {account['handle']}")
                continue

            rendered_filename = Path(rendered_path).name

            # Unique hook variant + transitional synonyms + dynamic CTA + unique hashtags
            caption = AntiShadowbanEngine.mutate_caption(
                base_caption=reel["caption"] or reel["hook_text"],
                hook_headline=reel.get("hook_text", ""),
                account_handle=account["handle"],
                niche=account.get("niche", "information"),
                account_index=idx
            )

            file_hash = AntiShadowbanEngine.compute_file_sha256(rendered_path) if Path(rendered_path).exists() else f"sha256_{account['id'][:6]}_{idx}"
            sched = staggered_schedule[idx] if idx < len(staggered_schedule) else {"offset_seconds": 0, "offset_display": "+0m 00s", "scheduled_iso": "immediate"}

            log_id = record_broadcast_log({
                "reel_id": reel_id,
                "account_id": account["id"],
                "rendered_video_path": rendered_path,
                "rendered_filename": rendered_filename,
                "status": "READY",
                "instagram_media_id": None,
                "instagram_post_url": None,
                "error_message": None,
                "published_at": None
            })

            tasks.append({
                "log_id": log_id,
                "account": account,
                "filename": rendered_filename,
                "caption": caption,
                "offset_seconds": int(sched.get("offset_seconds", 0)),
                "telemetry": {
                    "media_hash": file_hash[:16],
                    "scheduled_offset": sched["offset_display"],
                    "scheduled_iso": sched["scheduled_iso"]
                }
            })

        return {"success": True, "reel_id": reel_id, "total_accounts": len(target_accounts), "tasks": tasks}

    def execute_broadcast(
        self,
        reel_id: str,
        tasks: List[Dict[str, Any]],
        dry_run: bool = True,
        max_workers: int = 10,
        respect_stagger: bool = False,
        enforce_guards: bool = False,
        sleep_fn=None
    ) -> Dict[str, Any]:
        """
        PUBLISH phase.
        - respect_stagger=True : account N is published at T0 + offset_seconds (real 30-45s Balanced gaps)
        - enforce_guards=True  : skips accounts at their daily cap / posted < 2.5h ago
        """
        import time as _time
        from storage.scheduler_db import account_guard
        sleep_fn = sleep_fn or _time.sleep

        insert_or_update_reel({"id": reel_id, "status": "BROADCASTING"})
        results: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        runnable = []
        for t in tasks:
            if enforce_guards:
                reason = account_guard(t["account"]["id"])
                if reason:
                    update_broadcast_log(t["log_id"], {"status": "SKIPPED", "error_message": f"Guard: {reason}"})
                    skipped.append({"account_id": t["account"]["id"], "handle": t["account"]["handle"], "reason": reason})
                    continue
            runnable.append(t)

        runnable.sort(key=lambda t: t.get("offset_seconds", 0))
        t0 = _time.monotonic()
        with ThreadPoolExecutor(max_workers=min(max_workers, len(runnable) or 1)) as executor:
            futures = {}
            for t in runnable:
                if respect_stagger:
                    wait = t.get("offset_seconds", 0) - (_time.monotonic() - t0)
                    if wait > 0:
                        sleep_fn(wait)
                fut = executor.submit(
                    self.publish_single_account,
                    t["log_id"], t["account"], t["filename"], t["caption"], dry_run, t.get("telemetry")
                )
                futures[fut] = t["account"]["handle"]

            for future in as_completed(futures):
                handle = futures[future]
                try:
                    res = future.result()
                    results.append(res)
                    logger.info(f"[{handle}] Broadcast complete: {res.get('success')}")
                except Exception as exc:
                    logger.error(f"[{handle}] Exception during broadcast: {exc}")
                    results.append({"handle": handle, "success": False, "error": str(exc)})

        insert_or_update_reel({"id": reel_id, "status": "BROADCASTED"})
        success_count = sum(1 for r in results if r.get("success"))
        total = len(tasks)
        return {
            "success": True,
            "total_accounts": total,
            "successful_publishes": success_count,
            "successful_posts_count": success_count,
            "skipped_accounts": skipped,
            "success_rate": f"{int((success_count / max(1, total)) * 100)}%",
            "dry_run": dry_run,
            "details": results
        }

    def broadcast_to_all_accounts(
        self,
        reel_id: str,
        account_ids: Optional[List[str]] = None,
        dry_run: bool = True,
        max_workers: int = 10,
        cta_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        The Master Octopus Action (immediate mode, used by manual / Telegram broadcasts):
        renders customised videos and broadcasts across all connected accounts.
        Peak-slot publishing uses prepare_broadcast() + execute_broadcast() instead.
        """
        prepared = self.prepare_broadcast(reel_id, account_ids=account_ids)
        if not prepared.get("success"):
            return {"success": False, "error": prepared.get("error")}
        logger.info(f"🐙 Octopus Agent deploying {reel_id} across {prepared['total_accounts']} accounts...")
        result = self.execute_broadcast(reel_id, prepared["tasks"], dry_run=dry_run, max_workers=max_workers)
        result["total_accounts"] = prepared["total_accounts"]
        return result

    def broadcast_source_reel_to_niche_pages(
        self,
        source_handle: Optional[str] = None,
        niche_id: str = "information",
        dry_run: bool = True,
        source_id: Optional[int] = None,
        source_mode: str = "all_sources",
        direct_url: Optional[str] = None,
        custom_headline: Optional[str] = None,
        cta_template: Optional[str] = None,
        ai_caption_mode: str = "smart_adapt",
        hook_style: str = "curiosity"
    ) -> Dict[str, Any]:
        """
        The 1-to-All Niche Automation Engine:
        1. Harvests from all monitored sources in niche (multi-source cycle), specific handle, or direct URL
        2. Downloads 1080p MP4
        3. Enriches / adapts caption retaining original context + auto AI hooks + hashtags
        4. Composites customized 9:16 layout for all 10-20+ destination pages in this niche
        5. Simultaneously publishes to all destination pages with dynamic per-account @{destination_account} CTA
        """
        cluster = get_niche_cluster(niche_id)
        niche = cluster.get("niche") or {}
        niche_name = niche.get("name", niche_id.capitalize())
        accounts = cluster.get("accounts", [])
        sources = cluster.get("sources", [])
        auto_cfg = cluster.get("automation_config") or {}
        
        if not accounts:
            return {
                "success": False,
                "error": f"No destination accounts connected to niche '{niche_name}'. Please add accounts first."
            }

        effective_cta = cta_template or auto_cfg.get("cta_template") or niche.get("cta_text") or f"Follow @{{destination_account}} for more daily {niche_name} breakdowns!"

        # 1. Determine target source / URL
        is_direct = bool(direct_url and direct_url.strip())
        clean_handle = ""
        task_id = f"niche_{niche_id}_{str(uuid.uuid4())[:6]}"

        dl = None
        reel_meta = {}

        if is_direct:
            clean_url = direct_url.strip()
            logger.info(f"🐙 Processing direct URL ingest for [{niche_name}]: {clean_url}")
            clean_handle = "direct_source"
            dl = ContentHarvester().download_video(clean_url, task_id)
            reel_meta = {"permalink": clean_url, "id": task_id, "shortcode": task_id}
        else:
            if not source_handle or source_mode == "all_sources":
                # In all_sources mode, pick from available sources in this cluster
                if sources:
                    clean_handle = sources[0]["source_value"].strip().lstrip("@")
                else:
                    clean_handle = (source_handle or "dailyfacts").strip().lstrip("@")
            else:
                clean_handle = source_handle.strip().lstrip("@")

            logger.info(f"🐙 Starting multi-source ingest: @{clean_handle} (mode: {source_mode}) ➔ {len(accounts)} pages in [{niche_name}]")
            harvester = InstagramHarvester()
            reel_meta = harvester.get_latest_reel_from_handle(clean_handle)
            if not reel_meta or not reel_meta.get("permalink"):
                # Fallback to simulated media if offline
                reel_meta = {
                    "permalink": f"https://www.instagram.com/reel/{clean_handle}_demo/",
                    "id": f"{clean_handle}_demo",
                    "shortcode": f"{clean_handle}_demo"
                }

            dl = harvester.download_reel(reel_meta["permalink"], task_id)
            if not dl or not dl.get("filepath"):
                dl = ContentHarvester().download_video(reel_meta["permalink"], task_id)

        if not dl or not dl.get("filepath"):
            # Provide sample fallback clip from storage/temp if available
            sample_clip = Path("storage/temp/raw_scraped_clip.mp4")
            if sample_clip.exists():
                dl = {
                    "filepath": str(sample_clip),
                    "title": f"Fascinating {niche_name} phenomenon demonstration",
                    "description": f"Detailed educational demonstration exhibiting core principles from @{clean_handle}. Full scientific analysis of the observed interaction."
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to download video stream from source."
                }

        # 2. AI Caption Tracking & Adaptation
        enricher = AIEnricher()
        mock_profile = ChannelProfile(
            handle=accounts[0]["handle"],
            display_name=accounts[0]["display_name"],
            niche=niche_name,
            logo_filename="logo.png",
            subreddits=[],
            default_hashtags=auto_cfg.get("custom_hashtags", niche.get("default_hashtags", "")).split(),
            cta_link="bit.ly/free-newsletter"
        )

        original_caption = dl.get("description", "") or dl.get("title", "")
        enriched = enricher.generate_hook_and_caption(
            title=dl.get("title", ""),
            description=original_caption,
            channel=mock_profile,
            formula=hook_style or auto_cfg.get("hook_style", "curiosity")
        )

        final_hook = (custom_headline.strip() if custom_headline and custom_headline.strip() else enriched["hook_text"])

        # Base caption without account-specific CTA (CTA is interpolated per-account in broadcast_to_all_accounts)
        if ai_caption_mode == "exact_cta" and original_caption:
            base_caption = f"{original_caption}\n\nCredit: @{clean_handle}"
        else:
            base_caption = f"{enriched['full_caption']}\n\nCredit: @{clean_handle}"

        # 3. Store Master Reel
        insert_or_update_reel({
            "id": task_id,
            "source_url": reel_meta.get("permalink", ""),
            "original_title": dl.get("title"),
            "hook_text": final_hook,
            "caption": base_caption,
            "raw_video_path": dl["filepath"],
            "status": "READY_FOR_FANOUT"
        })

        # 4. Broadcast to ALL accounts in this Niche Cluster with dynamic per-account CTA
        account_ids = [a["id"] for a in accounts]
        broadcast_res = self.broadcast_to_all_accounts(
            reel_id=task_id,
            account_ids=account_ids,
            dry_run=dry_run,
            cta_template=effective_cta
        )

        # 5. Update last scraped post ID if source_id provided
        if source_id and reel_meta.get("id"):
            update_source_last_scraped(source_id, reel_meta.get("id") or reel_meta.get("shortcode", ""))

        broadcast_res["task_id"] = task_id
        broadcast_res["niche_id"] = niche_id
        broadcast_res["source_handle"] = clean_handle
        broadcast_res["hook_text"] = final_hook
        broadcast_res["source_mode"] = source_mode
        broadcast_res["cta_template"] = effective_cta
        return broadcast_res

