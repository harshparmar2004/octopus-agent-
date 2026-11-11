"""
ReelScorer: ranks harvested reels in the Candidate Pool so each peak slot posts the BEST fresh reel.

final_score (0-100) =
    0.40 * velocity   (engagement per hour, normalised by source follower count)
  + 0.25 * freshness  (100 if <= 12h old, linear decay to 0 at 72h)
  + 0.30 * niche_fit  (batched LLM rating 0-10, keyword heuristic fallback when LLM offline)
  + 0.05 * quality    (promo/ad captions penalised)

Hard gates (candidate is REJECTED): already posted by us in the last 14 days, promo/sponsored caption,
non-video media, duration outside 7-90s (when known).
"""
import json
import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from storage.db import get_niche_by_id
from storage.scheduler_db import (
    CANDIDATE_MAX_AGE_HOURS,
    from_iso,
    get_candidates,
    sources_used_today,
    update_candidate,
    utcnow,
    was_posted_recently,
)

logger = logging.getLogger("ReelScorer")

WEIGHTS = {"velocity": 0.40, "freshness": 0.25, "niche_fit": 0.30, "quality": 0.05}
FRESH_FULL_HOURS = 12
EVERGREEN_MAX_DAYS = 7
EVERGREEN_PENALTY = 0.75  # evergreen candidates get 75% of their score
LLM_BATCH_SIZE = 15

PROMO_PATTERNS = [
    r"\bsponsored\b", r"#ad\b", r"\bpaid partnership\b", r"\bgiveaway\b", r"\bdiscount code\b",
    r"\buse code\b", r"\bshop now\b", r"\bbuy now\b", r"\blimited offer\b", r"\bpromo\b",
]


