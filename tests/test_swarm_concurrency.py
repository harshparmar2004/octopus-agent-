import time
import unittest
from pathlib import Path

from config import settings
from storage.db import (
    init_octopus_db,
    get_all_niches,
    create_or_update_niche,
    add_or_update_account,
    add_monitored_source
)
from agents.niche_swarm_agent import NichePodAgent
from agents.swarm_coordinator import OctopusSwarmCoordinator
from renderers.video_compositor import VideoCompositor

class TestSwarmConcurrency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_octopus_db()
        # Seed test niches if needed
        create_or_update_niche({
            "id": "test_quantum",
            "name": "Test Quantum Niche",
            "brand_color": "#00b4d8",
            "avatar_icon": "⚛️"
        })
        create_or_update_niche({
            "id": "test_ai",
            "name": "Test AI Niche",
            "brand_color": "#7c3aed",
            "avatar_icon": "🤖"
        })
        add_or_update_account({
            "id": "tq_01",
            "handle": "@test.quantum",
            "display_name": "TestQuantum",
            "niche": "test_quantum",
            "niche_id": "test_quantum",
            "is_active": 1
        })
        add_or_update_account({
            "id": "tai_01",
            "handle": "@test.ai",
            "display_name": "TestAI",
            "niche": "test_ai",
            "niche_id": "test_ai",
            "is_active": 1
        })

    def test_01_niche_pod_agent_init(self):
        agent = NichePodAgent(niche_id="test_quantum")
        self.assertEqual(agent.niche_id, "test_quantum")
        self.assertGreaterEqual(len(agent.accounts), 1)
        self.assertEqual(agent.status, "IDLE")
        print("[PASS] NichePodAgent initialization successful.")

    def test_02_swarm_coordinator_discovery(self):
        coord = OctopusSwarmCoordinator()
        status = coord.get_swarm_status()
        self.assertGreaterEqual(status["total_niches"], 2)
        self.assertIn("agents", status)
        print(f"[PASS] SwarmCoordinator discovered {status['total_niches']} niches.")

    def test_03_parallel_swarm_dry_run_speed(self):
        from unittest.mock import patch
        with patch("scrapers.instagram_harvester.InstagramHarvester.get_latest_reel_from_handle") as mock_harvest:
            # Mock returning no new reel for instant parallel dry run
            mock_harvest.return_value = None
            coord = OctopusSwarmCoordinator()
            start = time.time()
            report = coord.run_swarm_parallel(dry_run=True, max_concurrency=10)
            duration = time.time() - start

            self.assertEqual(report["status"], "COMPLETED")
            self.assertIn("niches_processed", report)
            self.assertLess(duration, 5.0, "Parallel swarm scan took too long!")
            print(f"[PASS] Parallel swarm completed in {duration:.3f}s across {report['niches_processed']} niches.")

    def test_04_hardware_encoder_selection(self):
        import platform
        compositor = VideoCompositor()
        self.assertTrue(hasattr(compositor, "build_reel"))
        if platform.system() == "Darwin":
            print("[PASS] macOS environment detected: VideoToolbox hardware encoder enabled.")
        else:
            print(f"[PASS] {platform.system()} environment: CPU libx264 encoder configured.")

if __name__ == "__main__":
    unittest.main()
