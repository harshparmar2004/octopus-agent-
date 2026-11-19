"""
DEPRECATED compatibility shim for AntiShadowbanEngine.

The legitimate pieces (per-account caption voice, hashtag tiers, staggered
scheduling) now live in processors/distribution_policy.py. Import from there.
This class preserves backward-compatibility for endpoints and test suites.
"""
from typing import Dict, Any, Optional, List
from processors.distribution_policy import (  # noqa: F401
    DistributionPolicy,
    NICHE_HASHTAG_TAXONOMY,
    HOOK_PREFIX_VARIANTS,
    TRANSITIONAL_SYNONYMS,
    ACCOUNT_CTA_TEMPLATES,
)

DEVICE_SPOOF_PROFILES = [
    {
        "make": "Apple",
        "model": "iPhone 15 Pro Max",
        "handler_name": "Apple Video Media Handler",
        "encoder": "QuickTime / Apple iOS 17.5.1",
        "video_tag": "hvc1"
    },
    {
        "make": "Apple",
        "model": "iPhone 14 Pro",
        "handler_name": "Apple Video Media Handler",
        "encoder": "QuickTime / Apple iOS 17.4.1",
        "video_tag": "avc1"
    },
    {
        "make": "Samsung",
        "model": "Galaxy S24 Ultra",
        "handler_name": "VideoHandle",
        "encoder": "Samsung Exynos Media Framework v14.0",
        "video_tag": "avc1"
    },
    {
        "make": "Apple",
        "model": "iPhone 15 Plus",
        "handler_name": "Apple Video Media Handler",
        "encoder": "QuickTime / Apple iOS 17.5",
        "video_tag": "hvc1"
    },
    {
        "make": "Google",
        "model": "Pixel 8 Pro",
        "handler_name": "Android Camera Media",
        "encoder": "Android MediaCodec v14",
        "video_tag": "avc1"
    },
    {
        "make": "Apple",
        "model": "iPhone 13 Pro Max",
        "handler_name": "Apple Video Media Handler",
        "encoder": "QuickTime / Apple iOS 16.6",
        "video_tag": "avc1"
    },
    {
        "make": "OnePlus",
        "model": "OnePlus 12",
        "handler_name": "VideoHandle",
        "encoder": "OxygenOS Media Framework v14.0",
        "video_tag": "avc1"
    },
    {
        "make": "Apple",
        "model": "iPhone 15",
        "handler_name": "Apple Video Media Handler",
        "encoder": "QuickTime / Apple iOS 17.3",
        "video_tag": "hvc1"
    },
    {
        "make": "Samsung",
        "model": "Galaxy S23 Ultra",
        "handler_name": "VideoHandle",
        "encoder": "Samsung MediaCodec v14.0",
        "video_tag": "avc1"
    },
    {
        "make": "Apple",
        "model": "iPhone 14",
        "handler_name": "Apple Video Media Handler",
        "encoder": "QuickTime / Apple iOS 17.2",
        "video_tag": "avc1"
    }
]

class AntiShadowbanEngine(DistributionPolicy):
    """Backward-compatible engine inheriting from DistributionPolicy."""

    @staticmethod
    def get_pinned_device_profile(account_identifier: Optional[str] = None, account_index: int = 0) -> Dict[str, Any]:
        """
        Returns a permanent, deterministic device profile for an account.
        Guarantees that an account NEVER swaps its phone profile across days or reboots.
        Account @cute.aarohi.007 is permanently pinned to iPhone 15 Pro Max.
        """
        if account_identifier and account_identifier.strip():
            clean_id = account_identifier.strip().lower().lstrip("@").replace(".", "_")
            if "cute_aarohi" in clean_id:
                idx = 0
            else:
                import hashlib
                h_int = int(hashlib.sha256(clean_id.encode("utf-8")).hexdigest()[:8], 16)
                idx = h_int % len(DEVICE_SPOOF_PROFILES)
        else:
            idx = account_index % len(DEVICE_SPOOF_PROFILES)
        return DEVICE_SPOOF_PROFILES[idx]

    @staticmethod
    def get_device_profile(account_index: int = 0, account_identifier: Optional[str] = None) -> Dict[str, Any]:
        """Returns the pinned device profile for an account index or identifier."""
        return AntiShadowbanEngine.get_pinned_device_profile(account_identifier, account_index)

    @staticmethod
    def generate_realistic_creation_time(account_identifier: Optional[str] = None) -> str:
        """
        Generates a realistic creation timestamp (1 to 4 hours in the past)
        with minute and second entropy, matching realistic creator editing workflows.
        """
        import random
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        seed_val = (account_identifier or "") + now.strftime("%Y-%m-%d-%H")
        rng = random.Random(sum(ord(c) for c in seed_val))
        offset_hours = rng.randint(1, 4)
        offset_minutes = rng.randint(4, 56)
        offset_seconds = rng.randint(10, 59)
        created_dt = now - timedelta(hours=offset_hours, minutes=offset_minutes, seconds=offset_seconds)
        return created_dt.strftime("%Y-%m-%dT%H:%M:%S.000000Z")

    @staticmethod
    def get_metadata_args(account_identifier: Optional[str] = None, account_index: int = 0) -> List[str]:
        """
        Generates clean, authentic QuickTime/MP4 container metadata args:
        - make & model of the account's pinned device
        - realistic past creation timestamp (1-4h ago in UTC/IST)
        - zero artificial spam comment tags
        """
        device = AntiShadowbanEngine.get_pinned_device_profile(account_identifier, account_index)
        creation_time = AntiShadowbanEngine.generate_realistic_creation_time(account_identifier)
        return [
            "-map_metadata", "-1",
            "-metadata", f"make={device['make']}",
            "-metadata", f"model={device['model']}",
            "-metadata", f"encoder={device['encoder']}",
            "-metadata:s:v:0", f"handler_name={device['handler_name']}",
            "-metadata", f"creation_time={creation_time}"
        ]

    @staticmethod
    def get_video_mutation_params(account_index: int = 0, account_identifier: Optional[str] = None) -> Dict[str, Any]:
        """Provides simulated or backward-compatible parameters."""
        device = AntiShadowbanEngine.get_pinned_device_profile(account_identifier, account_index)
        contrast = round(0.992 + ((account_index * 3) % 7) * 0.003, 4)
        brightness = round(-0.005 + ((account_index * 2) % 6) * 0.002, 4)
        saturation = round(0.995 + ((account_index * 4) % 8) * 0.003, 4)
        gamma = round(0.994 + ((account_index * 5) % 7) * 0.002, 4)
        crop_dx = 2 + (account_index % 3) * 2
        crop_dy = 2 + ((account_index + 1) % 3) * 2
        pitch_rate = 44100 + ((account_index % 5) - 2) * 44

        video_filters = (
            f"eq=contrast={contrast}:brightness={brightness}:saturation={saturation}:gamma={gamma},"
            f"noise=c0s=1:c0f=u"
        )
        audio_filters = f"asetrate={pitch_rate},aresample=48000"

        return {
            "account_index": account_index,
            "contrast": contrast,
            "brightness": brightness,
            "saturation": saturation,
            "gamma": gamma,
            "crop_offset": (crop_dx, crop_dy),
            "video_filters": video_filters,
            "audio_filters": audio_filters,
            "device_profile": device,
            "metadata_args": AntiShadowbanEngine.get_metadata_args(account_identifier, account_index)
        }


