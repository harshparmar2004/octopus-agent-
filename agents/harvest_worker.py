"""
HarvestWorker: fills the per-niche Candidate Pool from all of the niche's sources.

Runs every ~75 min per niche (staggered). It does NOT download or post anything: it only stores
reel metadata + engagement so the ReelScorer can rank them. Media is downloaded later, only for the
top shortlisted candidate when a peak slot is being prepared.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from scrapers.instagram_harvester import InstagramHarvester
from storage.db import get_niche_cluster, is_source_already_scraped
from storage.scheduler_db import from_iso, to_iso, upsert_candidate
from processors.reel_scorer import ReelScorer

logger = logging.getLogger("HarvestWorker")


class HarvestWorker:
    def __init__(self, harvester: InstagramHarvester = None, scorer: ReelScorer = None,
                 reels_per_source: int = 12, max_threads: int = 5):
        self.harvester = harvester or InstagramHarvester()
        self.scorer = scorer or ReelScorer()
        self.reels_per_source = reels_per_source
        self.max_threads = max_threads

    def _scan_source(self, niche_id: str, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        if source.get("source_type") != "instagram_handle" or not source.get("is_active", 1):
            return []
        handle = (source.get("source_value") or "").strip().lstrip("@")
        if not handle:
            return []
        try:
            reels = self.harvester.get_recent_reels_from_handle(handle, limit=self.reels_per_source)
        except Exception as e:
            logger.error(f"[{niche_id}] Harvest error for @{handle}: {e}")
            return []
        out = []
        for r in reels:
            if not r.get("reel_id") or not r.get("permalink"):
                continue
            if is_source_already_scraped(r["permalink"]):
                continue  # already went through the legacy immediate pipeline
            ts = from_iso(r.get("timestamp"))
            out.append({
                "niche_id": niche_id,
                "source_id": source.get("id"),
                "source_handle": handle,
                "shortcode": str(r["reel_id"]),
                "permalink": r["permalink"],
                "caption": r.get("caption") or "",
                "posted_at": to_iso(ts) if ts else None,
                "like_count": r.get("like_count"),
                "comments_count": r.get("comments_count"),
                "view_count": r.get("view_count"),
                "source_followers": r.get("source_followers"),
                "duration_s": r.get("duration_s"),
                "media_type": r.get("media_type") or "VIDEO",
            })
        return out

    def harvest_niche(self, niche_id: str, score: bool = True) -> Dict[str, Any]:
        start = time.time()
        cluster = get_niche_cluster(niche_id)
        sources = [s for s in cluster.get("sources", []) if s.get("source_type") == "instagram_handle"]
        found: List[Dict[str, Any]] = []
        if sources:
            with ThreadPoolExecutor(max_workers=min(self.max_threads, len(sources))) as ex:
                for batch in ex.map(lambda s: self._scan_source(niche_id, s), sources):
                    found.extend(batch)
        for c in found:
            upsert_candidate(c)
        scored = self.scorer.score_niche(niche_id) if score else 0
        report = {
            "niche_id": niche_id,
            "sources_scanned": len(sources),
            "candidates_seen": len(found),
            "candidates_scored": scored,
            "duration_seconds": round(time.time() - start, 2),
        }
        logger.info(f"[{niche_id}] Harvest: {report}")
        return report
