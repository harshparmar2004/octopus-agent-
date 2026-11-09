import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

@dataclass
class ChannelProfile:
    handle: str
    display_name: str
    niche: str
    logo_filename: str
    subreddits: List[str]
    default_hashtags: List[str]
    cta_link: str

CHANNELS: Dict[str, ChannelProfile] = {
    "quantum": ChannelProfile(
        handle="@uncover.quantum",
        display_name="UncoverQuantum",
        niche="Quantum Computing, Modern Physics & Deep Tech",
        logo_filename="logo_quantum.png",
        subreddits=["physicsgifs", "QuantumComputing", "educationalgifs", "Physics"],
        default_hashtags=["#quantumphysics", "#quantumcomputing", "#physicsfacts", "#science", "#deeptech", "#techinnovation"],
        cta_link="bit.ly/free-ai-newsletter"
    ),
    "robotics": ChannelProfile(
        handle="@uncover.robotics",
        display_name="UncoverRobotics",
        niche="Humanoid Robotics, Automation & Embodied AI",
        logo_filename="logo_robotics.png",
        subreddits=["robotics", "automation", "Cyberpunk", "technology"],
        default_hashtags=["#robotics", "#humanoidrobot", "#automation", "#ai", "#engineering", "#futuretech"],
        cta_link="bit.ly/free-ai-newsletter"
    ),
    "ai": ChannelProfile(
        handle="@uncover.ai",
        display_name="UncoverAI",
        niche="Artificial Intelligence, Machine Learning & Generative Tech",
        logo_filename="logo_ai.png",
        subreddits=["artificial", "MachineLearning", "singularity", "OpenAI"],
        default_hashtags=["#artificialintelligence", "#machinelearning", "#genai", "#ainews", "#futuretrends"],
        cta_link="bit.ly/free-ai-newsletter"
    )
}

class Settings:
    BASE_DIR = BASE_DIR
    STORAGE_DIR = BASE_DIR / "storage"
    OUTPUT_DIR = BASE_DIR / "output"
    ASSETS_DIR = BASE_DIR / "assets"
    
    # Meta Graph API Credentials
    IG_USER_ID = os.getenv("INSTAGRAM_USER_ID", "")
    META_ACCESS_TOKEN = os.getenv("META_GRAPH_ACCESS_TOKEN", "")
    META_GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v21.0")
    INSTAGRAM_USER_ID = IG_USER_ID
    META_GRAPH_ACCESS_TOKEN = META_ACCESS_TOKEN
    
    # LLM Settings (Groq, Ollama, Gemini, OpenAI, Claude, Grok)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    XAI_API_KEY = os.getenv("XAI_API_KEY", "")
    
    # Storage / Public URL
    STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local_tunnel")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Proxy & Scraper Settings (Optional for High-Scale 500+ Account Instagram Scraping)
    SCRAPER_PROXY = os.getenv("SCRAPER_PROXY", "")
    INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "")
    
    # Default active channel
    DEFAULT_CHANNEL_KEY = os.getenv("DEFAULT_CHANNEL", "quantum")

    @classmethod
    def get_channel(cls, key: str = None) -> ChannelProfile:
        return CHANNELS.get(key or cls.DEFAULT_CHANNEL_KEY, CHANNELS["quantum"])

settings = Settings()
