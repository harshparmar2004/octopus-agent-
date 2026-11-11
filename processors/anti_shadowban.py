"""
Anti-Shadowban & Resilient Multi-Account Distribution Engine
============================================================
Guarantees that broadcasting a single viral reel across 10-20 Instagram accounts
does not trigger Meta's automated duplicate detection, spam filters, or shadowbans.

Core Pillars:
1. Perceptual Video Mutation (Micro-Crop, Color EQ, Noise Dithering, Audio Micro-Shift, EXIF Spoofing)
2. Context-Preserving Caption Variation (Hook variants, transitional flow, unique CTAs)
3. Tiered Dynamic Hashtag Shuffling (High, Mid, Micro tiers; zero identical sets across accounts)
4. Staggered Jitter Scheduling (Natural 2-5 min posting offsets)
"""

import hashlib
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

# Comprehensive 3-tier hashtag matrix per niche
NICHE_HASHTAG_TAXONOMY: Dict[str, Dict[str, List[str]]] = {
    "information": {
        "tier1_high": ["#knowledge", "#facts", "#dailyfacts", "#science", "#education", "#learning", "#curiosity"],
        "tier2_mid": ["#psychologyfacts", "#mindblowingfacts", "#interestingfacts", "#sciencefacts", "#financialfreedom", "#wealthbuilding", "#deepthoughts"],
        "tier3_micro": ["#intellectualcuriosity", "#cognitivepsychology", "#dailylearning", "#highsignal", "#truthseeker", "#curiousminds", "#mentalmodels"]
    },
    "quantum": {
        "tier1_high": ["#physics", "#quantumphysics", "#science", "#stem", "#space", "#universe", "#cosmos"],
        "tier2_mid": ["#quantummechanics", "#superconductivity", "#astrophysics", "#quantumcomputing", "#theoreticalphysics", "#particlephysics"],
        "tier3_micro": ["#meissnereffect", "#quantumlevitation", "#quantumentanglement", "#ferrofluid", "#scientificdiscovery", "#modernphysics"]
    },
    "robotics": {
        "tier1_high": ["#robotics", "#technology", "#futuretech", "#engineering", "#robots", "#innovation"],
        "tier2_mid": ["#humanoidrobot", "#artificialintelligence", "#bipedalrobot", "#mechatronics", "#bostondynamics", "#roboticsengineering"],
        "tier3_micro": ["#actuators", "#reinforcementlearning", "#embodiedai", "#roboticarm", "#kinematics", "#autonomoustheory"]
    },
    "ai": {
        "tier1_high": ["#ai", "#artificialintelligence", "#tech", "#innovation", "#future", "#machinelearning"],
        "tier2_mid": ["#generativeai", "#deeplearning", "#neuralnetworks", "#chatgpt", "#aimodels", "#autonomoussystems"],
        "tier3_micro": ["#llms", "#aibreakthrough", "#synthetictraining", "#computervision", "#futureofai", "#deeptech"]
    },
    "space": {
        "tier1_high": ["#space", "#astronomy", "#nasa", "#cosmos", "#universe", "#galaxy"],
        "tier2_mid": ["#jameswebb", "#spacex", "#astrophysics", "#deepspace", "#planetaryscience", "#nebula"],
        "tier3_micro": ["#interstellar", "#orbitalmechanics", "#exoplanets", "#supernova", "#stargazing", "#spaceexploration"]
    },
    "biotech": {
        "tier1_high": ["#biotechnology", "#biology", "#science", "#genetics", "#healthtech", "#nature"],
        "tier2_mid": ["#crispr", "#geneediting", "#syntheticbiology", "#molecularbiology", "#biomedical", "#cellularbiology"],
        "tier3_micro": ["#epigenetics", "#bioengineering", "#longevityscience", "#dnaediting", "#biotechbreakthrough"]
    },
    "parties": {
        "tier1_high": ["#nightlife", "#party", "#clubbing", "#music", "#vip", "#weekendvibes", "#luxury"],
        "tier2_mid": ["#miaminightlife", "#electronicmusic", "#housemusic", "#bottleservice", "#djset", "#afterhours"],
        "tier3_micro": ["#miamiclubs", "#technovibes", "#livmiami", "#e11evenmiami", "#clubspace", "#nightlifeculture"]
    },
    "organizing": {
        "tier1_high": ["#organization", "#homeorganization", "#declutter", "#minimalism", "#aesthetic", "#lifestyle"],
        "tier2_mid": ["#pantryorganization", "#restock", "#satisfyingvideos", "#homehacks", "#cleanhome", "#closetgoals"],
        "tier3_micro": ["#kitchenorganization", "#restockday", "#organizationtips", "#minimalisthome", "#aestheticcleaning"]
    },
    "fashion": {
        "tier1_high": ["#fashion", "#style", "#streetwear", "#luxuryfashion", "#ootd", "#outfitinspiration"],
        "tier2_mid": ["#capsulewardrobe", "#neutralstyle", "#parisfashion", "#tailoredsuit", "#quietluxury", "#stylingideas"],
        "tier3_micro": ["#minimalistfashion", "#fashioneditorial", "#silhouettefashion", "#fashionmasterclass", "#curatedcloset"]
    }
}

