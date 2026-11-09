import os
import json
import logging
from typing import Optional, Dict
import requests

from config import settings

logger = logging.getLogger("TelegramReviewer")

class TelegramReviewer:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_for_review(self, video_path: str, caption: str, hook_text: str, candidate_id: str) -> bool:
        """
        Sends the rendered Reel video directly to your Telegram chat with interactive buttons.
        """
        if not self.is_configured():
            logger.info("Telegram bot not configured. Skipping interactive push.")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendVideo"
        
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve & Post", "callback_data": f"approve_{candidate_id}"},
                    {"text": "❌ Discard", "callback_data": f"reject_{candidate_id}"}
                ]
            ]
        }

        short_summary = (
            f"🎬 *New Reel Ready for Review*\n\n"
            f"📌 *Hook:* {hook_text}\n\n"
            f"📝 *Caption:*\n{caption[:350]}...\n"
        )

        try:
            with open(video_path, "rb") as video_file:
                payload = {
                    "chat_id": self.chat_id,
                    "caption": short_summary,
                    "parse_mode": "Markdown",
                    "reply_markup": json.dumps(reply_markup)
                }
                files = {"video": video_file}
                res = requests.post(url, data=payload, files=files, timeout=60)
                
            if res.status_code == 200:
                logger.info("Reel successfully pushed to Telegram for review.")
                return True
            else:
                logger.error(f"Telegram API error: {res.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send video to Telegram: {e}")
            return False
