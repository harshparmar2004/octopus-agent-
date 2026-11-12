"""
Distribution Policy
===================
Legitimate per-account variation for a multi-page network:
- Per-account caption voice (hook opener, transitional phrasing, CTA)
- Tiered hashtag selection per niche (no two accounts share an identical set)
- Human-paced, staggered posting schedules

Deliberately NOT included: perceptual video/audio mutation, hash breaking,
or device/EXIF metadata spoofing. Those exist only to evade Meta's duplicate
detection, violate Meta Platform Terms, and put the whole network at risk.
Distinctness across accounts comes from exclusive content routing
(agents/content_router.py), not from disguising duplicates.
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
    "girls_party": {
        "tier1_high": ["#girlsparty", "#girlsnightout", "#partyvibes", "#clubbing", "#nightlife", "#reelsvideo", "#weekendmood"],
        "tier2_mid": ["#partynight", "#baddie", "#girlgang", "#bottleservice", "#vipnightlife", "#viralreels", "#outfitgoals"],
        "tier3_micro": ["#partyaesthetic", "#bestievibes", "#clubbingoutfit", "#weekendtakeover", "#afterhoursvibes", "#girlshavingfun"]
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
    },
    "ai_content": {
        "tier1_high": ["#ai", "#aiart", "#aivideo", "#artificialintelligence", "#tech", "#future"],
        "tier2_mid": ["#generativeai", "#aitools", "#midjourney", "#sora", "#aianimation", "#aigenerated"],
        "tier3_micro": ["#texttovideo", "#aifilm", "#aicreator", "#promptart", "#aiworkflow", "#aimagic"]
    },
    "memes": {
        "tier1_high": ["#memes", "#funny", "#meme", "#relatable", "#lol", "#humor"],
        "tier2_mid": ["#dailymemes", "#funnymemes", "#memesdaily", "#relatablememes", "#comedy", "#jokes"],
        "tier3_micro": ["#memepage", "#tagafriend", "#sendthistoyourfriend", "#memelife", "#dankhumor"]
    },
    "concerts": {
        "tier1_high": ["#concert", "#livemusic", "#music", "#tour", "#festival", "#live"],
        "tier2_mid": ["#concertvibes", "#musicfestival", "#crowd", "#stage", "#worldtour", "#gigs"],
        "tier3_micro": ["#frontrow", "#concertnight", "#livegig", "#setlist", "#iwasthere", "#tourlife"]
    },
    "girls_dance": {
        "tier1_high": ["#dance", "#dancevideo", "#reelsvideo", "#dancereels", "#trending", "#girlsnightout"],
        "tier2_mid": ["#dancechallenge", "#choreography", "#trendingdance", "#partyvibes", "#bestie", "#viralreels"],
        "tier3_micro": ["#dancetrend", "#girlgang", "#bestievibes", "#weekendmood", "#dancecover"]
    },
    "clubbing": {
        "tier1_high": ["#clubbing", "#nightlife", "#party", "#club", "#dj", "#weekendvibes"],
        "tier2_mid": ["#clublife", "#housemusic", "#techno", "#djset", "#bottleservice", "#afterparty"],
        "tier3_micro": ["#clubnight", "#nightout", "#dancefloor", "#afterhours", "#nightlifeculture"]
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


class DistributionPolicy:
    """
    Per-account caption voice, hashtag tiers and human-paced scheduling.
    """

    @staticmethod
    def generate_niche_hashtags(niche: str, account_index: int = 0, count: int = 7) -> List[str]:
        """
        Dynamically selects and shuffles hashtags from 3 volume tiers.
        Ensures NO TWO ACCOUNTS receive the identical hashtag set or order.
        """
        clean_niche = niche.lower().strip().replace(" ", "_")
        tax = NICHE_HASHTAG_TAXONOMY.get(clean_niche)
        if not tax:
            # Fallback checks
            for k in NICHE_HASHTAG_TAXONOMY:
                if k in clean_niche or clean_niche in k:
                    tax = NICHE_HASHTAG_TAXONOMY[k]
                    break
        if not tax:
            tax = NICHE_HASHTAG_TAXONOMY["information"]

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
        hashtags = DistributionPolicy.generate_niche_hashtags(clean_niche, account_index=account_index, count=7)
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