class ReelScorer:
    def __init__(self, use_llm: bool = True):
        self.use_llm = use_llm

    # ------------------------------------------------------------------ signals
    @staticmethod
    def age_hours(candidate: Dict[str, Any], now: Optional[datetime] = None) -> Optional[float]:
        now = now or utcnow()
        ts = from_iso(candidate.get("posted_at"))
        if not ts:
            return None
        return max(0.0, (now - ts).total_seconds() / 3600.0)

    @staticmethod
    def velocity_score(candidate: Dict[str, Any], age_h: Optional[float]) -> float:
        likes = candidate.get("like_count")
        comments = candidate.get("comments_count")
        if likes is None and comments is None:
            return 50.0  # unknown engagement (public mirror) -> neutral
        engagement = (likes or 0) + 3 * (comments or 0)
        followers = max(int(candidate.get("source_followers") or 0), 1000)
        hours = max(1.0, age_h if age_h is not None else 24.0)
        # Engagement rate per day relative to the source's own audience.
        # 8%/day relative engagement == outperforming viral reel -> 100
        daily_rate = (engagement / followers) * (24.0 / hours)
        return round(min(100.0, 100.0 * daily_rate / 0.08), 2)

    @staticmethod
    def freshness_score(age_h: Optional[float]) -> float:
        if age_h is None:
            return 60.0  # unknown timestamp -> moderately fresh (we only just discovered it)
        if age_h <= FRESH_FULL_HOURS:
            return 100.0
        if age_h >= CANDIDATE_MAX_AGE_HOURS:
            return 0.0
        span = CANDIDATE_MAX_AGE_HOURS - FRESH_FULL_HOURS
        return round(100.0 * (1 - (age_h - FRESH_FULL_HOURS) / span), 2)

    @staticmethod
    def quality_gate(candidate: Dict[str, Any]) -> Tuple[float, Optional[str]]:
        """Returns (quality_score, reject_reason)."""
        caption = (candidate.get("caption") or "").lower()
        for p in PROMO_PATTERNS:
            if re.search(p, caption):
                return 0.0, f"promo/sponsored caption ({p.strip(chr(92)+'b')})"
        mt = (candidate.get("media_type") or "VIDEO").upper()
        if mt not in ("VIDEO", "REELS", "REEL", "CLIPS"):
            return 0.0, f"not a reel ({mt})"
        dur = candidate.get("duration_s")
        if dur is not None and (dur < 7 or dur > 90):
            return 0.0, f"duration {dur:.0f}s outside 7-90s"
        if candidate.get("shortcode") and was_posted_recently(candidate["shortcode"]):
            return 0.0, "already posted in last 14 days"
        return 100.0, None

    # ------------------------------------------------------------------ niche fit
    @staticmethod
    def _niche_keywords(niche: Dict[str, Any]) -> List[str]:
        text = " ".join([
            niche.get("id", ""), niche.get("name", ""), niche.get("description", ""),
            (niche.get("default_hashtags") or "").replace("#", " "),
        ]).lower()
        stop = {"and", "the", "for", "daily", "with", "of", "&", "viral"}
        return sorted({w for w in re.findall(r"[a-z]{3,}", text) if w not in stop})

    def heuristic_niche_fit(self, candidates: List[Dict[str, Any]], niche: Dict[str, Any]) -> Dict[int, Tuple[float, str]]:
        kws = self._niche_keywords(niche)
        out = {}
        for c in candidates:
            cap = (c.get("caption") or "").lower()
            if not cap:
                out[c["id"]] = (6.0, "no caption - trusted niche source")
                continue
            hits = [k for k in kws if k in cap]
            score = min(10.0, 5.0 + 1.5 * len(hits))
            out[c["id"]] = (score, f"keyword match: {', '.join(hits[:4]) or 'none'}")
        return out

    def llm_niche_fit(self, candidates: List[Dict[str, Any]], niche: Dict[str, Any]) -> Dict[int, Tuple[float, str]]:
        """Batched LLM rating. Falls back to heuristic for any candidate the LLM doesn't return."""
        result = self.heuristic_niche_fit(candidates, niche)
        if not self.use_llm or not candidates:
            return result
        try:
            from processors.llm_manager import LLMManager, PROVIDER_DEFAULTS
            cfg = LLMManager().config
        except Exception:
            return result
        api_key = cfg.get("api_key", "")
        if not api_key:
            return result

        system = (
            "You are a viral Instagram Reels curator. Rate how well each reel fits the target niche AND how likely "
            "it is to go viral for a page in that niche. Score 0-10 (10 = perfect fit, high viral potential). "
            "Respond ONLY with JSON: {\"ratings\": [{\"id\": <int>, \"score\": <0-10>, \"reason\": \"<max 12 words>\"}]}"
        )
        for i in range(0, len(candidates), LLM_BATCH_SIZE):
            batch = candidates[i:i + LLM_BATCH_SIZE]
            items = "\n".join(
                f"- id={c['id']} | source=@{c.get('source_handle', '')} | caption: {(c.get('caption') or '(none)')[:280]!r}"
                for c in batch
            )
            user = f"Niche: {niche.get('name')} - {niche.get('description', '')}\nReels:\n{items}"
            parsed = self._call_llm_json(cfg, PROVIDER_DEFAULTS, system, user)
            if not parsed:
                continue
            for r in parsed.get("ratings", []):
                try:
                    cid = int(r["id"])
                    result[cid] = (max(0.0, min(10.0, float(r["score"]))), str(r.get("reason", ""))[:120])
                except Exception:
                    continue
        return result

    @staticmethod
    def _call_llm_json(cfg: Dict[str, Any], defaults: Dict[str, Any], system: str, user: str) -> Optional[Dict[str, Any]]:
        provider = cfg.get("provider", "gemini")
        model = cfg.get("model", "gemini-1.5-flash")
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "")
        raw = None
        try:
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {"contents": [{"parts": [{"text": f"{system}\n\n{user}"}]}],
                           "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
                res = requests.post(url, json=payload, timeout=25)
                if res.status_code == 200:
                    raw = res.json()["candidates"][0]["content"]["parts"][0]["text"]
            elif provider == "claude":
                res = requests.post("https://api.anthropic.com/v1/messages", json={
                    "model": model, "system": system, "max_tokens": 1200, "temperature": 0.2,
                    "messages": [{"role": "user", "content": user}]
                }, headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout=25)
                if res.status_code == 200:
                    raw = res.json()["content"][0]["text"]
            else:
                endpoint = (base_url or defaults.get(provider, {}).get("base_url", "https://api.openai.com/v1")).rstrip("/") + "/chat/completions"
                res = requests.post(endpoint, json={
                    "model": model, "temperature": 0.2,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]
                }, headers={"Authorization": f"Bearer {api_key}"}, timeout=25)
                if res.status_code == 200:
                    raw = res.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"LLM niche-fit call failed ({provider}): {e}")
            return None
        if not raw:
            return None
        m = re.search(r"\{[\s\S]*\}", raw)
        try:
            return json.loads(m.group(0)) if m else None
        except Exception:
            return None

    # ------------------------------------------------------------------ public API
    def score_niche(self, niche_id: str, now: Optional[datetime] = None) -> int:
        """(Re)scores all DISCOVERED/SCORED candidates of a niche. Returns number scored."""
        now = now or utcnow()
        niche = get_niche_by_id(niche_id) or {"id": niche_id, "name": niche_id.capitalize(), "description": ""}
        cands = get_candidates(niche_id, statuses=["DISCOVERED", "SCORED"], limit=300)
        if not cands:
            return 0

        eligible = []
        for c in cands:
            q, reason = self.quality_gate(c)
            if reason:
                update_candidate(c["id"], {"status": "REJECTED", "quality_score": q, "final_score": 0,
                                           "score_reason": f"Rejected: {reason}"})
                continue
            eligible.append(c)

        # Only ask the LLM about candidates without a niche-fit score yet (saves tokens on re-scores)
        need_fit = [c for c in eligible if not c.get("niche_fit_score")]
        fits = self.llm_niche_fit(need_fit, niche) if need_fit else {}

        for c in eligible:
            age_h = self.age_hours(c, now)
            v = self.velocity_score(c, age_h)
            f = self.freshness_score(age_h)
            if c["id"] in fits:
                nf10, nf_reason = fits[c["id"]]
                nf = nf10 * 10
            else:
                nf, nf_reason = float(c.get("niche_fit_score") or 50.0), None
            final = WEIGHTS["velocity"] * v + WEIGHTS["freshness"] * f + WEIGHTS["niche_fit"] * nf + WEIGHTS["quality"] * 100
            age_txt = f"{age_h:.0f}h old" if age_h is not None else "age unknown"
            reason = f"velocity {v:.0f} | fresh {f:.0f} ({age_txt}) | niche-fit {nf:.0f}"
            if nf_reason:
                reason += f" - {nf_reason}"
            update_candidate(c["id"], {
                "velocity_score": v, "freshness_score": f, "niche_fit_score": nf, "quality_score": 100,
                "final_score": round(final, 2), "score_reason": reason, "status": "SCORED",
            })
        return len(eligible)

    def rank_for_slot(self, niche_id: str, schedule: Dict[str, Any], now: Optional[datetime] = None,
                      day_start_utc: Optional[datetime] = None, top_n: int = 3) -> List[Dict[str, Any]]:
        """
        Returns the top-N candidates to try for the upcoming slot (best first), applying:
        pinned-first, min_score, source-diversity, freshness window and evergreen fallback.
        """
        now = now or utcnow()
        min_score = float(schedule.get("min_score", 35))
        pool = get_candidates(niche_id, statuses=["SCORED"], limit=300)
        used_sources = set()
        if schedule.get("source_diversity", True):
            used_sources = set(sources_used_today(niche_id, day_start_utc or (now - timedelta(hours=24))))

        fresh, evergreen = [], []
        for c in pool:
            if used_sources and c.get("source_handle") in used_sources and not c.get("pinned"):
                continue
            age_h = self.age_hours(c, now)
            if age_h is None:
                disc = from_iso(c.get("discovered_at"))
                age_h = (now - disc).total_seconds() / 3600 if disc else 0
            if c.get("pinned"):
                fresh.append((1e9, c))
            elif age_h <= CANDIDATE_MAX_AGE_HOURS and c["final_score"] >= min_score:
                fresh.append((c["final_score"], c))
            elif age_h <= EVERGREEN_MAX_DAYS * 24 and schedule.get("evergreen_fallback", True):
                eff = c["final_score"] * EVERGREEN_PENALTY
                if eff >= min_score * EVERGREEN_PENALTY:
                    evergreen.append((eff, dict(c, evergreen=True)))

        fresh.sort(key=lambda x: x[0], reverse=True)
        evergreen.sort(key=lambda x: x[0], reverse=True)
        ranked = [c for _, c in fresh] + [c for _, c in evergreen]
        return ranked[:top_n]
