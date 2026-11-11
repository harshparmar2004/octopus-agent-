"""
PeakTimeScheduler: posts the AI-selected best reel of every niche at Instagram peak hours (IST).

Timeline for each niche & slot (e.g. 18:00 IST):
  all day      : HarvestWorker fills the Candidate Pool every ~75 min (staggered per niche)
  T-30 min     : prepare_slot  -> rank pool, download best reel, AI hook/caption, master render,
                                  pre-render 20 per-account anti-shadowban variants, Telegram preview
  T (+-jitter) : publish_slot  -> Balanced staggered fanout (30-45s gaps) with per-account guards
  03:00 daily  : housekeeping  -> expire stale candidates, delete media older than 48h

Each niche gets a deterministic +-jitter (default 8 min) per slot so 20 niches never fire at the
exact same second. Slots missed by more than 15 min (server down) are SKIPPED, never posted off-peak.
"""
import hashlib
import json
import logging
import os
import random
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from config import settings, ChannelProfile
from storage.db import get_all_niches, get_niche_cluster, insert_or_update_reel
from storage.scheduler_db import (
    create_slot_run,
    expire_stale_candidates,
    from_iso,
    get_candidate,
    get_niche_schedule,
    get_slot_run,
    get_slot_runs,
    to_iso,
    update_candidate,
    update_slot_run,
    utcnow,
)
from processors.reel_scorer import ReelScorer
from agents.harvest_worker import HarvestWorker

logger = logging.getLogger("PeakTimeScheduler")

PRERENDER_LEAD_MINUTES = 30
MISFIRE_GRACE_MINUTES = 15
HARVEST_INTERVAL_MINUTES = 75
MEDIA_RETENTION_HOURS = 48


def slot_jitter_seconds(niche_id: str, slot_date: str, slot_time: str, jitter_minutes: int) -> int:
    """Deterministic per (niche, date, slot) jitter so restarts never re-roll the posting time."""
    if jitter_minutes <= 0:
        return 0
    seed = int(hashlib.sha256(f"{niche_id}|{slot_date}|{slot_time}".encode()).hexdigest()[:12], 16)
    return random.Random(seed).randint(-jitter_minutes * 60, jitter_minutes * 60)


def compute_scheduled_for(niche_id: str, local_day: date, slot_time: str, tz_name: str, jitter_minutes: int) -> datetime:
    tz = ZoneInfo(tz_name)
    hh, mm = (int(x) for x in slot_time.split(":"))
    local_dt = datetime(local_day.year, local_day.month, local_day.day, hh, mm, tzinfo=tz)
    jitter = slot_jitter_seconds(niche_id, local_day.isoformat(), slot_time, jitter_minutes)
    return (local_dt + timedelta(seconds=jitter)).astimezone(timezone.utc)


