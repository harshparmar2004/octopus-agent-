"""
Content Router Engine
=====================
Enforces the 1-to-1 Content Routing Rule:
- Exactly ONE reel is routed to ONE specific Instagram account.
- Scraped viral clips are NEVER duplicated or cross-posted across sister accounts.
- Accounts are matched based on sub-niche relevance, daily post limits, and minimum spacing.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from storage.db import get_all_accounts, get_connection
from storage.network_db import (
    ledger_get,
    ledger_register,
    ledger_assign,
    get_account_profile,
    account_assignments_since
)

logger = logging.getLogger("ContentRouter")

class ContentRouter:
    @staticmethod
    def route_reel_to_best_account(
        source_key: str,
        niche_id: str,
        video_metadata: Optional[Dict[str, Any]] = None,
        source_url: str = "",
        creator_handle: str = "",
        candidate_account_ids: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Selects the best destination account for a harvested reel and acquires an exclusive lock.
        Returns the selected account profile dict or None if no eligible account is available.
        """
        # 1. Register clip in content ledger if not already tracked
        existing = ledger_get(source_key)
        if not existing:
            ledger_register(
                source_key=source_key,
                source_url=source_url,
                source_creator=creator_handle,
                niche_id=niche_id
            )
            existing = ledger_get(source_key)

        if existing and existing.get("assigned_account_id"):
            logger.info(f"Reel {source_key} already assigned exclusively to {existing['assigned_account_id']}")
            return None

        # 2. Get eligible accounts for this niche
        all_accounts = get_all_accounts(active_only=True)
        clean_niche = niche_id.lower().strip()
        
        # Match accounts in this niche or sub-cluster
        eligible = []
        for a in all_accounts:
            acc_niche = (a.get("niche_id") or a.get("niche") or "").lower()
            if candidate_account_ids and a["id"] not in candidate_account_ids:
                continue
            if clean_niche in acc_niche or acc_niche in clean_niche:
                eligible.append(a)

        if not eligible:
            # Fallback to candidates if provided
            if candidate_account_ids:
                eligible = [a for a in all_accounts if a["id"] in candidate_account_ids]
            else:
                eligible = all_accounts[:1] if all_accounts else []

        if not eligible:
            logger.warning(f"No accounts found for niche {niche_id}")
            return None

        # 3. Score candidates based on:
        # - Daily cap not exceeded (e.g. 2-3 posts/day)
        # - Spacing since last post (e.g. min 2-3 hours)
        # - Sub-niche keyword match
        meta_text = " ".join([
            str(video_metadata.get("title", "")) if video_metadata else "",
            str(video_metadata.get("caption", "")) if video_metadata else "",
            str(video_metadata.get("tags", "")) if video_metadata else ""
        ]).lower()

        best_account = None
        best_score = -999.0

        for acc in eligible:
            prof = get_account_profile(acc["id"], niche_id=niche_id)
            if prof.get("paused"):
                continue

            daily_cap = prof.get("daily_cap", 3)
            min_gap_mins = prof.get("min_gap_minutes", 180)

            # Check past 24h assignments
            recent_24h = account_assignments_since(acc["id"], hours=24.0)
            if len(recent_24h) >= daily_cap:
                continue  # daily cap reached

            # Check spacing since latest assignment
            recent_slot = account_assignments_since(acc["id"], hours=min_gap_mins / 60.0)
            if len(recent_slot) > 0:
                continue  # too close to previous post

            # Calculate match score
            score = 10.0 - len(recent_24h) * 2.0  # balance load across accounts
            sub_niche = (prof.get("sub_niche") or "").lower()
            if sub_niche:
                for kw in sub_niche.split(","):
                    kw_clean = kw.strip()
                    if kw_clean and kw_clean in meta_text:
                        score += 5.0

            if score > best_score:
                best_score = score
                best_account = acc

        if not best_account:
            logger.info(f"All accounts in niche {niche_id} have satisfied daily caps or minimum spacing.")
            return None

        # 4. Atomically acquire exclusive assignment
        locked = ledger_assign(source_key, best_account["id"])
        if not locked:
            logger.warning(f"Could not lock {source_key} to {best_account['id']}; already assigned concurrently.")
            return None

        logger.info(f"Successfully locked {source_key} ➔ @{best_account['handle']} (Score: {best_score})")
        return best_account
