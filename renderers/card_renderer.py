import os
import textwrap
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from config import ChannelProfile, settings
from renderers.niche_templates import NicheTemplate, get_template_for_niche, get_template_by_id

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

        self.font_serif_path = "C:/Windows/Fonts/georgiab.ttf"
        if not os.path.exists(self.font_serif_path):
            self.font_serif_path = "C:/Windows/Fonts/timesbd.ttf"

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
        highlight_word: Optional[str] = None,
        template: Optional[NicheTemplate] = None,
        template_id: Optional[str] = None
    ) -> Path:
        """
        Renders a 1080x1920 transparent PNG overlay according to the specified NicheTemplate.
        Supports layout strategies:
        - 'top_card_cult' (Informative / Tech)
        - 'center_kinetic' (Nightlife / Parties)
        - 'minimal_step_bar' (Home Organizing / CleanTok)
        - 'editorial_lower_third' (Fashion / Beauty / Lifestyle)
        """
        if template is None:
            if template_id:
                template = get_template_by_id(template_id)
            if template is None:
                niche_val = getattr(channel, "niche", "information") or "information"
                template = get_template_for_niche(niche_val)

        layout = getattr(template, "overlay_layout", "top_card_cult")
        
        if layout == "center_kinetic":
            return self._render_center_kinetic(hook_text, channel, output_path, credit_handle, highlight_word, template)
        elif layout == "minimal_step_bar":
            return self._render_minimal_step_bar(hook_text, channel, output_path, credit_handle, highlight_word, template)
        elif layout == "editorial_lower_third":
            return self._render_editorial_lower_third(hook_text, channel, output_path, credit_handle, highlight_word, template)
        else:
            return self._render_top_card_cult(hook_text, channel, output_path, credit_handle, highlight_word, template)

    def _render_avatar_badge(self, draw, canvas, channel, badge_x, badge_y, avatar_size, brand_color):
        logo_path = self._find_logo_path(channel)
        ring_bbox = [badge_x - 3, badge_y - 3, badge_x + avatar_size + 3, badge_y + avatar_size + 3]
        draw.ellipse(ring_bbox, outline=brand_color, width=3)

        if logo_path:
            try:
                logo_img = Image.open(logo_path).convert("RGBA")
                logo_resized = logo_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                canvas.paste(logo_resized, (badge_x, badge_y), mask)
                return
            except Exception:
                pass

        # Fallback initials
        avatar_bbox = [badge_x, badge_y, badge_x + avatar_size, badge_y + avatar_size]
        draw.ellipse(avatar_bbox, fill="#0d1b2a", outline=brand_color, width=2)
        try:
            avatar_font = ImageFont.truetype(self.font_bold_path, 34)
        except Exception:
            avatar_font = ImageFont.load_default()
        initials = channel.display_name[:2].upper()
        draw.text((badge_x + 22, badge_y + 20), initials, font=avatar_font, fill=brand_color)

    # 1. TOP CARD CULT (Informative / Tech)
    def _render_top_card_cult(self, hook_text, channel, output_path, credit_handle, highlight_word, template):
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        badge_y = 210
        badge_x = 90
        avatar_size = 88
        brand_color = getattr(channel, "brand_color", "#00b4d8") or "#00b4d8"
        highlight_color = getattr(template, "highlight_color", "#DDF51A") or "#DDF51A"

        self._render_avatar_badge(draw, canvas, channel, badge_x, badge_y, avatar_size, brand_color)

        text_x = badge_x + avatar_size + 24
        try:
            name_font = ImageFont.truetype(self.font_bold_path, 32)
            handle_font = ImageFont.truetype(self.font_regular_path, 24)
            credit_font = ImageFont.truetype(self.font_regular_path, 22)
            hook_font = ImageFont.truetype(self.font_regular_path, 42)
        except Exception:
            name_font = handle_font = credit_font = hook_font = ImageFont.load_default()

        draw.text((text_x, badge_y + 8), channel.display_name, font=name_font, fill="#FFFFFF")
        name_bbox = draw.textbbox((text_x, badge_y + 8), channel.display_name, font=name_font)
        badge_pos_x = name_bbox[2] + 12
        badge_pos_y = badge_y + 16
        draw.ellipse([badge_pos_x, badge_pos_y, badge_pos_x + 20, badge_pos_y + 20], fill="#00b4d8")
        draw.line([badge_pos_x + 5, badge_pos_y + 10, badge_pos_x + 9, badge_pos_y + 14], fill="#FFFFFF", width=2)
        draw.line([badge_pos_x + 9, badge_pos_y + 14, badge_pos_x + 15, badge_pos_y + 6], fill="#FFFFFF", width=2)
        draw.text((text_x, badge_y + 48), channel.handle, font=handle_font, fill="#94a3b8")

        wrapped_lines = textwrap.wrap(hook_text, width=40)
        start_y = 360
        line_height = 56
        for i, line in enumerate(wrapped_lines):
            if highlight_word and highlight_word.lower() in line.lower():
                words = line.split(" ")
                cur_x = badge_x
                for w in words:
                    clean_w = w.strip(".,!?:;\"'")
                    color = highlight_color if clean_w.lower() == highlight_word.lower() else "#FFFFFF"
                    try:
                        w_font = ImageFont.truetype(self.font_bold_path, 42) if clean_w.lower() == highlight_word.lower() else hook_font
                    except Exception:
                        w_font = hook_font
                    draw.text((cur_x, start_y + (i * line_height)), w + " ", font=w_font, fill=color)
                    w_bbox = draw.textbbox((cur_x, start_y + (i * line_height)), w + " ", font=w_font)
                    cur_x = w_bbox[2]
            else:
                draw.text((badge_x, start_y + (i * line_height)), line, font=hook_font, fill="#FFFFFF")

        if credit_handle:
            clean_credit = credit_handle.strip().lstrip("@")
            credit_text = f"Source: @{clean_credit}"
            credit_y = start_y + (len(wrapped_lines) * line_height) + 20
            c_bbox = draw.textbbox((badge_x + 14, credit_y + 6), credit_text, font=credit_font)
            pill_bbox = [badge_x, credit_y, c_bbox[2] + 16, c_bbox[3] + 8]
            draw.rounded_rectangle(pill_bbox, radius=12, fill=(15, 23, 42, 200), outline=(56, 189, 248, 120), width=1)
            draw.text((badge_x + 14, credit_y + 6), credit_text, font=credit_font, fill="#38bdf8")

        canvas.save(output_path, "PNG")
        return output_path

    # 2. CENTER KINETIC (Nightlife / Parties / EDM)
    def _render_center_kinetic(self, hook_text, channel, output_path, credit_handle, highlight_word, template):
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        badge_y = 160
        badge_x = 90
        avatar_size = 76
        brand_color = getattr(channel, "brand_color", "#FF007F") or "#FF007F"
        highlight_color = getattr(template, "highlight_color", "#FF007F") or "#FF007F"

        self._render_avatar_badge(draw, canvas, channel, badge_x, badge_y, avatar_size, brand_color)

        text_x = badge_x + avatar_size + 20
        try:
            name_font = ImageFont.truetype(self.font_bold_path, 28)
            handle_font = ImageFont.truetype(self.font_regular_path, 22)
            hook_font = ImageFont.truetype(self.font_bold_path, 52)
            credit_font = ImageFont.truetype(self.font_bold_path, 22)
        except Exception:
            name_font = handle_font = hook_font = credit_font = ImageFont.load_default()

        draw.text((text_x, badge_y + 6), channel.display_name, font=name_font, fill="#FFFFFF")
        draw.text((text_x, badge_y + 40), channel.handle, font=handle_font, fill="#f43f5e")

        # Center kinetic headline (Y ~ 650)
        wrapped_lines = textwrap.wrap(hook_text, width=32)
        start_y = 620
        line_height = 68
        for i, line in enumerate(wrapped_lines):
            if highlight_word and highlight_word.lower() in line.lower():
                words = line.split(" ")
                cur_x = badge_x
                for w in words:
                    clean_w = w.strip(".,!?:;\"'")
                    color = highlight_color if clean_w.lower() == highlight_word.lower() else "#FFFFFF"
                    draw.text((cur_x, start_y + (i * line_height)), w + " ", font=hook_font, fill=color)
                    w_bbox = draw.textbbox((cur_x, start_y + (i * line_height)), w + " ", font=hook_font)
                    cur_x = w_bbox[2]
            else:
                draw.text((badge_x, start_y + (i * line_height)), line, font=hook_font, fill="#FFFFFF")

        # Sound / Venue Tag Pill
        sound_text = f"🎵 {credit_handle or 'Original Sound • Nightlife EDM'}"
        tag_y = start_y + (len(wrapped_lines) * line_height) + 25
        s_bbox = draw.textbbox((badge_x + 16, tag_y + 8), sound_text, font=credit_font)
        pill_bbox = [badge_x, tag_y, s_bbox[2] + 20, s_bbox[3] + 10]
        draw.rounded_rectangle(pill_bbox, radius=14, fill=(30, 10, 40, 220), outline=(255, 0, 127, 180), width=2)
        draw.text((badge_x + 16, tag_y + 8), sound_text, font=credit_font, fill="#FF007F")

        canvas.save(output_path, "PNG")
        return output_path

    # 3. MINIMAL STEP BAR (Home Organizing & CleanTok)
    def _render_minimal_step_bar(self, hook_text, channel, output_path, credit_handle, highlight_word, template):
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        card_x = 70
        card_y = 190
        card_w = 940
        brand_color = getattr(channel, "brand_color", "#84A98C") or "#84A98C"
        highlight_color = getattr(template, "highlight_color", "#84A98C") or "#84A98C"

        try:
            name_font = ImageFont.truetype(self.font_bold_path, 28)
            handle_font = ImageFont.truetype(self.font_regular_path, 22)
            hook_font = ImageFont.truetype(self.font_bold_path, 38)
            credit_font = ImageFont.truetype(self.font_regular_path, 20)
        except Exception:
            name_font = handle_font = hook_font = credit_font = ImageFont.load_default()

        # Warm linen rounded backing card
        wrapped_lines = textwrap.wrap(hook_text, width=42)
        card_h = 160 + (len(wrapped_lines) * 52)
        card_bbox = [card_x, card_y, card_x + card_w, card_y + card_h]
        draw.rounded_rectangle(card_bbox, radius=24, fill=(245, 235, 224, 240), outline=(213, 189, 175, 200), width=2)

        # Avatar inside card
        inner_badge_x = card_x + 28
        inner_badge_y = card_y + 24
        avatar_size = 64
        self._render_avatar_badge(draw, canvas, channel, inner_badge_x, inner_badge_y, avatar_size, brand_color)

        text_x = inner_badge_x + avatar_size + 18
        draw.text((text_x, inner_badge_y + 4), channel.display_name, font=name_font, fill="#1C1917")
        draw.text((text_x, inner_badge_y + 36), channel.handle, font=handle_font, fill="#78716C")

        # Step Pill badge top-right of card
        step_text = "✨ STEP-BY-STEP RESET"
        draw.text((card_x + card_w - 240, inner_badge_y + 12), step_text, font=credit_font, fill="#84A98C")

        # Hook text inside linen card
        start_y = inner_badge_y + avatar_size + 24
        line_height = 50
        for i, line in enumerate(wrapped_lines):
            if highlight_word and highlight_word.lower() in line.lower():
                words = line.split(" ")
                cur_x = inner_badge_x
                for w in words:
                    clean_w = w.strip(".,!?:;\"'")
                    color = highlight_color if clean_w.lower() == highlight_word.lower() else "#1C1917"
                    draw.text((cur_x, start_y + (i * line_height)), w + " ", font=hook_font, fill=color)
                    w_bbox = draw.textbbox((cur_x, start_y + (i * line_height)), w + " ", font=hook_font)
                    cur_x = w_bbox[2]
            else:
                draw.text((inner_badge_x, start_y + (i * line_height)), line, font=hook_font, fill="#1C1917")

        canvas.save(output_path, "PNG")
        return output_path

    # 4. EDITORIAL LOWER THIRD (Fashion / Chic Lifestyle)
    def _render_editorial_lower_third(self, hook_text, channel, output_path, credit_handle, highlight_word, template):
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        brand_color = getattr(channel, "brand_color", "#D4AF37") or "#D4AF37"
        highlight_color = getattr(template, "highlight_color", "#D4AF37") or "#D4AF37"

        try:
            name_font = ImageFont.truetype(self.font_bold_path, 26)
            handle_font = ImageFont.truetype(self.font_regular_path, 20)
            hook_font = ImageFont.truetype(self.font_serif_path if os.path.exists(self.font_serif_path) else self.font_bold_path, 40)
            credit_font = ImageFont.truetype(self.font_regular_path, 20)
        except Exception:
            name_font = handle_font = hook_font = credit_font = ImageFont.load_default()

        # Editorial lower-third floating bar (Y ~ 1320 - 1620)
        card_x = 70
        card_y = 1320
        card_w = 940
        wrapped_lines = textwrap.wrap(hook_text, width=38)
        card_h = 160 + (len(wrapped_lines) * 54)
        
        # Sleek dark frosted glass
        card_bbox = [card_x, card_y, card_x + card_w, card_y + card_h]
        draw.rounded_rectangle(card_bbox, radius=20, fill=(18, 18, 18, 215), outline=(212, 175, 55, 140), width=1)

        # Header inside bar
        inner_badge_x = card_x + 28
        inner_badge_y = card_y + 22
        avatar_size = 56
        self._render_avatar_badge(draw, canvas, channel, inner_badge_x, inner_badge_y, avatar_size, brand_color)

        text_x = inner_badge_x + avatar_size + 16
        draw.text((text_x, inner_badge_y + 4), channel.display_name.upper(), font=name_font, fill="#FAF8F5")
        draw.text((text_x, inner_badge_y + 32), channel.handle, font=handle_font, fill="#D4AF37")

        # Hook text in elegant serif / high-contrast
        start_y = inner_badge_y + avatar_size + 20
        line_height = 54
        for i, line in enumerate(wrapped_lines):
            if highlight_word and highlight_word.lower() in line.lower():
                words = line.split(" ")
                cur_x = inner_badge_x
                for w in words:
                    clean_w = w.strip(".,!?:;\"'")
                    color = highlight_color if clean_w.lower() == highlight_word.lower() else "#FAF8F5"
                    draw.text((cur_x, start_y + (i * line_height)), w + " ", font=hook_font, fill=color)
                    w_bbox = draw.textbbox((cur_x, start_y + (i * line_height)), w + " ", font=hook_font)
                    cur_x = w_bbox[2]
            else:
                draw.text((inner_badge_x, start_y + (i * line_height)), line, font=hook_font, fill="#FAF8F5")

        canvas.save(output_path, "PNG")
        return output_path
