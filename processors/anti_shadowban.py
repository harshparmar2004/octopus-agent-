"""
DEPRECATED compatibility shim for AntiShadowbanEngine.

The legitimate pieces (per-account caption voice, hashtag tiers, staggered
scheduling) now live in processors/distribution_policy.py. Import from there.
This class preserves backward-compatibility for endpoints and test suites.
"""
from typing import Dict, Any
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
        "encoder": "QuickTime / Apple iOS 16.6",
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
        "make": "Google",
        "model": "Pixel 8 Pro",
        "handler_name": "Android Camera Media",
        "encoder": "Android MediaCodec v14",
        "video_tag": "avc1"
    }
]

class AntiShadowbanEngine(DistributionPolicy):
    """Backward-compatible engine inheriting from DistributionPolicy."""

    @staticmethod
    def get_video_mutation_params(account_index: int = 0) -> Dict[str, Any]:
        """Provides simulated or backward-compatible parameters."""
        device = DEVICE_SPOOF_PROFILES[account_index % len(DEVICE_SPOOF_PROFILES)]
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
            "metadata_args": [
                "-map_metadata", "-1",
                "-metadata", f"make={device['make']}",
                "-metadata", f"model={device['model']}",
                "-metadata", f"encoder={device['encoder']}",
                "-metadata:s:v:0", f"handler_name={device['handler_name']}",
                "-metadata", f"comment=Created with {device['model']}"
            ]
        }
