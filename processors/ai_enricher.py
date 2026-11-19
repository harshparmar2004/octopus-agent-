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

    def generate_dance_viral_package(
        self,
        title: str,
        description: str,
        channel_handle: str = "@cute.aarohi.007",
        creator_credit: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Specialized AI viral synthesizer for Dance, Parties & Entertainment reels:
        1. On-Screen Curiosity Hook (5-9 words): Direct, observational, curiosity-inducing about expressions, moves or style.
        2. High-Engagement Caption:
           - Debate / question hook
           - Share & DM trigger (send to wedding sangeet partner / bestie)
           - Follow CTA
           - SEO keyword tags
        """
        c_handle = channel_handle if channel_handle.startswith("@") else f"@{channel_handle}"
        credit_tag = f"Dancer / Credit: @{creator_credit.lstrip('@')}" if creator_credit else "Credit: Original Creator"

        # Try Gemini / LLM synthesis first
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                prompt = f"""
You are the viral growth strategist for {c_handle}, an Instagram dance and party lifestyle account.
Analyze this video context:
Title: "{title}"
Description: "{description[:400]}"

Generate an engaging, viral package tailored to Instagram Reels:
1. "hook_text": A short, punchy 5 to 9 word curiosity hook to overlay on the video. Examples:
   - "Wait for her expressions at the drop ✨"
   - "Can we talk about this lehenga twirl? 🤌"
   - "Her energy is literally unmatched 🔥"
   - "The cleanest choreo of the wedding season 💃"
2. "question_line": An engaging question or debate starter for the first line of the caption.
3. "share_prompt": A direct reason for viewers to share or DM the reel (e.g. "Send this to your sangeet dance partner who needs to see this! 👯‍♀️👇").
4. "seo_hashtags": Array of 8-10 high-traffic, relevant search tags.

Respond ONLY with valid JSON:
{{
  "hook_text": "...",
  "question_line": "...",
  "share_prompt": "...",
  "seo_hashtags": ["#dance", "#dancereels", "#partyvibes", "#weddingdance", "#sangeetdance", "#reelsinstagram"]
}}
"""
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    parsed = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
                    hook_text = parsed.get("hook_text", "Obsessed with this energy! ✨💃")
                    q_line = parsed.get("question_line", "Is this the cleanest dance of the season? ✨")
                    share_prompt = parsed.get("share_prompt", "Tag your dance partner who needs to try this choreo! 👯‍♀️👇")
                    tags = " ".join(parsed.get("seo_hashtags", ["#dance", "#dancereels", "#partyvibes", "#weddingdance", "#sangeetdance", "#reelsinstagram"]))

                    full_caption = (
                        f"{q_line}\n\n"
                        f"{share_prompt}\n\n"
                        f"{credit_tag}\n\n"
                        f"👉 Follow {c_handle} for daily trending dance & party vibes! ✨💃\n\n"
                        f"{tags}"
                    )
                    return {
                        "hook_text": hook_text,
                        "full_caption": full_caption,
                        "credit": credit_tag
                    }
            except Exception as e:
                logger.warning(f"Gemini viral dance synthesis failed, using heuristic: {e}")

        # Heuristic fallback for dance virality
        clean_desc = re.sub(r'#\w+', '', description or title or "").strip()
        first_line = clean_desc.split("\n")[0].strip() if clean_desc else ""
        if len(first_line) > 10:
            hook_text = f"Wait for this vibe ✨💃" if len(first_line.split()) > 8 else first_line
        else:
            hook_text = "Obsessed with this energy! ✨💃"

        q_line = first_line if (first_line and len(first_line) > 5) else "Rate this choreo from 1 to 10! 👇"
        full_caption = (
            f"{q_line}\n\n"
            f"Tag your dance partner who needs to see this! 👯‍♀️💃\n\n"
            f"{credit_tag}\n\n"
            f"👉 Follow {c_handle} for daily trending dance & party vibes! ✨💃\n\n"
            f"#dance #dancereels #partyvibes #choreo #weddingdance #sangeetdance #reelsinstagram"
        )
        return {
            "hook_text": hook_text,
            "full_caption": full_caption,
            "credit": credit_tag
        }

