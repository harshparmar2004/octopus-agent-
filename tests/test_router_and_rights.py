import pytest
from storage.db import init_octopus_db
from storage.network_db import init_network_tables, ledger_get, set_account_profile
from processors.rights_ledger import RightsLedger
from agents.content_router import ContentRouter

@pytest.fixture(autouse=True)
def setup_db():
    init_octopus_db()
    init_network_tables()

def test_01_content_router_exclusive_lock():
    """Verifies that once a reel is routed to an account, it cannot be routed to a second account."""
    src = "reel_exclusive_test_001"
    
    # First routing attempt succeeds
    acc1 = ContentRouter.route_reel_to_best_account(
        source_key=src,
        niche_id="information",
        creator_handle="scraped_creator"
    )
    assert acc1 is not None
    
    # Second routing attempt on the same source_key must be rejected
    acc2 = ContentRouter.route_reel_to_best_account(
        source_key=src,
        niche_id="information",
        creator_handle="scraped_creator"
    )
    assert acc2 is None

    # Check ledger lock
    entry = ledger_get(src)
    assert entry["status"] == "ASSIGNED"
    assert entry["assigned_account_id"] == acc1["id"]

def test_02_girls_dance_permission_gate():
    """Verifies that girls_dance reels cannot publish without explicit creator permission."""
    src = "reel_dance_test_002"
    
    # Initial status requires permission
    res = RightsLedger.evaluate_reel_rights(
        source_key=src,
        creator_handle="dance_creator",
        niche_id="girls_dance",
        requires_permission=True
    )
    assert res["allowed"] is False
    assert res["status"] == "permission_required"
    
    # Grant permission
    RightsLedger.grant_permission(src, evidence="approved in DM")
    
    # Re-evaluate
    res2 = RightsLedger.evaluate_reel_rights(
        source_key=src,
        creator_handle="dance_creator",
        niche_id="girls_dance",
        requires_permission=True
    )
    assert res2["allowed"] is True
    assert res2["status"] == "permission_granted"

def test_03_takedown_and_blocklist():
    """Verifies that a takedown request blocks the creator globally."""
    src = "reel_takedown_test_003"
    creator = "blocked_creator_99"
    
    RightsLedger.process_takedown(
        source_key=src,
        creator_handle=creator,
        account_id="info_01",
        reason="creator request"
    )
    
    # New attempts for this creator must be rejected immediately
    eval_res = RightsLedger.evaluate_reel_rights(
        source_key="new_clip_from_same_creator",
        creator_handle=creator,
        niche_id="information"
    )
    assert eval_res["allowed"] is False
    assert eval_res["status"] == "blocked"
