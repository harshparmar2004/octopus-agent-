import os
import re
import string
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from PIL import Image, ImageDraw, ImageFont
from config import ChannelProfile, settings

class CardRenderer:
    """
    Renders the viral high-retention 'Cult / Octopus' visual overlay:
    - Pitch black canvas header
    - Universal circular master network logo with neon yellow ring (#DDF51A)
    - Dynamic per-page title + official Instagram blue verified badge (#0095F6) + muted handle
    - Dual-tone bold headline typography (white text + neon yellow punchline highlight)
    """
    def __init__(self, assets_dir: Path = settings.ASSETS_DIR):
        self.assets_dir = assets_dir
        self.assets_dir.mkdir(parents=True, exist_ok=True)

        # High-impact fonts
        self.font_bold_path = "C:/Windows/Fonts/segoeuib.ttf"
        if not os.path.exists(self.font_bold_path):
            self.font_bold_path = "C:/Windows/Fonts/arialbd.ttf"

        self.font_regular_path = "C:/Windows/Fonts/segoeui.ttf"
        if not os.path.exists(self.font_regular_path):
            self.font_regular_path = "C:/Windows/Fonts/arial.ttf"

        self.master_badge_path = self.assets_dir / "master_network_badge.png"

    def _get_master_logo(self) -> Optional[Path]:
        """Returns the single universal master network logo."""
        if self.master_badge_path.exists():
            return self.master_badge_path
        # Check standard logo candidates
        for name in ["octopus_logo.png", "logo.png"]:
            cand = self.assets_dir / name
            if cand.exists():
                return cand
        return None

    def render_header_overlay(
        self,
        hook_text: str,
        channel: ChannelProfile,
        output_path: Path,
        credit_handle: Optional[str] = None,
        highlight_word: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Renders the pixel-perfect 1080x1920 overlay.
        Returns metadata containing the exact bottom coordinate of the text zone.
        """
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        badge_x = 75
        badge_y = 175
        avatar_size = 96
        neon_yellow = (221, 245, 26, 255)      # #DDF51A (Cult Neon Yellow)
        pure_white = (255, 255, 255, 255)      # #FFFFFF
        muted_grey = (142, 142, 142, 255)      # #8E8E8E
        verified_blue = (0, 149, 246, 255)     # #0095F6 (Instagram Blue)

        # 1. UNIVERSAL MASTER LOGO WITH NEON RING
        master_logo = self._get_master_logo()
        ring_thickness = 4
        ring_bbox = [badge_x - ring_thickness, badge_y - ring_thickness, 
                     badge_x + avatar_size + ring_thickness, badge_y + avatar_size + ring_thickness]
        draw.ellipse(ring_bbox, outline=neon_yellow, width=ring_thickness)

        if master_logo and master_logo.exists():
            try:
                logo_img = Image.open(master_logo).convert("RGBA")
                logo_resized = logo_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                canvas.paste(logo_resized, (badge_x, badge_y), mask)
            except Exception:
                master_logo = None

        if not master_logo:
            # Fallback stylized dark disc with neon brand letter
            draw.ellipse([badge_x, badge_y, badge_x + avatar_size, badge_y + avatar_size], fill=(12, 12, 14, 255))
            try:
                av_font = ImageFont.truetype(self.font_bold_path, 38)
            except Exception:
                av_font = ImageFont.load_default()
            initial = channel.display_name[:1].upper() if channel.display_name else "O"
            draw.text((badge_x + 32, badge_y + 22), initial, font=av_font, fill=neon_yellow)

        # 2. PER-PAGE DISPLAY NAME + VERIFIED BLUE BADGE
        text_x = badge_x + avatar_size + 24
        try:
            name_font = ImageFont.truetype(self.font_bold_path, 34)
            handle_font = ImageFont.truetype(self.font_regular_path, 23)
            headline_font = ImageFont.truetype(self.font_bold_path, 46)
        except Exception:
            name_font = handle_font = headline_font = ImageFont.load_default()

        # Draw page name
        draw.text((text_x, badge_y + 8), channel.display_name, font=name_font, fill=pure_white)

        # Draw verified blue badge
        name_bbox = draw.textbbox((text_x, badge_y + 8), channel.display_name, font=name_font)
        v_size = 22
        v_x = name_bbox[2] + 12
        v_y = badge_y + 17
        draw.ellipse([v_x, v_y, v_x + v_size, v_y + v_size], fill=verified_blue)
        # Checkmark
        draw.line([v_x + 6, v_y + 11, v_x + 10, v_y + 15], fill=pure_white, width=2)
        draw.line([v_x + 10, v_y + 15, v_x + 16, v_y + 7], fill=pure_white, width=2)

        # Handle text in muted grey
        handle_text = channel.handle if channel.handle.startswith("@") else f"@{channel.handle}"
        draw.text((text_x, badge_y + 50), handle_text, font=handle_font, fill=muted_grey)

        # 3. DUAL-TONE HEADLINE TYPOGRAPHY
        start_y = 315
        max_text_width = 930  # 1080 - 75*2 = 930
        line_height = 62

        # Extract explicit highlight word from text if marked with *word*
        clean_text = hook_text
        if not highlight_word:
            match = re.search(r'\*([a-zA-Z0-9_\-]+)\*', hook_text)
            if match:
                highlight_word = match.group(1)
                clean_text = hook_text.replace(f"*{highlight_word}*", highlight_word)
            else:
                # Auto-detect emotionally charged keyword if present
                keywords = ["completely", "insane", "never", "secret", "billionaire", "dumb", "taxes", "wealth", "truth", "money", "hidden", "mistake"]
                for kw in keywords:
                    if re.search(rf'\b{kw}\b', hook_text, re.IGNORECASE):
                        highlight_word = kw
                        break

        # Tokenize and word-wrap with kerning calculation
        words = clean_text.split()
        lines: List[List[Dict[str, Any]]] = []
        current_line: List[Dict[str, Any]] = []
        current_line_width = 0

        space_bbox = draw.textbbox((0, 0), " ", font=headline_font)
        space_width = space_bbox[2] - space_bbox[0]

        for w in words:
            # Strip punctuation for highlight comparison
            stripped_w = w.strip(string.punctuation).lower()
            is_hl = bool(highlight_word and stripped_w == highlight_word.lower())

            w_bbox = draw.textbbox((0, 0), w, font=headline_font)
            w_width = w_bbox[2] - w_bbox[0]

            if current_line and (current_line_width + space_width + w_width) > max_text_width:
                lines.append(current_line)
                current_line = [{"word": w, "is_highlight": is_hl, "width": w_width}]
                current_line_width = w_width
            else:
                if current_line:
                    current_line_width += space_width
                current_line.append({"word": w, "is_highlight": is_hl, "width": w_width})
                current_line_width += w_width

        if current_line:
            lines.append(current_line)

        # Render each line with dual-tone word coloring
        curr_y = start_y
        for line in lines:
            curr_x = badge_x
            for item in line:
                color = neon_yellow if item["is_highlight"] else pure_white
                draw.text((curr_x, curr_y), item["word"], font=headline_font, fill=color)
                curr_x += item["width"] + space_width
            curr_y += line_height

        text_bottom_y = curr_y + 15

        canvas.save(output_path, "PNG")
        return {
            "overlay_path": str(output_path),
            "text_bottom_y": text_bottom_y,
            "highlight_word": highlight_word,
            "num_lines": len(lines)
        }
