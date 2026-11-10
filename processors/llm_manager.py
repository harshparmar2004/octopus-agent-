import os
import json
import time
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from config import settings
from renderers.niche_templates import get_template_for_niche

logger = logging.getLogger("LLMManager")

CONFIG_PATH = settings.STORAGE_DIR / "llm_config.json"

DEFAULT_CONFIG = {
    "provider": "gemini",
    "model": "gemini-1.5-flash",
    "api_key": "",
    "base_url": "",
    "temperature": 0.7,
    "system_persona": "viral_curiosity",
    "status": "CONFIGURED"
}

PROVIDER_DEFAULTS = {
    "grok": {
        "name": "xAI Grok",
        "default_model": "grok-2",
        "models": ["grok-2", "grok-2-mini", "grok-beta"],
        "base_url": "https://api.x.ai/v1",
        "env_key": "XAI_API_KEY"
    },
    "openai": {
        "name": "OpenAI ChatGPT",
        "default_model": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY"
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_model": "claude-3-5-sonnet-20241022",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY"
    },
    "gemini": {
        "name": "Google Gemini",
        "default_model": "gemini-1.5-flash",
        "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
        "base_url": "https://generativelanguage.googleapis.com",
        "env_key": "GEMINI_API_KEY"
    },
    "groq": {
        "name": "Groq Cloud (Ultra-Fast Free Tier — Llama & Open Models)",
        "default_model": "llama-3.3-70b-versatile",
        "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it", "qwen-2.5-32b"],
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY"
    },
    "ollama": {
        "name": "Ollama (Local / Self-Hosted Open Weights)",
        "default_model": "llama3.2",
        "models": ["llama3.2", "llama3.1", "mistral", "deepseek-r1", "qwen2.5"],
        "base_url": "http://localhost:11434/v1",
        "env_key": "OLLAMA_API_KEY"
    },
    "custom": {
        "name": "Custom / Local OpenAI-Compatible (Ollama, DeepSeek, vLLM)",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-r1", "llama3.2", "mistral"],
        "base_url": "http://localhost:11434/v1",
        "env_key": "CUSTOM_LLM_API_KEY"
    }
}

class LLMManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMManager, cls).__new__(cls)
            cls._instance._init_manager()
        return cls._instance

    def _init_manager(self):
        settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.config = dict(DEFAULT_CONFIG)
        self.config = self.load_config()
        self.last_execution_trace: Optional[Dict[str, Any]] = None

    def load_config(self) -> Dict[str, Any]:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    cfg = dict(DEFAULT_CONFIG)
                    cfg.update(saved)
                    return cfg
            except Exception as e:
                logger.error(f"Error reading llm_config.json: {e}")
        
        cfg = dict(DEFAULT_CONFIG)
        if os.getenv("XAI_API_KEY"):
            cfg["provider"] = "grok"
            cfg["model"] = "grok-2"
            cfg["api_key"] = os.getenv("XAI_API_KEY")
            cfg["base_url"] = "https://api.x.ai/v1"
        elif os.getenv("OPENAI_API_KEY"):
            cfg["provider"] = "openai"
            cfg["model"] = "gpt-4o"
            cfg["api_key"] = os.getenv("OPENAI_API_KEY")
            cfg["base_url"] = "https://api.openai.com/v1"
        elif os.getenv("ANTHROPIC_API_KEY"):
            cfg["provider"] = "claude"
            cfg["model"] = "claude-3-5-sonnet-20241022"
            cfg["api_key"] = os.getenv("ANTHROPIC_API_KEY")
        elif os.getenv("GROQ_API_KEY"):
            cfg["provider"] = "groq"
            cfg["model"] = "llama-3.3-70b-versatile"
            cfg["api_key"] = os.getenv("GROQ_API_KEY")
            cfg["base_url"] = "https://api.groq.com/openai/v1"
        elif os.getenv("GEMINI_API_KEY"):
            cfg["provider"] = "gemini"
            cfg["model"] = "gemini-1.5-flash"
            cfg["api_key"] = os.getenv("GEMINI_API_KEY")
        
        self.save_config(cfg)
        return cfg

    def save_config(self, new_config: Dict[str, Any]):
        self.config = {**self.config, **new_config}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Saved LLM config: provider={self.config.get('provider')}, model={self.config.get('model')}")

    def get_public_config(self) -> Dict[str, Any]:
        c = dict(self.config)
        key = c.get("api_key", "")
        if key and len(key) > 8:
            c["masked_key"] = key[:4] + "••••••••" + key[-4:]
        elif key:
            c["masked_key"] = "••••••••"
        else:
            c["masked_key"] = ""
        c["has_key"] = bool(key)
        del c["api_key"]
        c["providers_info"] = PROVIDER_DEFAULTS
        return c

    def test_connection(self, provider: str, model: str, api_key: str, base_url: Optional[str] = None) -> Dict[str, Any]:
        start = time.time()
        test_prompt = "Write a 1-sentence viral scientific curiosity hook about magnetic levitation. Output JSON: {\"hook\": \"...\"}"
        
        try:
            if api_key in ["demo", "mock", "test"]:
                time.sleep(0.18)
                hook = "MAGNETIC FIELDS CAN SUSPEND MATTER WITHOUT FRICTION"
                return {
                    "success": True,
                    "status": "connected",
                    "provider": provider,
                    "model": model,
                    "latency_ms": 182,
                    "sample": f'{{"hook": "{hook}"}}',
                    "sample_hook": hook,
                    "message": f"Connected to {provider.upper()} ({model}) in 182ms! Handshake verified (Test Mode)."
                }

            if not api_key:
                # If testing with saved key
                if self.config.get("api_key") and self.config.get("provider") == provider:
                    api_key = self.config["api_key"]
                else:
                    return {"success": False, "status": "error", "error": f"Please enter your {provider.upper()} API key to perform live connection test."}

            if provider in ["openai", "grok", "groq", "ollama", "custom"]:
                endpoint = (base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "https://api.openai.com/v1")).rstrip("/") + "/chat/completions"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": test_prompt}],
                    "temperature": 0.7
                }
                res = requests.post(endpoint, json=payload, headers=headers, timeout=12)
                latency_ms = int((time.time() - start) * 1000)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return {
                        "success": True,
                        "status": "connected",
                        "provider": provider,
                        "model": model,
                        "latency_ms": latency_ms,
                        "sample": content.strip()[:180],
                        "sample_hook": content.strip()[:180],
                        "message": f"Connected to {provider.upper()} ({model}) in {latency_ms}ms! Handshake verified."
                    }
                else:
                    return {"success": False, "status": "error", "error": f"HTTP {res.status_code}: {res.text[:200]}"}

            elif provider == "claude":
                endpoint = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model,
                    "max_tokens": 250,
                    "messages": [{"role": "user", "content": test_prompt}]
                }
                res = requests.post(endpoint, json=payload, headers=headers, timeout=12)
                latency_ms = int((time.time() - start) * 1000)
                if res.status_code == 200:
                    data = res.json()
                    content = data["content"][0]["text"]
                    return {
                        "success": True,
                        "status": "connected",
                        "provider": provider,
                        "model": model,
                        "latency_ms": latency_ms,
                        "sample": content.strip()[:180],
                        "sample_hook": content.strip()[:180],
                        "message": f"Connected to Claude ({model}) in {latency_ms}ms! Handshake verified."
                    }
                else:
                    return {"success": False, "status": "error", "error": f"HTTP {res.status_code}: {res.text[:200]}"}

            elif provider == "gemini":
                endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {"contents": [{"parts": [{"text": test_prompt}]}]}
                res = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
                latency_ms = int((time.time() - start) * 1000)
                if res.status_code == 200:
                    data = res.json()
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    return {
                        "success": True,
                        "status": "connected",
                        "provider": provider,
                        "model": model,
                        "latency_ms": latency_ms,
                        "sample": content.strip()[:180],
                        "sample_hook": content.strip()[:180],
                        "message": f"Connected to Gemini ({model}) in {latency_ms}ms! Handshake verified."
                    }
                else:
                    return {"success": False, "status": "error", "error": f"HTTP {res.status_code}: {res.text[:200]}"}

            return {"success": False, "status": "error", "error": f"Unsupported provider: {provider}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def synthesize_reel(
        self,
        title: str,
        description: str,
        niche: str,
        channel_handle: str = "@info.daily",
        formula: str = "curiosity"
    ) -> Dict[str, Any]:
        start = time.time()
        cfg = self.config
        provider = cfg.get("provider", "gemini")
        model = cfg.get("model", "gemini-1.5-flash")
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url", "")

        # Resolve template for niche
        template = get_template_for_niche(niche)

        system_instruction = template.persona_system_instruction.format(
            channel_handle=channel_handle,
            niche=niche
        )
        system_instruction += """
Respond strictly with valid JSON schema:
{
  "hook_text": "...",
  "caption_paragraphs": ["...", "..."],
  "credit": "...",
  "hashtags": ["#...", "#..."]
}"""

        user_content = f"Video Title: {title}\nContext / Description: {description[:800]}\nFormula: {formula}\nNiche Template: {template.name}"
        prompt_str = f"{system_instruction}\n\n{user_content}"

        parsed = None
        if api_key:
            try:
                if provider in ["openai", "grok", "groq", "ollama", "custom"]:
                    endpoint = (base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "https://api.openai.com/v1")).rstrip("/") + "/chat/completions"
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": user_content}
                        ],
                        "temperature": 0.7
                    }
                    res = requests.post(endpoint, json=payload, headers=headers, timeout=20)
                    if res.status_code == 200:
                        raw = res.json()["choices"][0]["message"]["content"]
                        clean_raw = raw.strip()
                        if clean_raw.startswith("```json"):
                            clean_raw = clean_raw[7:-3].strip()
                        elif clean_raw.startswith("```"):
                            clean_raw = clean_raw[3:-3].strip()
                        parsed = json.loads(clean_raw)

                elif provider == "claude":
                    endpoint = "https://api.anthropic.com/v1/messages"
                    headers = {
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": model,
                        "system": system_instruction,
                        "messages": [{"role": "user", "content": user_content}],
                        "max_tokens": 1000,
                        "temperature": 0.7
                    }
                    res = requests.post(endpoint, json=payload, headers=headers, timeout=20)
                    if res.status_code == 200:
                        raw = res.json()["content"][0]["text"]
                        clean_raw = raw.strip()
                        if clean_raw.startswith("```json"):
                            clean_raw = clean_raw[7:-3].strip()
                        elif clean_raw.startswith("```"):
                            clean_raw = clean_raw[3:-3].strip()
                        parsed = json.loads(clean_raw)

                elif provider == "gemini":
                    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{
                            "parts": [{"text": prompt_str}]
                        }],
                        "generationConfig": {"temperature": 0.7}
                    }
                    res = requests.post(endpoint, json=payload, headers=headers, timeout=20)
                    if res.status_code == 200:
                        candidates = res.json().get("candidates", [])
                        if candidates:
                            raw = candidates[0]["content"]["parts"][0]["text"]
                            clean_raw = raw.strip()
                            if clean_raw.startswith("```json"):
                                clean_raw = clean_raw[7:-3].strip()
                            elif clean_raw.startswith("```"):
                                clean_raw = clean_raw[3:-3].strip()
                            parsed = json.loads(clean_raw)
            except Exception as e:
                logger.warning(f"Error calling {provider}: {e}")

        # Template-specific fallback if LLM offline
        if not parsed or not isinstance(parsed, dict) or "hook_text" not in parsed:
            if template.caption_format == "numbered_checklist":
                parsed = {
                    "hook_text": template.sample_headline,
                    "caption_paragraphs": [
                        "Step 1: Clear and wipe down all surfaces completely before sorting goods by daily usage frequency.",
                        "Step 2: Decant staples into clear labeled airtight canisters to eliminate visual clutter instantly.",
                        "Step 3: Keep a designated overflow bin on the bottom shelf so incoming items never break the system."
                    ],
                    "credit": "@organize.daily / minimalist storage archives",
                    "hashtags": template.default_hashtags
                }
            elif template.caption_format == "hype_punchline":
                parsed = {
                    "hook_text": template.sample_headline,
                    "caption_paragraphs": [
                        "The energy peaked at 3:45 AM when this unreleased drop shook the entire pavilion — complete pure euphoria on the dancefloor.",
                        "Track ID: Afterlife Horizons (Original Mix). Save this sound for your weekend festival playlist and tag your crew below!"
                    ],
                    "credit": "@afterhours.club / live set archives",
                    "hashtags": template.default_hashtags
                }
            elif template.caption_format == "editorial_lookbook":
                parsed = {
                    "hook_text": template.sample_headline,
                    "caption_paragraphs": [
                        "The formula centers around balancing an oversized relaxed silhouette with structured high-waisted tailored linen trousers.",
                        "Tonal neutral layering in cream, oat, and espresso creates an understated quiet luxury depth without loud logos.",
                        "Which piece would you style this with: look 1 (leather slides) or look 2 (minimalist slingback heels)?"
                    ],
                    "credit": "@chic.rotation / style lookbook archives",
                    "hashtags": template.default_hashtags
                }
            else:
                # Default educational format
                parsed = {
                    "hook_text": template.sample_headline,
                    "caption_paragraphs": [
                        f"When examining {title.lower() or 'this phenomenon'}, researchers discovered a fundamental principle that explains how these forces operate.",
                        f"Under controlled observation, the interaction demonstrates intricate dynamics that conventional models frequently overlook.",
                        f"This breakthrough offers compelling insights for future applications. Follow {channel_handle} for daily deep-dive breakdowns."
                    ],
                    "credit": "via original source / open archives",
                    "hashtags": template.default_hashtags
                }

        latency_ms = int((time.time() - start) * 1000)
        paragraphs = parsed.get("caption_paragraphs", [])
        body = "\n\n".join(paragraphs)
        credit = parsed.get("credit", "via original source")
        hashtags = " ".join(parsed.get("hashtags", template.default_hashtags))

        full_caption = (
            f"{body}\n\n"
            f"🔬 Credit: {credit}\n"
            f"✨ Follow {channel_handle} for daily {niche.lower()} inspiration.\n"
            f"💬 Share your thoughts in the comments below!\n\n"
            f"{hashtags}"
        )

        trace = {
            "provider": provider,
            "model": model,
            "template_id": template.id,
            "template_name": template.name,
            "highlight_color": template.highlight_color,
            "latency_ms": latency_ms,
            "prompt": prompt_str,
            "hook_text": parsed.get("hook_text", template.sample_headline),
            "caption_paragraphs": paragraphs,
            "full_caption": full_caption,
            "credit": credit,
            "hashtags": hashtags,
            "tokens_used": len(prompt_str.split()) + len(full_caption.split()),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.last_execution_trace = trace

        return trace
