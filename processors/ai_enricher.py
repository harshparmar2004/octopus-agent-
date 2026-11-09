import os
import re
import json
import logging
from typing import Dict, Any, Optional
import requests

from config import settings, ChannelProfile

from processors.llm_manager import LLMManager

logger = logging.getLogger("AIEnricher")

class AIEnricher:
    def __init__(self, api_key: Optional[str] = None):
        self.llm_manager = LLMManager()
        if api_key:
            self.llm_manager.config["api_key"] = api_key

    def generate_hook_and_caption(self, title: str, description: str, channel: ChannelProfile, formula: str = "curiosity") -> Dict[str, Any]:
        """
        Uses active LLM Brain (Grok, ChatGPT, Claude, Gemini, Custom) to generate:
        1. On-Screen Hook / Headline
        2. Instagram Caption (3 paragraphs + Credit + CTA)
        3. Hashtags
        """
        trace = self.llm_manager.synthesize_reel(
            title=title,
            description=description,
            niche=getattr(channel, "niche", "Information"),
            channel_handle=getattr(channel, "handle", "@info.daily"),
            formula=formula
        )
        return {
            "hook_text": trace.get("hook_text", title),
            "full_caption": trace.get("full_caption", ""),
            "credit": trace.get("credit", "via original source"),
            "hashtags": trace.get("hashtags", ""),
            "trace": trace
        }

    def _call_gemini(self, title: str, description: str, channel: ChannelProfile) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        
        prompt = f"""
You are the head of content for {channel.handle} ({channel.niche}).
Analyze this video metadata and generate content in our signature viral format.

Video Title: "{title}"
Video Description/Context: "{description[:500]}"

Requirements:
1. "hook_text": A single, fascinating on-screen headline.
   - Tone: Observational, direct, scientific, slightly mysterious.
   - Style examples:
     * "This represents the Casimir effect between two plates caused by Quantum Fluctuations."
     * "David Tong explaining the vacuum and quantum fields."
     * "A biologist connected a synthesizer to the organic activity of a mushroom and it started playing fungi music."
   - Length: 10 to 18 words. No emojis, no clickbait buzzwords (no "Wait till the end", no "Mind blowing").
2. "caption_paragraphs": List of 2-3 engaging, well-explained paragraphs explaining the underlying mechanism clearly to curious people.
3. "credit": Who to credit (e.g. from title/description, or "Original Creator / Researcher").
4. "hashtags": Array of 10-12 focused niche hashtags.

Respond ONLY with valid JSON in this exact schema:
{{
  "hook_text": "...",
  "caption_paragraphs": ["...", "..."],
  "credit": "...",
  "hashtags": ["#...", "#..."]
}}
"""
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
        res.raise_for_status()
        data = res.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)

        # Assemble full caption
        body = "\n\n".join(parsed.get("caption_paragraphs", []))
        credit = parsed.get("credit", "via original source")
        hashtags = " ".join(parsed.get("hashtags", channel.default_hashtags))
        
        full_caption = (
            f"{body}\n\n"
            f"🔬 Credit: {credit}\n"
            f"✨ Follow {channel.handle} for more {channel.niche.lower()}.\n"
            f"🔗 {channel.cta_link}\n\n"
            f"{hashtags}"
        )

        return {
            "hook_text": parsed.get("hook_text", title),
            "full_caption": full_caption,
            "credit": credit,
            "hashtags": hashtags
        }

    def _heuristic_fallback(self, title: str, description: str, channel: ChannelProfile) -> Dict[str, Any]:
        """
        Reliable fallback rule engine when running offline or without an API key.
        """
        # Clean title
        clean_title = re.sub(r'\[.*?\]|\(.*?\)|#\w+', '', title).strip()
        if not clean_title.endswith(('.', '!', '?')):
            clean_title += '.'

        hook = clean_title
        if len(hook.split()) > 18:
            hook = " ".join(hook.split()[:16]) + "..."

        hashtags_str = " ".join(channel.default_hashtags)
        full_caption = (
            f"{clean_title}\n\n"
            f"Exploring the boundaries of {channel.niche.lower()}. "
            f"Every phenomenon demonstrates the underlying physics and engineering shaping our universe.\n\n"
            f"🔬 Credit: Original Creator\n"
            f"✨ Follow {channel.handle} for daily {channel.niche.lower()} breakdowns.\n"
            f"🔗 {channel.cta_link}\n\n"
            f"{hashtags_str}"
        )

        return {
            "hook_text": hook,
            "full_caption": full_caption,
            "credit": "Original Creator",
            "hashtags": hashtags_str
        }
