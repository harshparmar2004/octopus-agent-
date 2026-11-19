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
        - 100% human, aesthetic curator tone (NEVER sounds like a spam bot or scraper)
        - Observational on-screen curiosity hook (5-8 words)
        - Clean, genuine 2-3 line caption with conversational question or DM trigger
        - Subtle, respectful dancer credit (Dancing: @creator)
        - 3 to 4 targeted, aesthetic hashtags (no spam hashtag walls)
        - ZERO follow-begging phrases ("Follow for more", "👉 Follow @handle")
        """
        c_handle = channel_handle if channel_handle.startswith("@") else f"@{channel_handle}"

        # Clean credit handle
        credit_str = None
        if creator_credit and creator_credit.strip() and creator_credit not in ("curated_source", "none", "unknown"):
            clean_cr = creator_credit.strip().lstrip("@")
            credit_str = f"Dancing: @{clean_cr}"

        # 1. Try Gemini AI if a valid key is set (ignore test dummy keys)
        api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
        if api_key and not api_key.startswith("AIzaSyTest"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
                prompt = f"""
You are an authentic, aesthetic dance enthusiast and curator writing natural Instagram Reels captions.
Video Title: "{title}"
Video Description: "{description[:400]}"
Creator: "{creator_credit or ''}"

Write a genuinely authentic, non-spammy caption:
Rules:
- Sound 100% human, casual, and aesthetic.
- NEVER use spam phrases like '👉 Follow @handle', 'Follow for more', 'Daily vibes', or 'Tag someone'.
- Keep caption short (2 to 3 lines maximum).
- Include an observation about the specific dance/outfit/energy, followed by a natural question for viewers.
- Strictly 3 to 4 clean, focused hashtags.