class PeakTimeScheduler:
    def __init__(self, dry_run: Optional[bool] = None, tz_name: str = "Asia/Kolkata",
                 scorer: Optional[ReelScorer] = None, harvest_worker: Optional[HarvestWorker] = None,
                 media_builder: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Optional[str]]] = None,
                 telegram=None, fanout=None):
        if dry_run is None:
            dry_run = os.getenv("OCTOPUS_LIVE_POSTING", "false").lower() not in ("1", "true", "yes")
        self.dry_run = dry_run
        self.tz_name = tz_name
        self.scorer = scorer or ReelScorer()
        self.harvest_worker = harvest_worker or HarvestWorker(scorer=self.scorer)
        self._media_builder = media_builder
        self._telegram = telegram
        self._fanout = fanout
        self.scheduler = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ lazy deps
    @property
    def fanout(self):
        if self._fanout is None:
            from publisher.octopus_fanout import OctopusFanoutEngine
            self._fanout = OctopusFanoutEngine()
        return self._fanout

    @property
    def telegram(self):
        if self._telegram is None:
            try:
                from bot.octopus_telegram_bot import OctopusTelegramBot
                self._telegram = OctopusTelegramBot()
            except Exception:
                self._telegram = False
        return self._telegram or None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        if self.scheduler and self.scheduler.running:
            return
        self.scheduler = BackgroundScheduler(timezone=ZoneInfo(self.tz_name),
                                             job_defaults={"coalesce": True, "max_instances": 1})
        niches = [n["id"] for n in get_all_niches()]
        for i, niche_id in enumerate(niches):
            # Stagger first harvest per niche (every 90s) so 20 niches don't scrape at once
            self.scheduler.add_job(
                self.harvest_niche, IntervalTrigger(minutes=HARVEST_INTERVAL_MINUTES, jitter=600),
                args=[niche_id], id=f"harvest:{niche_id}", replace_existing=True,
                next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30 + i * 90),
                misfire_grace_time=600,
            )
        self.scheduler.add_job(self.plan_all, CronTrigger(hour=0, minute=5), id="planner:daily", replace_existing=True)
        self.scheduler.add_job(self.housekeeping, CronTrigger(hour=3, minute=0), id="housekeeping:daily", replace_existing=True)
        self.scheduler.start()
        self.plan_all()
        logger.info(f"Peak-Time Scheduler started ({len(niches)} niches, tz={self.tz_name}, dry_run={self.dry_run}).")

    def shutdown(self) -> None:
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------ planning
    def plan_all(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        planned = []
        for n in get_all_niches():
            planned.extend(self.plan_niche(n["id"], now=now))
        return planned

    def plan_niche(self, niche_id: str, now: Optional[datetime] = None, days: int = 2,
                   replan: bool = False) -> List[Dict[str, Any]]:
        """Creates slot_runs for today + tomorrow (local tz) and registers prepare/publish jobs."""
        now = now or utcnow()
        sched = get_niche_schedule(niche_id)
        tz_name = sched.get("timezone") or self.tz_name
        local_today = now.astimezone(ZoneInfo(tz_name)).date()
        out = []

        if replan:
            self._drop_planned(niche_id, set(sched["slot_times"]) if sched.get("enabled") else set(), now)
        if not sched.get("enabled"):
            return out

        for d in range(days):
            day = local_today + timedelta(days=d)
            for slot_time in sched["slot_times"]:
                when = compute_scheduled_for(niche_id, day, slot_time, tz_name, int(sched.get("jitter_minutes", 8)))
                if when < now - timedelta(minutes=MISFIRE_GRACE_MINUTES):
                    continue  # already passed
                run = create_slot_run(niche_id, slot_time, day.isoformat(), when, dry_run=self.dry_run)
                if run["status"] in ("PLANNED", "AWAITING_APPROVAL", "APPROVED"):
                    self._register_jobs(run, now)
                out.append(run)
        return out

    def _drop_planned(self, niche_id: str, keep_slots: set, now: datetime) -> None:
        for run in get_slot_runs(since=now - timedelta(minutes=MISFIRE_GRACE_MINUTES), niche_id=niche_id):
            if run["status"] == "PLANNED" and run["slot_time"] not in keep_slots:
                update_slot_run(run["id"], {"status": "SKIPPED", "error": "Removed: schedule changed"})
                self._remove_jobs(run["id"])

    def _register_jobs(self, run: Dict[str, Any], now: datetime) -> None:
        if not self.scheduler:
            return
        from apscheduler.triggers.date import DateTrigger
        when = from_iso(run["scheduled_for"])
        prep_at = when - timedelta(minutes=PRERENDER_LEAD_MINUTES)
        if run["status"] == "PLANNED":
            self.scheduler.add_job(self.prepare_slot, DateTrigger(run_date=max(prep_at, now + timedelta(seconds=5))),
                                   args=[run["id"]], id=f"prepare:{run['id']}", replace_existing=True,
                                   misfire_grace_time=PRERENDER_LEAD_MINUTES * 60)
        self.scheduler.add_job(self.publish_slot, DateTrigger(run_date=max(when, now + timedelta(seconds=10))),
                               args=[run["id"]], id=f"publish:{run['id']}", replace_existing=True,
                               misfire_grace_time=MISFIRE_GRACE_MINUTES * 60)

    def _remove_jobs(self, slot_run_id: int) -> None:
        if not self.scheduler:
            return
        for prefix in ("prepare", "publish"):
            try:
                self.scheduler.remove_job(f"{prefix}:{slot_run_id}")
            except Exception:
                pass

    # ------------------------------------------------------------------ harvest
    def harvest_niche(self, niche_id: str) -> Dict[str, Any]:
        try:
            return self.harvest_worker.harvest_niche(niche_id)
        except Exception as e:
            logger.error(f"[{niche_id}] harvest failed: {e}", exc_info=True)
            return {"niche_id": niche_id, "error": str(e)}

    # ------------------------------------------------------------------ media build
    def build_master_reel(self, candidate: Dict[str, Any], cluster: Dict[str, Any]) -> Optional[str]:
        """Download -> AI hook & caption -> 9:16 master render. Returns reel_id or None."""
        if self._media_builder:
            return self._media_builder(candidate, cluster)

        from scrapers.instagram_harvester import InstagramHarvester
        from scrapers.content_harvester import ContentHarvester
        from processors.ai_enricher import AIEnricher
        from renderers.video_compositor import VideoCompositor

        niche = cluster.get("niche") or {}
        niche_id = niche.get("id") or candidate["niche_id"]
        name = niche.get("name", niche_id)
        task_id = f"slot_{niche_id}_{uuid.uuid4().hex[:6]}"

        dl = InstagramHarvester().download_reel(candidate["permalink"], custom_id=task_id)
        if not dl or not dl.get("filepath"):
            dl = ContentHarvester().download_video(candidate["permalink"], custom_id=task_id)
        if not dl or not dl.get("filepath"):
            logger.warning(f"[{niche_id}] download failed: {candidate['permalink']}")
            return None

        accounts = cluster.get("accounts", [])
        primary = accounts[0] if accounts else {"id": niche_id, "handle": f"@{niche_id}.hub", "display_name": name}
        ch = ChannelProfile(handle=primary.get("handle"), display_name=primary.get("display_name", name), niche=name,
                            logo_filename=f"logo_{primary.get('id', niche_id)}.png", subreddits=[],
                            default_hashtags=[], cta_link="bit.ly/free-ai-newsletter")
        orig_title = dl.get("title") or (candidate.get("caption") or "")[:60]
        orig_desc = dl.get("description") or candidate.get("caption") or ""
        enriched = AIEnricher().generate_hook_and_caption(orig_title, orig_desc, ch)
        hook = enriched.get("hook_text", orig_title)
        credit = candidate.get("source_handle", "")
        full_caption = (f"{hook}\n\n{enriched.get('full_caption', '')}\n\n"
                        f"{niche.get('cta_text') or f'Follow for daily {name}!'}\n\n"
                        f"{niche.get('default_hashtags') or ''}\n\nCredit: @{credit}")
        rendered_name = f"{task_id}.mp4"
        rendered = VideoCompositor().build_reel(raw_video_path=dl["filepath"], hook_text=hook, channel=ch,
                                                output_filename=rendered_name, credit_handle=credit)
        if not rendered:
            return None
        update_candidate(candidate["id"], {"raw_video_path": dl["filepath"]})
        insert_or_update_reel({
            "id": task_id, "source_url": candidate["permalink"], "original_title": orig_title,
            "hook_text": hook, "caption": full_caption, "raw_video_path": dl["filepath"],
            "rendered_video_path": rendered, "rendered_filename": rendered_name, "status": "READY_FOR_PUBLISH",
        })
        return task_id

    # ------------------------------------------------------------------ prepare (T-30)
    def prepare_slot(self, slot_run_id: int, exclude_candidate_ids: Optional[List[int]] = None,
                     now: Optional[datetime] = None) -> Dict[str, Any]:
        with self._lock:
            run = get_slot_run(slot_run_id)
            if not run or run["status"] not in ("PLANNED",):
                return run or {}
            niche_id = run["niche_id"]
            now = now or utcnow()
            sched = get_niche_schedule(niche_id)
            cluster = get_niche_cluster(niche_id)
            account_ids = [a["id"] for a in cluster.get("accounts", []) if a.get("is_active", 1)]
            if not account_ids:
                update_slot_run(slot_run_id, {"status": "SKIPPED", "error": "No active accounts in niche"})
                return get_slot_run(slot_run_id)

            tz = ZoneInfo(sched.get("timezone") or self.tz_name)
            local_day_start = datetime.combine(now.astimezone(tz).date(), datetime.min.time(), tzinfo=tz)
            ranked = self.scorer.rank_for_slot(niche_id, sched, now=now, day_start_utc=local_day_start.astimezone(timezone.utc))
            if not ranked:
                # Pool empty -> one on-demand harvest, then retry
                self.harvest_niche(niche_id)
                ranked = self.scorer.rank_for_slot(niche_id, sched, now=now, day_start_utc=local_day_start.astimezone(timezone.utc))
            excl = set(exclude_candidate_ids or [])
            ranked = [c for c in ranked if c["id"] not in excl]

            for cand in ranked:
                update_candidate(cand["id"], {"status": "SELECTED", "selected_for_slot": slot_run_id})
                try:
                    reel_id = self.build_master_reel(cand, cluster)
                except Exception as e:
                    logger.error(f"[{niche_id}] master build failed for candidate {cand['id']}: {e}", exc_info=True)
                    reel_id = None
                if not reel_id:
                    update_candidate(cand["id"], {"status": "REJECTED", "score_reason": "Build failed (download/render)"})
                    continue
                prepared = self.fanout.prepare_broadcast(reel_id, account_ids=account_ids,
                                                         fanout_mode=sched.get("fanout_mode", "balanced"))
                if not prepared.get("success"):
                    update_candidate(cand["id"], {"status": "REJECTED", "score_reason": prepared.get("error", "prepare failed")})
                    continue
                update_candidate(cand["id"], {"status": "RENDERED"})
                status = "APPROVED"
                tg = self.telegram
                if sched.get("approval_mode") == "telegram_timeout" and tg and tg.is_configured():
                    status = "AWAITING_APPROVAL"
                update_slot_run(slot_run_id, {
                    "status": status, "candidate_id": cand["id"], "reel_id": reel_id,
                    "accounts_total": len(prepared["tasks"]),
                    "prepared_payload": {"tasks": prepared["tasks"], "evergreen": bool(cand.get("evergreen"))},
                })
                if status == "AWAITING_APPROVAL":
                    try:
                        tg.send_slot_preview(get_slot_run(slot_run_id), cand, sched)
                    except Exception as e:
                        logger.warning(f"Telegram slot preview failed: {e}")
                logger.info(f"[{niche_id}] Slot {run['slot_time']} prepared with candidate {cand['id']} (score {cand.get('final_score')}).")
                return get_slot_run(slot_run_id)

            update_slot_run(slot_run_id, {"status": "SKIPPED", "error": "No eligible candidate above min_score"})
            logger.info(f"[{niche_id}] Slot {run['slot_time']} skipped: empty pool.")
            return get_slot_run(slot_run_id)

    # ------------------------------------------------------------------ approval actions
    def approve_slot(self, slot_run_id: int) -> Dict[str, Any]:
        run = get_slot_run(slot_run_id)
        if run and run["status"] == "AWAITING_APPROVAL":
            update_slot_run(slot_run_id, {"status": "APPROVED"})
        return get_slot_run(slot_run_id) or {}

    def skip_slot(self, slot_run_id: int, reason: str = "Skipped by operator") -> Dict[str, Any]:
        run = get_slot_run(slot_run_id)
        if run and run["status"] not in ("DONE", "PUBLISHING"):
            update_slot_run(slot_run_id, {"status": "SKIPPED", "error": reason})
            if run.get("candidate_id"):
                update_candidate(run["candidate_id"], {"status": "SCORED", "selected_for_slot": None})
            self._remove_jobs(slot_run_id)
        return get_slot_run(slot_run_id) or {}

    def swap_slot(self, slot_run_id: int) -> Dict[str, Any]:
        """Reject the current pick and prepare the next-best candidate for the same slot."""
        run = get_slot_run(slot_run_id)
        if not run or run["status"] in ("DONE", "PUBLISHING", "SKIPPED"):
            return run or {}
        excl = []
        if run.get("candidate_id"):
            excl.append(run["candidate_id"])
            update_candidate(run["candidate_id"], {"status": "REJECTED", "score_reason": "Swapped by operator"})
        update_slot_run(slot_run_id, {"status": "PLANNED", "candidate_id": None, "reel_id": None, "prepared_payload": None})
        return self.prepare_slot(slot_run_id, exclude_candidate_ids=excl)

    # ------------------------------------------------------------------ publish (T)
    def publish_slot(self, slot_run_id: int, now: Optional[datetime] = None, sleep_fn=None) -> Dict[str, Any]:
        run = get_slot_run(slot_run_id)
        if not run:
            return {}
        now = now or utcnow()
        when = from_iso(run["scheduled_for"])
        if run["status"] in ("DONE", "SKIPPED", "FAILED", "PUBLISHING"):
            return run
        if when and now > when + timedelta(minutes=MISFIRE_GRACE_MINUTES):
            update_slot_run(slot_run_id, {"status": "SKIPPED", "error": "Missed peak window (> 15 min late)"})
            return get_slot_run(slot_run_id)

        if run["status"] == "PLANNED":  # prepare job didn't run (e.g. restart) -> prepare now
            run = self.prepare_slot(slot_run_id, now=now)
            if run.get("status") not in ("APPROVED", "AWAITING_APPROVAL"):
                return run
        if run["status"] == "AWAITING_APPROVAL":
            logger.info(f"Slot {slot_run_id}: no Telegram response before slot time -> auto-approved.")

        payload = json.loads(run.get("prepared_payload") or "{}")
        tasks = payload.get("tasks", [])
        dry = bool(run.get("dry_run", 1))
        update_slot_run(slot_run_id, {"status": "PUBLISHING", "started_at": to_iso(utcnow())})
        try:
            res = self.fanout.execute_broadcast(
                run["reel_id"], tasks, dry_run=dry,
                respect_stagger=not dry,      # real 30-45s gaps when live
                enforce_guards=not dry,       # daily cap / 2.5h spacing when live
                sleep_fn=sleep_fn,
            )
            update_slot_run(slot_run_id, {
                "status": "DONE", "finished_at": to_iso(utcnow()),
                "accounts_posted": res.get("successful_posts_count", 0),
                "accounts_skipped": len(res.get("skipped_accounts", [])),
            })
            if run.get("candidate_id"):
                update_candidate(run["candidate_id"], {"status": "PUBLISHED"})
        except Exception as e:
            logger.error(f"Slot {slot_run_id} publish failed: {e}", exc_info=True)
            update_slot_run(slot_run_id, {"status": "FAILED", "error": str(e), "finished_at": to_iso(utcnow())})
        return get_slot_run(slot_run_id)

    # ------------------------------------------------------------------ manual trigger
    def run_slot_now(self, niche_id: str, dry_run: bool = True, background: bool = True) -> Dict[str, Any]:
        now = utcnow()
        local = now.astimezone(ZoneInfo(self.tz_name))
        run = create_slot_run(niche_id, f"manual-{local.strftime('%H%M%S')}", local.date().isoformat(), now, dry_run=dry_run)

        def _go():
            self.prepare_slot(run["id"], now=now)
            r = get_slot_run(run["id"])
            if r and r["status"] == "AWAITING_APPROVAL":
                self.approve_slot(run["id"])
            self.publish_slot(run["id"], now=utcnow())

        if background:
            threading.Thread(target=_go, daemon=True).start()
        else:
            _go()
        return get_slot_run(run["id"])

    # ------------------------------------------------------------------ housekeeping
    def housekeeping(self) -> Dict[str, Any]:
        expired = expire_stale_candidates()
        deleted = 0
        cutoff = time.time() - MEDIA_RETENTION_HOURS * 3600
        try:
            out_dir = Path(settings.OUTPUT_DIR)
            for p in out_dir.rglob("*.mp4"):
                try:
                    if p.stat().st_mtime < cutoff:
                        p.unlink()
                        deleted += 1
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Media cleanup error: {e}")
        logger.info(f"Housekeeping: expired {expired} candidates, deleted {deleted} old media files.")
        return {"expired_candidates": expired, "deleted_files": deleted}

    # ------------------------------------------------------------------ status
    def status(self) -> Dict[str, Any]:
        jobs = self.scheduler.get_jobs() if self.scheduler else []
        return {
            "running": bool(self.scheduler and self.scheduler.running),
            "dry_run": self.dry_run,
            "timezone": self.tz_name,
            "jobs": len(jobs),
        }


_instance: Optional[PeakTimeScheduler] = None


def get_peak_scheduler() -> PeakTimeScheduler:
    global _instance
    if _instance is None:
        _instance = PeakTimeScheduler()
    return _instance