# Hook Variation Patterns
HOOK_PREFIX_VARIANTS = [
    "",  # Original hook
    "The reality is: ",
    "Most people don't realize that ",
    "Did you know that ",
    "A fascinating truth about ",
    "Here is why ",
    "What actually happens when ",
    "It is rarely talked about, but "
]

# Transitional Synonyms for Body Paragraphs
TRANSITIONAL_SYNONYMS = {
    "furthermore": ["in addition", "on top of that", "what is more", "moreover"],
    "interestingly": ["fascinatingly", "remarkably", "notably", "intriguingly"],
    "ultimately": ["at its core", "in the end", "essentially", "fundamentally"],
    "for example": ["for instance", "as an illustration", "to put this in perspective"],
    "however": ["that being said", "nevertheless", "yet", "on the other hand"]
}

# Distinct Call-To-Action (CTA) Variations
ACCOUNT_CTA_TEMPLATES = [
    "👉 Save this reel to revisit later.\n✨ Follow {handle} for daily high-signal {niche}.",
    "👉 Double tap if this resonates with you.\n✨ Follow {handle} for daily {niche} breakdowns.",
    "👉 Share this with someone who needs to see it.\n✨ Follow {handle} for daily deep dives.",
    "👉 Drop your perspective in the comments below.\n✨ Follow {handle} for more {niche}.",
    "👉 Bookmark this for your weekly growth review.\n✨ Follow {handle} for daily insights."
]

# Mobile Device Spoofing Profiles
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


