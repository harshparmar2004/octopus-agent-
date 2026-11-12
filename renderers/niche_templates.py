"""
Niche Template System for Octopus Agent
Defines visual layouts, color palettes, typography, and AI copywriting formulas per niche.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class NicheTemplate(BaseModel):
    id: str
    name: str
    category: str
    overlay_layout: str               # 'top_card_cult', 'center_kinetic', 'minimal_step_bar', 'editorial_lower_third'
    primary_color: str                # Hex color for main text
    highlight_color: str              # Hex color for glowing/accent word
    card_background: str              # RGBA / Hex for card surface
    font_family: str                  # 'sans_bold', 'punchy_kinetic', 'clean_humanist', 'serif_editorial'
    badge_icon: str                   # Emoji badge
    hook_formula: str                 # 'curiosity_paradox', 'fomo_hype', 'satisfying_routine', 'aesthetic_vibe', 'contrarian_wealth'
    caption_format: str               # 'three_paragraph_depth', 'hype_punchline', 'numbered_checklist', 'editorial_lookbook'
    persona_system_instruction: str
    default_hashtags: List[str]
    sample_headline: str
    sample_highlight: str
    audio_ducking: bool = True
    speed_factor: float = 1.0

# 1. Informative & Deep Tech (Cult Aesthetic)
TEMPLATE_INFORMATIVE = NicheTemplate(
    id="informative_cult",
    name="Cult Aesthetic (Informative, Science & Deep Tech)",
    category="informative",
    overlay_layout="top_card_cult",
    primary_color="#FFFFFF",
    highlight_color="#DDF51A",        # High-contrast Neon Yellow
    card_background="rgba(10, 10, 10, 0.85)",
    font_family="sans_bold",
    badge_icon="💡",
    hook_formula="curiosity_paradox",
    caption_format="three_paragraph_depth",
    persona_system_instruction=(
        "You are the chief viral media curator for {channel_handle} specializing in {niche}. "
        "Objective: craft an educational 9:16 vertical reel package from source video metadata: "
        "1. 'hook_text': 10 to 18 words on-screen headline. Direct, observational, curiosity-inducing, scientific authority. No exclamation marks, no spammy words. "
        "2. 'caption_paragraphs': Exactly 3 paragraphs. Para 1: Phenomenon hook. Para 2: Underlying science/mechanics. Para 3: Key takeaway and CTA to discuss. "
        "3. 'credit': Original researcher or attribution tag. "
        "4. 'hashtags': 8 to 12 targeted hashtags."
    ),
    default_hashtags=["#information", "#science", "#tech", "#curiosity", "#knowledge", "#didyouknow", "#deepfacts"],
    sample_headline="Two people can earn the exact same salary and end up living completely different lives",
    sample_highlight="completely",
    audio_ducking=True,
    speed_factor=1.0
)

# 2. Parties, Nightlife & EDM
TEMPLATE_NIGHTLIFE = NicheTemplate(
    id="nightlife_party",
    name="Electric Kinetic (Parties, EDM & Nightlife)",
    category="nightlife",
    overlay_layout="center_kinetic",
    primary_color="#FFFFFF",
    highlight_color="#FF007F",        # Electric Hot Pink / Neon
    card_background="rgba(15, 5, 25, 0.88)",
    font_family="punchy_kinetic",
    badge_icon="🎉",
    hook_formula="fomo_hype",
    caption_format="hype_punchline",
    persona_system_instruction=(
        "You are the head curator for {channel_handle} covering nightlife, EDM festivals, DJ sets, and after-hours party culture. "
        "Objective: craft an ultra-high energy viral reel package. "
        "1. 'hook_text': 8 to 14 words ultra-punchy FOMO hook capturing intense crowd energy. "
        "2. 'caption_paragraphs': Exactly 2 short punchy blocks. Block 1: The sheer vibe, venue name, and moment of peak energy. Block 2: Track ID / DJ sound credit and a hype CTA to save for the weekend. "
        "3. 'credit': DJ, producer, or festival credit tag. "
        "4. 'hashtags': 8 to 12 nightlife and EDM hashtags."
    ),
    default_hashtags=["#nightlife", "#edmlifestyle", "#partyvibes", "#techno", "#festivalvibes", "#clubbing", "#raveculture", "#djset"],
    sample_headline="The exact moment the entire crowd lost their minds when this drop hit in Tulum",
    sample_highlight="lost their minds",
    audio_ducking=False,
    speed_factor=1.04
)

# 3. Home Organizing, CleanTok & ASMR
TEMPLATE_ORGANIZING = NicheTemplate(
    id="organizing_home",
    name="Scandinavian Minimalist (Home Organizing & CleanTok)",
    category="organizing",
    overlay_layout="minimal_step_bar",
    primary_color="#1C1917",
    highlight_color="#84A98C",        # Soothing Sage Green
    card_background="rgba(245, 235, 224, 0.94)", # Warm Linen
    font_family="clean_humanist",
    badge_icon="🧺",
    hook_formula="satisfying_routine",
    caption_format="numbered_checklist",
    persona_system_instruction=(
        "You are the minimalist home aesthetic director for {channel_handle} specializing in home organization, decluttering, Sunday resets, and ASMR storage systems. "
        "Objective: craft a calming, deeply satisfying reel package. "
        "1. 'hook_text': 10 to 16 words promising an effortless, clutter-free transformation. "
        "2. 'caption_paragraphs': Exactly 3 numbered checklist steps. Step 1: Sorting/decluttering rule. Step 2: Container/labeling technique. Step 3: High-frequency maintenance tip. "
        "3. 'credit': Original creator or organizer link credit. "
        "4. 'hashtags': 8 to 12 organization and clean home hashtags."
    ),
    default_hashtags=["#organizationhacks", "#sundayreset", "#cleantok", "#pantryorganization", "#minimalisthome", "#asmrcleaning", "#declutter"],
    sample_headline="The 15-minute Sunday pantry reset routine that permanently eliminates clutter",
    sample_highlight="permanently",
    audio_ducking=True,
    speed_factor=1.0
)

# 4. Fashion, Beauty & Chic Lifestyle
TEMPLATE_FASHION = NicheTemplate(
    id="fashion_editorial",
    name="Vogue Editorial (Fashion, Beauty & Chic Lifestyle)",
    category="fashion",
    overlay_layout="editorial_lower_third",
    primary_color="#FAF8F5",
    highlight_color="#D4AF37",        # Champagne Gold
    card_background="rgba(18, 18, 18, 0.82)",
    font_family="serif_editorial",
    badge_icon="✨",
    hook_formula="aesthetic_vibe",
    caption_format="editorial_lookbook",
    persona_system_instruction=(
        "You are the fashion editor and wardrobe stylist for {channel_handle} specializing in capsule wardrobes, clean girl aesthetic, and quiet luxury. "
        "Objective: craft an effortlessly chic reel package. "
        "1. 'hook_text': 8 to 14 words establishing an aspirational styling rule or outfit equation. "
        "2. 'caption_paragraphs': 3 structured blocks. Block 1: Outfit formula breakdown. Block 2: Fit, silhouette balance, and fabric texture notes. Block 3: Interactive styling poll. "
        "3. 'credit': Designer, stylist, or model credit tag. "
        "4. 'hashtags': 8 to 12 fashion and aesthetic hashtags."
    ),
    default_hashtags=["#outfitinspo", "#capsulewardrobe", "#cleangirlstyle", "#aestheticfits", "#styleguide", "#parisianstyle", "#quietluxury"],
    sample_headline="The 3-layer French-girl capsule outfit formula that looks effortlessly expensive",
    sample_highlight="effortlessly expensive",
    audio_ducking=True,
    speed_factor=1.0
)

# 5. Finance, Crypto & Wealth
TEMPLATE_FINANCE = NicheTemplate(
    id="wealth_crypto",
    name="Cyber Wealth (Finance, Crypto & Investing)",
    category="finance",
    overlay_layout="top_card_cult",
    primary_color="#FFFFFF",
    highlight_color="#10B981",        # Emerald Mint Green
    card_background="rgba(10, 16, 13, 0.88)",
    font_family="sans_bold",
    badge_icon="📈",
    hook_formula="contrarian_wealth",
    caption_format="three_paragraph_depth",
    persona_system_instruction=(
        "You are the macro-economic and investment research director for {channel_handle}. "
        "Objective: craft an asymmetric market insight reel package: "
        "1. 'hook_text': 10 to 16 words contrarian financial revelation contrasting retail traps vs institutional moves. "
        "2. 'caption_paragraphs': 3 structured blocks. Block 1: The market misconception. Block 2: Data/mechanism breakdown. Block 3: Risk management takeaway. "
        "3. 'credit': Source market analyst or chart data source. "
        "4. 'hashtags': 8 to 12 finance and investing hashtags."
    ),
    default_hashtags=["#personalfinance", "#investing101", "#wealthbuilding", "#crypto", "#stocks", "#financialfreedom", "#moneyhacks"],
    sample_headline="Why 90% of retail investors buy the exact top while institutions accumulate silently",
    sample_highlight="accumulate silently",
    audio_ducking=True,
    speed_factor=1.0
)

# 6. Fitness, Gym & Raw Discipline
TEMPLATE_FITNESS = NicheTemplate(
    id="fitness_beast",
    name="Raw Intensity (Fitness, Gym & Bodybuilding)",
    category="fitness",
    overlay_layout="center_kinetic",
    primary_color="#FFFFFF",
    highlight_color="#EF4444",        # Crimson Fire Red
    card_background="rgba(20, 6, 6, 0.90)",
    font_family="punchy_kinetic",
    badge_icon="🏋️",
    hook_formula="fomo_hype",
    caption_format="hype_punchline",
    persona_system_instruction=(
        "You are the elite strength coach and high-performance director for {channel_handle}. "
        "Objective: deliver a raw, zero-excuses viral lifting and athletic breakdown: "
        "1. 'hook_text': 8 to 14 words visceral cue on form mastery, mechanical tension, or mental discipline. "
        "2. 'caption_paragraphs': 2 intense blocks. Block 1: The bio-mechanical mistake holding athletes back. Block 2: The exact execution cue to implement next workout. "
        "3. 'credit': Athlete or lifter credit tag. "
        "4. 'hashtags': 8 to 12 fitness and gym hashtags."
    ),
    default_hashtags=["#gymmotivation", "#bodybuilding", "#hypertrophy", "#workouttips", "#fitnesstips", "#discipline", "#legday"],
    sample_headline="The single pelvic tilt adjustment that doubles hamstring tension instantly",
    sample_highlight="doubles hamstring tension",
    audio_ducking=False,
    speed_factor=1.02
)

# 7. Cinematic Travel, Food & Hidden Gems
TEMPLATE_TRAVEL = NicheTemplate(
    id="travel_cinema",
    name="Cinematic Wanderlust (Travel, Food & Hidden Gems)",
    category="travel",
    overlay_layout="editorial_lower_third",
    primary_color="#FAF8F5",
    highlight_color="#F97316",        # Sunset Tangerine
    card_background="rgba(18, 12, 10, 0.85)",
    font_family="serif_editorial",
    badge_icon="✈️",
    hook_formula="aesthetic_vibe",
    caption_format="editorial_lookbook",
    persona_system_instruction=(
        "You are the travel documentary producer and luxury explorer for {channel_handle}. "
        "Objective: craft a wanderlust cinematic reel package: "
        "1. 'hook_text': 8 to 15 words transporting viewers into a hidden secret or breathtaking destination. "
        "2. 'caption_paragraphs': 3 evocative blocks. Block 1: Location name, coordinates, and scenic atmosphere. Block 2: Local culinary secret or insider tip. Block 3: How to reach it and best season to visit. "
        "3. 'credit': Creator or filmmaker credit tag. "
        "4. 'hashtags': 8 to 12 travel and adventure hashtags."
    ),
    default_hashtags=["#travelgram", "#hiddengems", "#wanderlust", "#bucketlist", "#exploremore", "#cinematictravel", "#beautifuldestinations"],
    sample_headline="The secret volcanic hot springs in Northern Iceland that tourists walk right past",
    sample_highlight="secret volcanic hot springs",
    audio_ducking=True,
    speed_factor=1.0
)

# 8. Psychology, Philosophy & Mental Models
TEMPLATE_PSYCHOLOGY = NicheTemplate(
    id="psychology_depth",
    name="Stoic Wisdom (Psychology & Mental Models)",
    category="psychology",
    overlay_layout="minimal_step_bar",
    primary_color="#18181B",
    highlight_color="#8B5CF6",        # Deep Royal Violet
    card_background="rgba(244, 244, 248, 0.95)",
    font_family="clean_humanist",
    badge_icon="🧠",
    hook_formula="curiosity_paradox",
    caption_format="numbered_checklist",
    persona_system_instruction=(
        "You are the cognitive psychologist and philosophical strategist for {channel_handle}. "
        "Objective: craft a profound, high-retention mental model reel: "
        "1. 'hook_text': 10 to 16 words exposing an everyday psychological blindspot or ancient stoic truth. "
        "2. 'caption_paragraphs': 3 actionable steps. Step 1: Cognitive bias identified. Step 2: Psychological reframing tool. Step 3: Daily behavioral anchor. "
        "3. 'credit': Author, psychologist, or philosophical origin. "
        "4. 'hashtags': 8 to 12 psychology and mental model hashtags."
    ),
    default_hashtags=["#psychologyfacts", "#mentalmodels", "#stoicism", "#mindsetshift", "#selfmastery", "#criticalthinking", "#humanbehavior"],
    sample_headline="The subtle psychological defense mechanism that silently sabotages high achievers",
    sample_highlight="silently sabotages",
    audio_ducking=True,
    speed_factor=1.0
)

# Master Registry of All Templates
DEFAULT_TEMPLATES: Dict[str, NicheTemplate] = {
    "informative_cult": TEMPLATE_INFORMATIVE,
    "nightlife_party": TEMPLATE_NIGHTLIFE,
    "organizing_home": TEMPLATE_ORGANIZING,
    "fashion_editorial": TEMPLATE_FASHION,
    "wealth_crypto": TEMPLATE_FINANCE,
    "fitness_beast": TEMPLATE_FITNESS,
    "travel_cinema": TEMPLATE_TRAVEL,
    "psychology_depth": TEMPLATE_PSYCHOLOGY,
}

# Mapping from Niche IDs to Template IDs
NICHE_TO_TEMPLATE_MAP: Dict[str, str] = {
    # 1. Informative / Science / Deep Tech
    "information": "informative_cult",
    "quantum": "informative_cult",
    "robotics": "informative_cult",
    "ai": "informative_cult",
    "space": "informative_cult",
    "biotech": "informative_cult",
    "science": "informative_cult",
    "history": "informative_cult",
    "technology": "informative_cult",

    # 2. Nightlife / EDM / Parties
    "parties": "nightlife_party",
    "nightlife": "nightlife_party",
    "girls_party": "nightlife_party",
    "girls_nightlife": "nightlife_party",
    "edm": "nightlife_party",
    "music": "nightlife_party",
    "festivals": "nightlife_party",

    # 3. Home / CleanTok / Organizing
    "organizing": "organizing_home",
    "cleantok": "organizing_home",
    "home": "organizing_home",
    "asmr": "organizing_home",
    "diy": "organizing_home",

    # 4. Fashion / Beauty / Luxury
    "fashion": "fashion_editorial",
    "beauty": "fashion_editorial",
    "girls": "fashion_editorial",
    "lifestyle": "fashion_editorial",
    "luxury": "fashion_editorial",
    "skincare": "fashion_editorial",

    # 5. Finance / Crypto / Real Estate
    "finance": "wealth_crypto",
    "crypto": "wealth_crypto",
    "investing": "wealth_crypto",
    "money": "wealth_crypto",
    "realestate": "wealth_crypto",
    "business": "wealth_crypto",
    "startups": "wealth_crypto",

    # 6. Fitness / Gym / Motivation
    "fitness": "fitness_beast",
    "gym": "fitness_beast",
    "workout": "fitness_beast",
    "motivation": "fitness_beast",
    "bodybuilding": "fitness_beast",
    "health": "fitness_beast",

    # 7. Travel / Hidden Gems / Food
    "travel": "travel_cinema",
    "adventure": "travel_cinema",
    "food": "travel_cinema",
    "nature": "travel_cinema",
    "destinations": "travel_cinema",

    # 8. Psychology / Philosophy / Mindset
    "psychology": "psychology_depth",
    "mindset": "psychology_depth",
    "philosophy": "psychology_depth",
    "stoicism": "psychology_depth",
    "books": "psychology_depth",
}

def get_template_for_niche(niche_id: str) -> NicheTemplate:
    """Resolves the best matching template for a given niche identifier."""
    clean_niche = niche_id.lower().strip()
    template_id = NICHE_TO_TEMPLATE_MAP.get(clean_niche, "informative_cult")
    return DEFAULT_TEMPLATES.get(template_id, TEMPLATE_INFORMATIVE)

def get_template_by_id(template_id: str) -> Optional[NicheTemplate]:
    """Retrieves a template by its unique template ID."""
    return DEFAULT_TEMPLATES.get(template_id)

def list_all_templates() -> List[Dict[str, Any]]:
    """Returns a list of all available templates serialized as dictionaries."""
    return [t.model_dump() for t in DEFAULT_TEMPLATES.values()]

def register_custom_template(template: NicheTemplate) -> NicheTemplate:
    """Registers a new or updated template into the active registry."""
    DEFAULT_TEMPLATES[template.id] = template
    return template
