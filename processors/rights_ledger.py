"""
Rights and Attribution Ledger
=============================
Enforces creator attribution, permission gating (mandatory for girls_dance),
and handles takedown requests with automated source blocklisting.
"""
from typing import Dict, Any, Optional
from storage.network_db import (
    rights_get,
    rights_upsert,
    block_creator,
    is_creator_blocked,
    ledger_set_status,
    record_strike
)

class RightsLedger:
    @staticmethod
    def evaluate_reel_rights(source_key: str, creator_handle: str, niche_id: str, requires_permission: bool = False) -> Dict[str, Any]:
        """
        Determines whether a scraped reel is authorized to enter the publishing queue.
        - Blocked creators are rejected immediately.
        - Niches marked with requires_permission (e.g. girls_dance) MUST have permission_granted.
        - Other niches require valid creator attribution (credit).
        """
        clean_handle = (creator_handle or "").lstrip("@").lower().strip()
        
        # 1. Check if creator is on blocklist
        if is_creator_blocked(clean_handle):
            return {
                "allowed": False,
                "status": "blocked",
                "reason": f"Creator @{clean_handle} is on the network blocklist"
            }

        existing = rights_get(source_key)
        current_status = existing["status"] if existing else ("permission_required" if requires_permission else "credited_ok")

        if not existing:
            rights_upsert(
                source_key=source_key,
                creator_handle=clean_handle,
                niche_id=niche_id,
                status=current_status
            )

        # 2. Permission check
        if requires_permission and current_status != "permission_granted":
            return {
                "allowed": False,
                "status": current_status,
                "reason": f"Creator @{clean_handle} permission is required before publishing"
            }

        return {
            "allowed": True,
            "status": current_status,
            "creator_handle": clean_handle
        }

    @staticmethod
    def generate_permission_dm(creator_handle: str, destination_handle: str, niche_id: str) -> str:
        """Drafts a respectful, high-conversion permission request DM."""
        clean_creator = creator_handle.lstrip("@")
        clean_dest = destination_handle if destination_handle.startswith("@") else f"@{destination_handle}"
        
        return (
            f"Hey {clean_creator}! Loved your recent video. We'd love to feature your clip on {clean_dest} "
            f"with full prominent credit to you (@{clean_creator}) in both the caption and tags! "
            f"Would you be cool with us sharing it? Let us know! 😊"
        )

    @staticmethod
    def grant_permission(source_key: str, evidence: str = "creator approved in DM"):
        """Records creator permission for a specific clip."""
        rights_upsert(source_key=source_key, status="permission_granted", evidence=evidence)

    @staticmethod
    def process_takedown(source_key: str, creator_handle: str, account_id: str, reason: str = "Creator request"):
        """
        Handles takedowns:
        1. Marks ledger item as TAKEN_DOWN
        2. Adds creator to global blocklist to never scrape again
        3. Records strike for auditing
        """
        clean_handle = creator_handle.lstrip("@").lower()
        ledger_set_status(source_key, "TAKEN_DOWN")
        block_creator(clean_handle, reason=f"Takedown requested: {reason}")
        record_strike(account_id, reason=f"Takedown on source {source_key}: {reason}")