Respond ONLY with valid JSON:
{{
  "hook_text": "5-8 words on-screen hook (e.g. That lehenga twirl at the end 🤌✨)",
  "observation": "1-2 lines natural observation and question",
  "hashtags": ["#tag1", "#tag2", "#tag3"]
}}
"""
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json"}
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    parsed = json.loads(data["candidates"][0]["content"]["parts"][0]["text"])
                    hook = parsed.get("hook_text", "Obsessed with this energy! ✨💃")
                    obs = parsed.get("observation", "").strip()
                    tags = " ".join(parsed.get("hashtags", ["#danceinspo", "#weddingseason", "#choreo"]))

                    caption_parts = [obs] if obs else []
                    if credit_str:
                        caption_parts.append(credit_str)
                    caption_parts.append(tags)

                    return {
                        "hook_text": hook,
                        "full_caption": "\n\n".join(caption_parts),
                        "credit": credit_str or "Original Creator"
                    }
            except Exception as e:
                logger.warning(f"Gemini caption generation error: {e}")

        # 2. Dynamic, Context-Aware Humanized Synthesizer (Zero-Spam Fallback)
        raw_text = f"{title} {description}".lower()
        clean_desc = re.sub(r'#\w+', '', description or "").strip()
        first_line = clean_desc.split("\n")[0].strip() if clean_desc else ""

        # Context detection
        is_lehenga_outfit = any(w in raw_text for w in ["lehenga", "twirl", "saree", "outfit", "dress", "fit", "transition"])
        is_sangeet_wedding = any(w in raw_text for w in ["sangeet", "wedding", "shaadi", "bride", "bridesmaid", "festive"])
        is_footwork_choreo = any(w in raw_text for w in ["choreo", "choreography", "steps", "footwork", "routine", "tutorial"])
        is_energy_party = any(w in raw_text for w in ["energy", "party", "drop", "beat", "vibe", "fire", "hype"])

        if is_lehenga_outfit:
            hooks = [
                "The flow in this lehenga twirl 🤌✨",
                "Can we talk about this outfit transition? 😍",
                "That grace and twirl is pure perfection ✨",
                "Outfit details on another level 💫"
            ]
            observations = [
                "The grace and flow in this outfit are simply unreal 🤌✨\n\nWhich color combination was your favorite? 👇",
                "That twirl at the drop was absolute perfection ✨\n\nNeed this outfit saved for the next wedding season! 💃",
                "The outfit transition is so smooth you have to watch twice 💫\n\nRate this look from 1 to 10? 👇"
            ]
            tags = "#lehengatwirl #weddingseason #ethnicwear #danceinspo"
        elif is_sangeet_wedding:
            hooks = [
                "The cleanest sangeet choreo yet 💃",
                "Learning this for wedding season ✨",
                "Her energy on this track is unmatched 🔥",
                "Sangeet dance goals right here 👯‍♀️"
            ]
            observations = [
                "Setting the bar for sangeet season with this routine ✨💃\n\nWho’s learning this hook step next? 👇",
                "The joy and energy in this dance are so infectious 🤌\n\nSave this for your upcoming wedding choreography! 💫",
                "The cleanest sangeet choreography of the season 🔥\n\nRate this routine from 1 to 10? 👇"
            ]
            tags = "#sangeetdance #weddingchoreography #bollywooddance #danceinspo"
        elif is_footwork_choreo:
            hooks = [
                "Obsessed with this footwork 🔥",
                "The transitions are so clean 🤌✨",
                "Wait for the footwork at the drop ⚡",
                "The rhythm on this track is unmatched 💃"
            ]
            observations = [
                "The footwork and transitions here are so satisfying to watch 🤌🔥\n\nCan we talk about how clean this timing is? 👇",
                "Obsessed with the rhythm and musicality on this choreography ✨\n\nWhich section was your favorite? 💃",
                "The timing and sync on this beat are pure art 💫\n\nRate this choreo from 1 to 10? 👇"
            ]
            tags = "#choreo #dancereels #footwork #danceinspiration"
        elif is_energy_party:
            hooks = [
                "Her energy is literally unmatched 🔥",
                "Wait for the beat drop ⚡✨",
                "That smile at the drop makes this 10x better 😍",
                "Unmatched energy from start to finish 💫"
            ]
            observations = [
                "The energy and pure vibe in this routine are unmatched 🔥✨\n\nCan’t stop watching this loop! Rate it 1–10? 👇",
                "That expression at the drop makes the whole dance 10x better 🤌\n\nWhat song should be next? 👇",
                "Unmatched confidence and rhythm from the very first second ⚡💃\n\nWhich move was your favorite? 👇"
            ]
            tags = "#dancereels #viralchoreo #festivevibes #dance"
        else:
            hooks = [
                "Wait for the drop ✨💃",
                "Her expressions are everything 😍",
                "Can we talk about this choreo? 🤌",
                "The energy here is infectious 🔥"
            ]
            if first_line and len(first_line) > 6 and not first_line.startswith("@"):
                observations = [
                    f"{first_line} ✨\n\nRate this routine from 1 to 10? 👇",
                    f"Obsessed with this performance 🤌\n\nCan we talk about how clean this routine is? 👇",
                    f"The rhythm and grace here are so good ✨\n\nWhich part was your favorite? 👇"
                ]
            else:
                observations = [
                    "The grace and rhythm here are simply unreal 🤌✨\n\nRate this dance from 1 to 10? 👇",
                    "Obsessed with the expressions and energy on this track 🔥\n\nCan’t stop rewatching this routine! 💃",
                    "The timing and footwork here are so clean 💫\n\nWhich part was your favorite? 👇"
                ]
            tags = "#danceinspo #dancereels #choreo #festive"

        # Deterministic but diverse selection based on title/desc hash
        seed = sum(ord(c) for c in (title + description)) if (title or description) else 42
        selected_hook = hooks[seed % len(hooks)]
        selected_obs = observations[seed % len(observations)]

        caption_blocks = [selected_obs]
        if credit_str:
            caption_blocks.append(credit_str)
        caption_blocks.append(tags)

        return {
            "hook_text": selected_hook,
            "full_caption": "\n\n".join(caption_blocks),
            "credit": credit_str or "Original Creator"
        }


