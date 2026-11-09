import os
import textwrap
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from config import ChannelProfile, settings

class CardRenderer:
    def __init__(self, assets_dir: Path = settings.ASSETS_DIR):
        self.assets_dir = assets_dir
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        
        # Load system fonts
        self.font_bold_path = "C:/Windows/Fonts/segoeuib.ttf"
        if not os.path.exists(self.font_bold_path):
            self.font_bold_path = "C:/Windows/Fonts/arialbd.ttf"
            
        self.font_regular_path = "C:/Windows/Fonts/segoeui.ttf"
        if not os.path.exists(self.font_regular_path):
            self.font_regular_path = "C:/Windows/Fonts/arial.ttf"

    def _find_logo_path(self, channel: ChannelProfile) -> Optional[Path]:
        """Looks for specific or master logo in assets directory."""
        candidates = []
        if getattr(channel, "logo_filename", None):
            candidates.append(self.assets_dir / channel.logo_filename)
        
        # Check by handle or display name
        h_clean = channel.handle.lstrip("@").replace("octopus.", "").replace(".", "_")
        candidates.append(self.assets_dir / f"logo_{h_clean}.png")
        candidates.append(self.assets_dir / f"logo_{channel.display_name.lower()}.png")
        candidates.append(self.assets_dir / "logo.png")
        
        for cand in candidates:
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
    ) -> Path:
        """
        Renders a 1080x1920 transparent PNG overlay with:
        1. Channel Template Logo Badge (Circular logo PNG + Verified check + Handle)
        2. Hook/Headline text with elegant word-wrapping and typography
        3. Optional Original Source Credit Pill
        """
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # 1. Avatar Icon & Channel Info (Y ~ 220)
        badge_y = 210
        badge_x = 90
        avatar_size = 88
        brand_color = getattr(channel, "brand_color", "#00b4d8") or "#00b4d8"

        logo_path = self._find_logo_path(channel)
        
        # Draw outer decorative ring with brand color
        ring_bbox = [badge_x - 3, badge_y - 3, badge_x + avatar_size + 3, badge_y + avatar_size + 3]
        draw.ellipse(ring_bbox, outline=brand_color, width=3)

        if logo_path:
            try:
                logo_img = Image.open(logo_path).convert("RGBA")
                logo_resized = logo_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                
                # Circular mask
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                
                canvas.paste(logo_resized, (badge_x, badge_y), mask)
            except Exception:
                logo_path = None # Fallback to text initials

        if not logo_path:
            # Fallback stylized avatar
            avatar_bbox = [badge_x, badge_y, badge_x + avatar_size, badge_y + avatar_size]
            draw.ellipse(avatar_bbox, fill="#0d1b2a", outline=brand_color, width=2)
            try:
                avatar_font = ImageFont.truetype(self.font_bold_path, 34)
            except Exception:
                avatar_font = ImageFont.load_default()
            initials = channel.display_name[:2].upper()
            draw.text((badge_x + 22, badge_y + 20), initials, font=avatar_font, fill=brand_color)

        # Channel text next to avatar
        text_x = badge_x + avatar_size + 24
        try:
            name_font = ImageFont.truetype(self.font_bold_path, 32)
            handle_font = ImageFont.truetype(self.font_regular_path, 24)
            credit_font = ImageFont.truetype(self.font_regular_path, 22)
        except Exception:
            name_font = handle_font = credit_font = ImageFont.load_default()

        # Draw Channel Name + Verified Badge
        draw.text((text_x, badge_y + 8), channel.display_name, font=name_font, fill="#FFFFFF")
        
        # Calculate width of channel name to position verified badge
        name_bbox = draw.textbbox((text_x, badge_y + 8), channel.display_name, font=name_font)
        badge_pos_x = name_bbox[2] + 12
        badge_pos_y = badge_y + 16
        
        # Draw verified circle badge
        draw.ellipse([badge_pos_x, badge_pos_y, badge_pos_x + 20, badge_pos_y + 20], fill="#00b4d8")
        # Checkmark
        draw.line([badge_pos_x + 5, badge_pos_y + 10, badge_pos_x + 9, badge_pos_y + 14], fill="#FFFFFF", width=2)
        draw.line([badge_pos_x + 9, badge_pos_y + 14, badge_pos_x + 15, badge_pos_y + 6], fill="#FFFFFF", width=2)

        # Handle
        draw.text((text_x, badge_y + 48), channel.handle, font=handle_font, fill="#94a3b8")

        # 2. Hook / Headline Text (Y ~ 360 - 640)
        try:
            hook_font = ImageFont.truetype(self.font_regular_path, 42)
        except Exception:
            hook_font = ImageFont.load_default()

        wrapped_lines = textwrap.wrap(hook_text, width=40)
        start_y = 360
        line_height = 56
        for i, line in enumerate(wrapped_lines):
            if highlight_word and highlight_word.lower() in line.lower():
                words = line.split(" ")
                cur_x = badge_x
                for w in words:
                    clean_w = w.strip(".,!?:;\"'")
                    color = "#DDF51A" if clean_w.lower() == highlight_word.lower() else "#FFFFFF"
                    try:
                        w_font = ImageFont.truetype(self.font_bold_path, 42) if clean_w.lower() == highlight_word.lower() else hook_font
                    except Exception:
                        w_font = hook_font
                    draw.text((cur_x, start_y + (i * line_height)), w + " ", font=w_font, fill=color)
                    w_bbox = draw.textbbox((cur_x, start_y + (i * line_height)), w + " ", font=w_font)
                    cur_x = w_bbox[2]
            else:
                draw.text((badge_x, start_y + (i * line_height)), line, font=hook_font, fill="#FFFFFF")

        # 3. Optional Original Source Credit Tag
        if credit_handle:
            clean_credit = credit_handle.strip().lstrip("@")
            credit_text = f"Source: @{clean_credit}"
            credit_y = start_y + (len(wrapped_lines) * line_height) + 20
            
            # Subtle rounded credit pill background
            c_bbox = draw.textbbox((badge_x + 14, credit_y + 6), credit_text, font=credit_font)
            pill_bbox = [badge_x, credit_y, c_bbox[2] + 16, c_bbox[3] + 8]
            draw.rounded_rectangle(pill_bbox, radius=12, fill=(15, 23, 42, 200), outline=(56, 189, 248, 120), width=1)
            draw.text((badge_x + 14, credit_y + 6), credit_text, font=credit_font, fill="#38bdf8")

        canvas.save(output_path, "PNG")
        return output_path

