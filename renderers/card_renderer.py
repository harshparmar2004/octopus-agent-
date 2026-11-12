import os
import textwrap
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
        
        if layout == "full_screen_neon_hud":
            return self._render_full_screen_neon_hud(hook_text, channel, output_path, credit_handle, highlight_word, template)
        elif layout == "center_kinetic":
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

    def _hex_to_rgb(self, hex_str: str):
        hex_clean = hex_str.lstrip("#")
        if len(hex_clean) == 6:
            return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))
        return (255, 0, 127)

    def _draw_glow_text(self, draw, pos, text, font, fill_core, glow_color, radius=3, anchor="mm"):
        gx, gy = pos
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx != 0 or dy != 0:
                    draw.text((gx + dx, gy + dy), text, font=font, fill=glow_color, anchor=anchor)
        draw.text(pos, text, font=font, fill=fill_core, anchor=anchor)

    # 5. FULL-SCREEN CYBER NEON HUD (Girls Party, VIP Nightlife & EDM)
    def _render_full_screen_neon_hud(self, hook_text, channel, output_path, credit_handle, highlight_word, template):
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        width, height = 1080, 1920

        # Check for pre-built custom template PNG (e.g. designed with nano banana / Photoshop)
        custom_candidates = [
            self.assets_dir / f"overlay_{channel.handle.lstrip('@').replace('.', '_')}.png",
            self.assets_dir / f"overlay_{channel.handle.lstrip('@')}.png",
            self.assets_dir / "girls_party_overlay.png",
            self.assets_dir / "templates" / "girls_party_neon.png"
        ]
        for cand in custom_candidates:
            if cand.exists():
                try:
                    custom_img = Image.open(cand).convert("RGBA")
                    if custom_img.size != (width, height):
                        custom_img = custom_img.resize((width, height), Image.Resampling.LANCZOS)
                    canvas.paste(custom_img, (0, 0), custom_img)
                    canvas.save(output_path, "PNG")
                    return output_path
                except Exception as e:
                    pass

        margin_x = 45
        margin_top = 80
        margin_bot = 1830

        glow_hex = getattr(template, "highlight_color", "#FF007F") or "#FF007F"
        glow_rgb = self._hex_to_rgb(glow_hex)
        glow_rgba = glow_rgb + (220,)
        neon_core = (255, 255, 255, 255)

        # 1. Outer chamfered cyber frame
        notch = 40
        frame_pts = [
            (margin_x + notch, margin_top),
            (width - margin_x - notch, margin_top),
            (width - margin_x, margin_top + notch),
            (width - margin_x, margin_bot - notch),
            (width - margin_x - notch, margin_bot),
            (margin_x + notch, margin_bot),
            (margin_x, margin_bot - notch),
            (margin_x, margin_top + notch),
            (margin_x + notch, margin_top)
        ]
        draw.line(frame_pts, fill=glow_rgba, width=3)

        # 2. Corner heavy bracket accents
        bracket_len = 60
        # TL
        draw.line([(margin_x - 12, margin_top - 12 + bracket_len), (margin_x - 12, margin_top - 12), (margin_x - 12 + bracket_len, margin_top - 12)], fill=glow_rgba, width=6)
        # TR
        draw.line([(width - margin_x + 12 - bracket_len, margin_top - 12), (width - margin_x + 12, margin_top - 12), (width - margin_x + 12, margin_top - 12 + bracket_len)], fill=glow_rgba, width=6)
        # BL
        draw.line([(margin_x - 12, margin_bot + 12 - bracket_len), (margin_x - 12, margin_bot + 12), (margin_x - 12 + bracket_len, margin_bot + 12)], fill=glow_rgba, width=6)
        # BR
        draw.line([(width - margin_x + 12 - bracket_len, margin_bot + 12), (width - margin_x + 12, margin_bot + 12), (width - margin_x + 12, margin_bot + 12 - bracket_len)], fill=glow_rgba, width=6)

        # Fonts
        try:
            font_badge = ImageFont.truetype(self.font_bold_path, 32)
            font_sub = ImageFont.truetype(self.font_regular_path, 20)
            font_handle = ImageFont.truetype(self.font_bold_path, 26)
            font_hook = ImageFont.truetype(self.font_bold_path, 36)
        except Exception:
            font_badge = font_sub = font_handle = font_hook = ImageFont.load_default()

        # 3. Top Glowing Branded Pill: [ C U T E   A A R O H I ]
        raw_name = (channel.display_name or "OCTOPUS").strip()
        spaced_words = [" ".join(list(w.upper())) for w in raw_name.split()]
        badge_text = "   ".join(spaced_words)

        tb = draw.textbbox((0, 0), badge_text, font=font_badge)
        text_w = tb[2] - tb[0]
        pill_w = max(580, text_w + 100)
        pill_h = 76
        pill_x1 = (width - pill_w) // 2
        pill_y1 = 110
        pill_x2 = pill_x1 + pill_w
        pill_y2 = pill_y1 + pill_h

        b_notch = 16
        badge_pts = [
            (pill_x1 + b_notch, pill_y1),
            (pill_x2 - b_notch, pill_y1),
            (pill_x2, pill_y1 + b_notch),
            (pill_x2, pill_y2 - b_notch),
            (pill_x2 - b_notch, pill_y2),
            (pill_x1 + b_notch, pill_y2),
            (pill_x1, pill_y2 - b_notch),
            (pill_x1, pill_y1 + b_notch),
            (pill_x1 + b_notch, pill_y1)
        ]
        draw.polygon(badge_pts, fill=(18, 5, 24, 215), outline=glow_rgba, width=3)
        # Inner accent lines
        draw.line([(pill_x1 + 10 + b_notch, pill_y1 + 8), (pill_x2 - 10 - b_notch, pill_y1 + 8)], fill=glow_rgba, width=1)
        draw.line([(pill_x1 + 10 + b_notch, pill_y2 - 8), (pill_x2 - 10 - b_notch, pill_y2 - 8)], fill=glow_rgba, width=1)

        # Horizontal connector antenna lines with terminal microdots
        mid_y = pill_y1 + pill_h // 2
        draw.line([(55, mid_y), (pill_x1 - 15, mid_y)], fill=glow_rgba, width=2)
        draw.ellipse([(pill_x1 - 22, mid_y - 4), (pill_x1 - 14, mid_y + 4)], fill=glow_rgba)
        draw.line([(pill_x2 + 15, mid_y), (width - 55, mid_y)], fill=glow_rgba, width=2)
        draw.ellipse([(pill_x2 + 14, mid_y - 4), (pill_x2 + 22, mid_y + 4)], fill=glow_rgba)

        # Center Name in Badge
        self._draw_glow_text(draw, (width // 2, mid_y), badge_text, font_badge, neon_core, glow_rgba, radius=4)

        # 4. Optional Hook Text Banner (below pill, y ~ 220)
        if hook_text and len(hook_text.strip()) > 0:
            clean_hook = hook_text.strip()
            # If hook is short, draw a glowing floating subtitle
            wrapped_lines = textwrap.wrap(clean_hook, width=34)[:2]
            start_y = pill_y2 + 25
            for idx, line in enumerate(wrapped_lines):
                self._draw_glow_text(draw, (width // 2, start_y + (idx * 46)), line, font_hook, neon_core, glow_rgba, radius=2)

        # 5. Bottom Sleek Footer: ● LIVE      @HANDLE      GIRLS PARTY
        bot_y = 1800
        draw.line([(80, bot_y - 40), (width - 80, bot_y - 40)], fill=glow_rgba, width=1)
        draw.rectangle([(width // 2 - 6, bot_y - 40 - 6), (width // 2 + 6, bot_y - 40 + 6)], fill=glow_rgba)

        # Red/Pink LIVE dot and text
        draw.ellipse([(110, bot_y - 8), (126, bot_y + 8)], fill=(255, 0, 80, 255))
        self._draw_glow_text(draw, (170, bot_y), "LIVE", font_sub, neon_core, glow_rgba, radius=2)

        # Central Handle
        h_text = channel.handle.upper()
        if not h_text.startswith("@"):
            h_text = f"@{h_text}"
        self._draw_glow_text(draw, (width // 2, bot_y), h_text, font_handle, neon_core, glow_rgba, radius=3)

        # Right Niche Tag
        niche_label = "GIRLS PARTY"
        self._draw_glow_text(draw, (width - 170, bot_y), niche_label, font_sub, neon_core, glow_rgba, radius=2)

        canvas.save(output_path, "PNG")
        return output_path

    # 6. ASPECT-RATIO ADAPTIVE CONTAINER BOX (1:1, 9:16, 16:9, etc.)
    def render_adaptive_box_layers(
        self,
        box_coords: Tuple[int, int, int, int],  # (box_x, box_y, box_w, box_h)
        channel: ChannelProfile,
        hook_text: str = "",
        hook_placement: str = "bottom",         # "bottom", "middle", "none"
        template: Optional[NicheTemplate] = None,
        bg_output_path: Optional[Path] = None,
        fg_output_path: Optional[Path] = None
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """
        Renders the two-layer adaptive container:
        1. bg_output_path: 1080x1920 matte tech background + diffuse neon pink outer glow shadow radiating OUTSIDE the box.
        2. fg_output_path: 1080x1920 transparent overlay with sharp neon border lines, corner HUD brackets,
                           top [ C U T E   A A R O H I ] header badge (strictly ABOVE the box),
                           bottom live ticker, and collision-aware hook text placement.
        """
        canvas_w, canvas_h = 1080, 1920
        box_x, box_y, box_w, box_h = box_coords

        glow_hex = getattr(template, "highlight_color", "#FF007F") or "#FF007F"
        glow_rgb = self._hex_to_rgb(glow_hex)
        glow_rgba = glow_rgb + (255,)

        # ---------------- 1. BACKGROUND & OUTER GLOW SHADOW ----------------
        bg = Image.new("RGBA", (canvas_w, canvas_h), (8, 6, 12, 255))
        bg_draw = ImageDraw.Draw(bg)
        for y in range(0, canvas_h, 8):
            bg_draw.line([(0, y), (canvas_w, y)], fill=(14, 11, 18, 255), width=1)

        # Multi-pass outer glowing shadow radiating OUTSIDE the box lines
        shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer)
        s_draw.rectangle([box_x - 6, box_y - 6, box_x + box_w + 6, box_y + box_h + 6], fill=glow_rgb + (140,))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=28))

        mid_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        m_draw = ImageDraw.Draw(mid_glow)
        m_draw.rectangle([box_x - 2, box_y - 2, box_x + box_w + 2, box_y + box_h + 2], fill=glow_rgb + (210,))
        mid_glow = mid_glow.filter(ImageFilter.GaussianBlur(radius=12))

        bg.paste(shadow_layer, (0, 0), shadow_layer)
        bg.paste(mid_glow, (0, 0), mid_glow)

        if bg_output_path:
            bg.save(bg_output_path, "PNG")

        # ---------------- 2. FOREGROUND OVERLAY ----------------
        fg = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        fg_draw = ImageDraw.Draw(fg)

        # Crisp neon frame line bordering the video box
        fg_draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], outline=glow_rgba, width=3)

        # Corner heavy HUD bracket accents
        blen = 50
        # TL
        fg_draw.line([(box_x - 8, box_y - 8 + blen), (box_x - 8, box_y - 8), (box_x - 8 + blen, box_y - 8)], fill=glow_rgba, width=5)
        # TR
        fg_draw.line([(box_x + box_w + 8 - blen, box_y - 8), (box_x + box_w + 8, box_y - 8), (box_x + box_w + 8, box_y - 8 + blen)], fill=glow_rgba, width=5)
        # BL
        fg_draw.line([(box_x - 8, box_y + box_h + 8 - blen), (box_x - 8, box_y + box_h + 8), (box_x - 8 + blen, box_y + box_h + 8)], fill=glow_rgba, width=5)
        # BR
        fg_draw.line([(box_x + box_w + 8 - blen, box_y + box_h + 8), (box_x + box_w + 8, box_y + box_h + 8), (box_x + box_w + 8, box_y + box_h + 8 - blen)], fill=glow_rgba, width=5)

        # Fonts
        try:
            font_badge = ImageFont.truetype(self.font_bold_path, 30)
            font_sub = ImageFont.truetype(self.font_regular_path, 20)
            font_handle = ImageFont.truetype(self.font_bold_path, 24)
            font_hook = ImageFont.truetype(self.font_bold_path, 34)
        except Exception:
            font_badge = font_sub = font_handle = font_hook = ImageFont.load_default()

        # Top Badge: [ C U T E   A A R O H I ] strictly ABOVE the video box!
        raw_name = (channel.display_name or "OCTOPUS").strip()
        spaced_words = [" ".join(list(w.upper())) for w in raw_name.split()]
        badge_text = "   ".join(spaced_words)

        tb = fg_draw.textbbox((0, 0), badge_text, font=font_badge)
        pill_w = max(560, (tb[2] - tb[0]) + 80)
        pill_h = 70
        pill_x1 = (canvas_w - pill_w) // 2
        pill_y1 = max(60, min(100, box_y - 95))
        pill_x2 = pill_x1 + pill_w
        pill_y2 = pill_y1 + pill_h

        b_pts = [
            (pill_x1 + 14, pill_y1), (pill_x2 - 14, pill_y1),
            (pill_x2, pill_y1 + 14), (pill_x2, pill_y2 - 14),
            (pill_x2 - 14, pill_y2), (pill_x1 + 14, pill_y2),
            (pill_x1, pill_y2 - 14), (pill_x1, pill_y1 + 14),
            (pill_x1 + 14, pill_y1)
        ]
        fg_draw.polygon(b_pts, fill=(18, 8, 22, 240), outline=glow_rgba, width=2)
        self._draw_glow_text(fg_draw, (canvas_w // 2, pill_y1 + pill_h // 2), badge_text, font_badge, (255, 255, 255, 255), glow_rgba, radius=3)

        # Horizontal antenna lines
        mid_y = pill_y1 + pill_h // 2
        fg_draw.line([(60, mid_y), (pill_x1 - 15, mid_y)], fill=glow_rgb + (200,), width=2)
        fg_draw.ellipse([(pill_x1 - 22, mid_y - 4), (pill_x1 - 14, mid_y + 4)], fill=glow_rgba)
        fg_draw.line([(pill_x2 + 15, mid_y), (canvas_w - 60, mid_y)], fill=glow_rgb + (200,), width=2)
        fg_draw.ellipse([(pill_x2 + 14, mid_y - 4), (pill_x2 + 22, mid_y + 4)], fill=glow_rgba)

        # Bottom Live Ticker: ● LIVE   @HANDLE   GIRLS PARTY
        bot_y = 1810
        fg_draw.line([(80, bot_y - 35), (canvas_w - 80, bot_y - 35)], fill=glow_rgb + (160,), width=1)
        fg_draw.rectangle([(canvas_w // 2 - 5, bot_y - 35 - 5), (canvas_w // 2 + 5, bot_y - 35 + 5)], fill=glow_rgba)

        fg_draw.ellipse([(110, bot_y - 8), (126, bot_y + 8)], fill=(255, 0, 80, 255))
        self._draw_glow_text(fg_draw, (170, bot_y), "LIVE", font_sub, (255, 255, 255, 255), glow_rgba, radius=2)

        h_text = channel.handle.upper()
        if not h_text.startswith("@"):
            h_text = f"@{h_text}"
        self._draw_glow_text(fg_draw, (canvas_w // 2, bot_y), h_text, font_handle, (255, 255, 255, 255), glow_rgba, radius=2)

        niche_label = "GIRLS PARTY"
        self._draw_glow_text(fg_draw, (canvas_w - 170, bot_y), niche_label, font_sub, (255, 255, 255, 255), glow_rgba, radius=2)

        # Smart Hook Text Placement (only if video is clean of baked-in text)
        if hook_text and hook_placement != "none":
            wrapped = textwrap.wrap(hook_text, width=32)[:2]
            if hook_placement == "middle":
                target_y = box_y + box_h // 2 - (len(wrapped) - 1) * 22
            else:  # "bottom"
                target_y = box_y + box_h - 75 - (len(wrapped) - 1) * 22

            for line in wrapped:
                self._draw_glow_text(fg_draw, (canvas_w // 2, target_y), line, font_hook, (255, 255, 255, 255), glow_rgba, radius=3)
                target_y += 44

        if fg_output_path:
            fg.save(fg_output_path, "PNG")

        return bg_output_path, fg_output_path


