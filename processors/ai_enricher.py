import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
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
    def generate_dance_viral_package(
        self,
        title: str,
        description: str,
        channel_handle: str = "@cute.aarohi.007",
        creator_credit: Optional[str] = None,
        account_index: int = 0
    ) -> Dict[str, Any]:
        """
        Synthesizes a humanized, zero-spam viral package for dance/entertainment reels.
        Supports account_index (0 to 9) to generate a distinct angle for multi-account networks.
        """
        packages = self.generate_multi_account_dance_package(
            count=1,
            title=title,
            description=description,
            channel_handles=[channel_handle],
            creator_credit=creator_credit,
            start_index=account_index
        )
        return packages[0] if packages else {
            "hook_text": "Wait for this vibe ✨💃",
            "full_caption": "Obsessed with this performance 🤌\n\nRate this routine from 1 to 10? 👇\n\n#danceinspo #dancereels",
            "credit": "Original Creator"
        }

    def generate_multi_account_dance_package(
        self,
        count: int = 10,
        title: str = "",
        description: str = "",
        channel_handles: Optional[List[str]] = None,
        creator_credit: Optional[str] = None,
        start_index: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes up to 10 completely distinct, non-overlapping viral packages for multi-account syndication.
        Guarantees that NO TWO ACCOUNTS share identical hook text, observations, questions, or hashtag clusters.
        Zero spam phrases allowed.
        """
        credit_str = None
        if creator_credit and creator_credit.strip() and creator_credit not in ("curated_source", "none", "unknown"):
            clean_cr = creator_credit.strip().lstrip("@")
            credit_str = f"Dancing: @{clean_cr}"

        archetypes = [
            {
                "angle": "outfit",
                "hooks": [
                    "The flow in this lehenga twirl 🤌✨",
                    "Can we talk about this outfit? 😍",
                    "That twirl and grace is perfection ✨"
                ],
                "obs": "The grace and flow in this outfit are simply unreal 🤌✨\n\nWhich color combination was your favorite? 👇",
                "tags": "#lehengatwirl #ethnicwear #weddingfashion #danceinspo"
            },
            {
                "angle": "choreo",
                "hooks": [
                    "The cleanest footwork routine yet 💃",
                    "Obsessed with this footwork 🔥",
                    "The transitions are so clean 🤌✨"
                ],
                "obs": "The footwork and transitions here are so satisfying to watch 🤌🔥\n\nCan we talk about how clean this timing is? 👇",
                "tags": "#choreo #dancereels #footwork #bollywooddance"
            },
            {
                "angle": "expression",
                "hooks": [
                    "Her expressions are everything 😍✨",
                    "Wait for her expressions at the drop ✨",
                    "That smile makes this 10x better 😍"
                ],
                "obs": "The expressions and smile at the drop make this 10x better 🤌✨\n\nRate these expressions from 1 to 10? 👇",
                "tags": "#danceexpressions #dancevideo #graceful #reelsindia"
            },
            {
                "angle": "energy",
                "hooks": [
                    "Her energy on this beat is unmatched 🔥",
                    "Unmatched energy from start to finish 💫",
                    "Wait for the beat drop ⚡✨"
                ],
                "obs": "The energy and pure vibe in this routine are unmatched 🔥✨\n\nCan’t stop watching this loop! Rate it 1–10? 👇",
                "tags": "#energydance #dancereels #partyvibes #viralchoreo"
            },
            {
                "angle": "sangeet",
                "hooks": [
                    "Setting sangeet goals with this routine ✨",
                    "The cleanest sangeet choreo yet 💃",
                    "Sangeet dance goals right here 👯‍♀️"
                ],
                "obs": "Setting the bar for sangeet season with this routine ✨💃\n\nWho’s learning this hook step next? 👇",
                "tags": "#sangeetdance #weddingchoreography #shaadiseason #sangeetinspo"
            },
            {
                "angle": "transition",
                "hooks": [
                    "Can we talk about this transition? 🤌💫",
                    "The smoothest transition on the beat 💫",
                    "Wait for the timing at the drop ⚡"
                ],
                "obs": "The transition on the beat drop is so smooth you have to watch twice 💫\n\nDid you catch that timing? 👇",
                "tags": "#transitionreels #visualflow #dancereel #trendingaudio"
            },
            {
                "angle": "music_vibe",
                "hooks": [
                    "Obsessed with the rhythm on this track 🎶",
                    "The rhythm on this track is unmatched 💃",
                    "Can't get this beat out of my head 🤌"
                ],
                "obs": "The rhythm and musicality on this choreography are pure art 💫\n\nWhat song should be covered next? 👇",
                "tags": "#trendingbeats #bollywoodmusic #rhythmdance #dancevibes"
            },
            {
                "angle": "learning_steps",
                "hooks": [
                    "Learning this hook step for wedding season 👯‍♀️",
                    "Learning this for wedding season ✨",
                    "Save this for your next dance practice 💫"
                ],
                "obs": "Obsessed with this choreography! Bookmark this for your upcoming wedding practice! 💫\n\nWho are you dancing this with? 👇",
                "tags": "#dancepractice #hookstep #sangeetprep #dancetutorial"
            },
            {
                "angle": "festive",
                "hooks": [
                    "Pure festive celebration vibes ✨🎉",
                    "That grace and twirl is pure perfection ✨",
                    "Festive season energy done right 💃"
                ],
                "obs": "The joy and festive energy in this dance are so infectious 🤌✨\n\nWhich part was your favorite? 👇",
                "tags": "#festivedance #celebrationvibes #ethnicdance #indiandance"
            },
            {
                "angle": "viral_loop",
                "hooks": [
                    "Wait for the drop at the end ⚡💃",
                    "Can't stop rewatching this choreo 💃",
                    "Rate this routine from 1 to 10? 🤌"
                ],
                "obs": "Unmatched confidence and rhythm from the very first second ⚡💃\n\nRate this dance from 1 to 10? 👇",
                "tags": "#viralreels #danceloop #choreography #trendingreels"
            }
        ]

        # Context relevance priority
        raw_text = f"{title} {description}".lower()
        if any(w in raw_text for w in ["sangeet", "wedding", "shaadi"]):
            # Rotate sangeet to front
            archetypes = archetypes[4:5] + archetypes[:4] + archetypes[5:]
        elif any(w in raw_text for w in ["lehenga", "saree", "outfit", "twirl"]):
            pass  # outfit is already first
        elif any(w in raw_text for w in ["choreo", "footwork", "steps"]):
            archetypes = archetypes[1:2] + archetypes[:1] + archetypes[2:]

        results: List[Dict[str, Any]] = []
        seed = sum(ord(c) for c in (title + description)) if (title or description) else 1337

        for i in range(count):
            idx = (start_index + i) % len(archetypes)
            arch = archetypes[idx]
            hook = arch["hooks"][(seed + i) % len(arch["hooks"])]
            obs = arch["obs"]
            tags = arch["tags"]

            caption_blocks = [obs]
            if credit_str:
                caption_blocks.append(credit_str)
            caption_blocks.append(tags)

            results.append({
                "account_index": start_index + i,
                "angle": arch["angle"],
                "hook_text": hook,
                "full_caption": "\n\n".join(caption_blocks),
                "credit": credit_str or "Original Creator"
            })

        return results