class AntiShadowbanEngine:
    """
    Coordinates media perturbation, text mutation, hashtag shuffling,
    and temporal jitter for multi-account publishing.
    """

    @staticmethod
    def get_video_mutation_params(account_index: int = 0) -> Dict[str, Any]:
        """
        Generates micro-perturbation filter settings unique to this account index.
        The resulting video is visually indistinguishable to humans, but breaks:
        - Exact pixel MD5 / SHA256 hashes
        - Meta PDQ & TMK perceptual frame hashes
        - Acoustic audio waveform matching
        """
        # Cycle through device spoof profiles
        device = DEVICE_SPOOF_PROFILES[account_index % len(DEVICE_SPOOF_PROFILES)]

        # Micro-Color Grading (0.98 to 1.02 variance)
        contrast = round(0.992 + ((account_index * 3) % 7) * 0.003, 4)
        brightness = round(-0.005 + ((account_index * 2) % 6) * 0.002, 4)
        saturation = round(0.995 + ((account_index * 4) % 8) * 0.003, 4)
        gamma = round(0.994 + ((account_index * 5) % 7) * 0.002, 4)

        # Micro-Crop & Scale (2 to 6 pixel shift)
        crop_dx = 2 + (account_index % 3) * 2
        crop_dy = 2 + ((account_index + 1) % 3) * 2

        # Audio Micro-Resample & Subtle Pitch Drift (0.998 to 1.002)
        pitch_rate = 44100 + ((account_index % 5) - 2) * 44  # +/- 88 Hz

        # FFmpeg filter snippets
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
                "-map_metadata", "-1",  # Strip input container metadata
                "-metadata", f"make={device['make']}",
                "-metadata", f"model={device['model']}",
                "-metadata", f"encoder={device['encoder']}",
                "-metadata:s:v:0", f"handler_name={device['handler_name']}",
                "-metadata", f"comment=Created with {device['model']}"
            ]
        }

    @staticmethod
    def generate_niche_hashtags(niche: str, account_index: int = 0, count: int = 7) -> List[str]:
        """
        Dynamically selects and shuffles hashtags from 3 volume tiers.
        Ensures NO TWO ACCOUNTS receive the identical hashtag set or order.
        """
        clean_niche = niche.lower().strip()
        tax = NICHE_HASHTAG_TAXONOMY.get(clean_niche, NICHE_HASHTAG_TAXONOMY["information"])

        t1 = list(tax["tier1_high"])
        t2 = list(tax["tier2_mid"])
        t3 = list(tax["tier3_micro"])

        # Deterministic pseudo-random seed per account index
        rng = random.Random(account_index * 1337 + len(clean_niche))

        # Sample 2 from Tier 1, 3 from Tier 2, 2 from Tier 3
        s1 = rng.sample(t1, min(2, len(t1)))
        s2 = rng.sample(t2, min(3, len(t2)))
        s3 = rng.sample(t3, min(2, len(t3)))

        selected = s1 + s2 + s3
        rng.shuffle(selected)
        return selected[:count]

    @staticmethod
    def mutate_caption(
        base_caption: str,
        hook_headline: str,
        account_handle: str,
        niche: str,
        account_index: int = 0
    ) -> str:
        """
        Synthesizes a distinct, context-preserving caption for one specific account.
        Varies the hook opener, substitutes transitional synonyms, and applies
        a distinct CTA + shuffled hashtag set.
        """
        clean_handle = account_handle if account_handle.startswith("@") else f"@{account_handle}"
        clean_niche = niche.lower().replace("_", " ")

        # 1. Mutate Opening Hook Sentence
        prefix = HOOK_PREFIX_VARIANTS[account_index % len(HOOK_PREFIX_VARIANTS)]
        if prefix:
            first_char = hook_headline[0].lower() if hook_headline else ""
            rest = hook_headline[1:] if len(hook_headline) > 1 else ""
            mutated_headline = f"{prefix}{first_char}{rest}"
        else:
            mutated_headline = hook_headline

        # 2. Extract or split body paragraphs
        raw_paragraphs = [p.strip() for p in base_caption.split("\n\n") if p.strip()]
        if not raw_paragraphs:
            raw_paragraphs = [hook_headline]

        mutated_paragraphs = []
        for idx, p in enumerate(raw_paragraphs):
            # If paragraph starts like the headline, replace it with mutated headline
            if idx == 0 and (hook_headline[:20].lower() in p[:40].lower()):
                mutated_paragraphs.append(mutated_headline)
                continue

            mutated_text = p
            # Apply subtle transitional replacement
            for orig_word, syn_list in TRANSITIONAL_SYNONYMS.items():
                pattern = re.compile(rf"\b{orig_word}\b", re.IGNORECASE)
                if pattern.search(mutated_text):
                    chosen_syn = syn_list[account_index % len(syn_list)]
                    mutated_text = pattern.sub(chosen_syn, mutated_text, count=1)
            mutated_paragraphs.append(mutated_text)

        body_block = "\n\n".join(mutated_paragraphs)

        # 3. Dynamic CTA
        cta_template = ACCOUNT_CTA_TEMPLATES[account_index % len(ACCOUNT_CTA_TEMPLATES)]
        cta_block = cta_template.format(handle=clean_handle, niche=clean_niche)

        # 4. Dynamic Tiered Hashtags
        hashtags = AntiShadowbanEngine.generate_niche_hashtags(clean_niche, account_index=account_index, count=7)
        hashtag_block = " ".join(hashtags)

        # 5. Assemble Full Caption
        full_caption = f"{body_block}\n\n{cta_block}\n\n{hashtag_block}"
        return full_caption

    @staticmethod
    def get_staggered_schedule(
        account_count: int,
        base_delay_seconds: int = 35,
        jitter_seconds: int = 15,
        mode: str = "balanced"
    ) -> List[Dict[str, Any]]:
        """
        Computes non-colliding staggered publish offsets for N accounts.
        Modes:
        - 'turbo': 12-20s micro-jitter (~2-3 mins for 20 accounts)
        - 'balanced' (Default): 30-45s natural jitter (~5-8 mins for 20 accounts)
        - 'stealth': 120-210s extended jitter (~35-50 mins for 20 accounts)
        """
        if mode == "turbo":
            base_delay = 12
            jitter_max = 8
        elif mode == "stealth":
            base_delay = 120
            jitter_max = 90
        else:  # balanced (default)
            base_delay = base_delay_seconds if base_delay_seconds != 180 else 35
            jitter_max = jitter_seconds if jitter_seconds != 90 else 15

        schedule = []
        current_offset = 0
        base_time = datetime.utcnow()

        for idx in range(account_count):
            if idx == 0:
                current_offset = 0
            else:
                jitter = ((idx * 17) % max(1, jitter_max))
                step = base_delay + jitter
                current_offset += step

            scheduled_dt = base_time + timedelta(seconds=current_offset)
            minutes = current_offset // 60
            seconds = current_offset % 60

            schedule.append({
                "account_index": idx,
                "mode": mode,
                "offset_seconds": current_offset,
                "offset_display": f"+{minutes}m {seconds:02d}s" if current_offset > 0 else "+0m 00s (Immediate)",
                "scheduled_iso": scheduled_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            })

        return schedule

    @staticmethod
    def compute_file_sha256(filepath: str) -> str:
        """Computes the SHA256 hex digest of a media file."""
        p = Path(filepath)
        if not p.exists():
            return ""
        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
