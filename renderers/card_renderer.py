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
            
        self.font_black_path = "C:/Windows/Fonts/ariblk.ttf"
        if not os.path.exists(self.font_black_path):
            self.font_black_path = self.font_bold_path

        self.font_regular_path = "C:/Windows/Fonts/segoeui.ttf"
        if not os.path.exists(self.font_regular_path):
            self.font_regular_path = "C:/Windows/Fonts/arial.ttf"

        self.font_serif_path = "C:/Windows/Fonts/georgiab.ttf"
        if not os.path.exists(self.font_serif_path):
            self.font_serif_path = "C:/Windows/Fonts/timesbd.ttf"

    def _find_logo_path(self, channel: ChannelProfile) -> Optional[Path]:
        """Looks for specific or master logo in assets and assets/logos directory."""
        candidates = []
        if getattr(channel, "logo_filename", None):
            candidates.append(self.assets_dir / channel.logo_filename)
            candidates.append(self.assets_dir / "logos" / channel.logo_filename)
        
        # Check by handle or display name
        h_clean = channel.handle.lstrip("@").replace("octopus.", "").replace(".", "_")
        candidates.append(self.assets_dir / f"logo_{h_clean}.png")
        candidates.append(self.assets_dir / "logos" / f"logo_{h_clean}.png")
        candidates.append(self.assets_dir / f"logo_{channel.display_name.lower().replace(' ', '_')}.png")
        candidates.append(self.assets_dir / "logos" / f"logo_{channel.display_name.lower().replace(' ', '_')}.png")
        
        # Cult Information branding
        niche_val = getattr(channel, "niche", "").lower()
        if "cult" in h_clean or "cult" in niche_val or "info" in niche_val or "ai_tech" in niche_val:
            candidates.append(self.assets_dir / "logos" / "logo_cult_badge.png")
            candidates.append(self.assets_dir / "logo_cult_badge.png")
            candidates.append(self.assets_dir / "logos" / "logo_cult_information.png")

        candidates.append(self.assets_dir / "logo.png")
        
        for cand in candidates:
            if cand.exists():
                return cand
        return None

    @staticmethod
    def compute_dynamic_highlights(hook_text: str, highlight_input: Optional[str] = None) -> str:
        """
        Dynamically calculates theme neon highlight phrases based on word count:
        - Short headlines (<= 8 words): higher highlight density (~40%-55%)
        - Medium headlines (9-14 words): balanced highlight (~30%-40%)
        - Long headlines (>= 15 words): distributed highlight (~25%-35%, 5-8 words across lines)
        Preserves dual-tone white base + neon accent without ever highlighting 100%.
        """
        import re
        raw_words = hook_text.split()
        total_words = len(raw_words)
        if total_words == 0:
            return ""

        stop_words = {
            'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'with', 'by',
            'from', 'this', 'that', 'these', 'those', 'just', 'is', 'are', 'was', 'were', 'be',
            'been', 'has', 'have', 'had', 'do', 'does', 'did', 'can', 'could', 'will', 'would',
            'shall', 'should', 'may', 'might', 'must', 'so', 'as', 'but', 'if', 'it', 'its',
            'my', 'your', 'his', 'her', 'their', 'our', 'what', 'which', 'who', 'whom', 'into',
            'onto', 'about', 'than', 'more', 'less', 'within', 'over'
        }

        # If explicit highlight phrases are given, check if coverage is balanced
        if highlight_input:
            provided_phrases = [p.strip() for p in re.split(r'[,;|\n]', str(highlight_input)) if p.strip()]
            if provided_phrases:
                hl_words_count = sum(len(p.split()) for p in provided_phrases)
                ratio = hl_words_count / max(1, total_words)
                if 0.20 <= ratio <= 0.60:
                    return ', '.join(provided_phrases)

        if total_words <= 8:
            target_hl_count = max(2, int(round(total_words * 0.45)))
        elif total_words <= 14:
            target_hl_count = max(3, int(round(total_words * 0.35)))
        else:
            target_hl_count = max(5, int(round(total_words * 0.30)))

        scores = []
        for i, w in enumerate(raw_words):
            clean = re.sub(r'[^a-zA-Z0-9$%.-]', '', w).lower()
            if clean in stop_words:
                base_score = -5.0
            else:
                base_score = 2.0
                if any(c.isdigit() for c in w) or any(c in w for c in ['$', '%']):
                    base_score += 4.0
                if w.isupper() and len(w) > 1:
                    base_score += 4.0
                elif w[0].isupper():
                    base_score += 2.0
                if any(k in clean for k in ['ai', 'robot', 'game', 'shooter', 'fable', 'claude', 'tech', 'human', 'pro', 'secret', 'breakthrough', 'history', 'capabilities']):
                    base_score += 3.0
            scores.append((i, base_score, w))

        phrase_candidates = []
        for length in [4, 3, 2]:
            for i in range(len(raw_words) - length + 1):
                chunk = raw_words[i:i+length]
                chunk_scores = [scores[i+j][1] for j in range(length)]
                if chunk_scores[0] > 0 and chunk_scores[-1] > 0:
                    avg_score = sum(chunk_scores)
                    phrase_candidates.append((avg_score, i, length, ' '.join(chunk)))

        phrase_candidates.sort(key=lambda x: x[0], reverse=True)

        selected_phrases = []
        covered_indices = set()
        total_selected_words = 0

        for score, idx, length, text in phrase_candidates:
            indices = set(range(idx, idx + length))
            if not indices.intersection(covered_indices):
                if not any(abs(idx - ci) <= 1 for ci in covered_indices) or not selected_phrases:
                    selected_phrases.append(text)
                    covered_indices.update(indices)
                    total_selected_words += length
                if total_selected_words >= target_hl_count:
                    break

        if not selected_phrases and highlight_input:
            return str(highlight_input)

        return ', '.join(selected_phrases)

    def render_header_overlay(
        self,
        hook_text: str,
        channel: ChannelProfile,
        output_path: Path,
        credit_handle: Optional[str] = None,
        highlight_word: Optional[str] = None,
        template: Optional[NicheTemplate] = None,
        template_id: Optional[str] = None,
        aspect_ratio: Optional[float] = None,
        show_credit: bool = False
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
            return self._render_top_card_cult(hook_text, channel, output_path, credit_handle, highlight_word, template, aspect_ratio=aspect_ratio, show_credit=show_credit)

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

    # 1. TOP CARD CULT (Cult Information / Tech)
    def _render_top_card_cult(
        self,
        hook_text: str,
        channel: ChannelProfile,
        output_path: Path,
        credit_handle: Optional[str] = None,
        highlight_word: Optional[str] = None,
        template: Optional[NicheTemplate] = None,
        aspect_ratio: Optional[float] = None,
        show_credit: bool = False
    ) -> Path:
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        highlight_color = getattr(template, "highlight_color", "#C1F02A") or "#C1F02A"
        if isinstance(highlight_color, str) and highlight_color.startswith("#"):
            hc_hex = highlight_color.lstrip("#")
            if len(hc_hex) == 6:
                neon_color = tuple(int(hc_hex[i:i+2], 16) for i in (0, 2, 4)) + (255,)
            else:
                neon_color = (193, 240, 42, 255)
        else:
            neon_color = (193, 240, 42, 255)

        white_color = (255, 255, 255, 255)

        # 1. Fonts
        try:
            headline_font = ImageFont.truetype(self.font_black_path, 44)
        except Exception:
            try:
                headline_font = ImageFont.truetype(self.font_bold_path, 44)
            except Exception:
                headline_font = ImageFont.load_default()

        try:
            handle_font = ImageFont.truetype(self.font_bold_path, 36)
        except Exception:
            handle_font = ImageFont.load_default()

        try:
            credit_font = ImageFont.truetype(self.font_regular_path, 22)
        except Exception:
            credit_font = ImageFont.load_default()

        # 2. Text Wrapping for Headline
        wrapped_lines = textwrap.wrap(hook_text, width=36)
        if not wrapped_lines:
            wrapped_lines = [hook_text]
        line_height = 66
        headline_total_h = len(wrapped_lines) * line_height

        # 3. Dynamic Aspect-Ratio Based Vertical Positioning:
        # - 16:9 / Cropped (Widescreen >= 1.25): Shift header downwards to eliminate empty top void
        # - 1:1 (Square 0.85 to 1.25): Shift header upwards to comfortably fit 1080x1080 video
        # - 9:16 (Vertical <= 0.70): Standard top safe positioning
        if aspect_ratio is not None and aspect_ratio >= 1.25:
            row_y = 190
            y_text = 305
        elif aspect_ratio is not None and 0.85 <= aspect_ratio < 1.25:
            row_y = 100
            y_text = 195
        else:
            row_y = 140
            y_text = 245

        # Dynamic Black Header Background covering top area
        header_h = max(440, y_text + headline_total_h + 30)
        draw.rectangle([0, 0, 1080, header_h], fill=(0, 0, 0, 255))

        # 4. Centered Header Row: [Circular Badge] + @handle + [Verified Badge]
        badge_size = 76
        logo_path = self._find_logo_path(channel)
        if not logo_path or not logo_path.exists():
            logo_path = self.assets_dir / "logos" / "logo_cult_badge.png"

        badge_img = None
        if logo_path and logo_path.exists():
            try:
                raw_badge = Image.open(logo_path).convert("RGBA")
                badge_img = raw_badge.resize((badge_size, badge_size), Image.Resampling.LANCZOS)
            except Exception:
                badge_img = None

        raw_handle = getattr(channel, "handle", "@cult_information") or "@cult_information"
        handle_text = raw_handle if raw_handle.startswith("@") else f"@{raw_handle}"
        
        h_bbox = draw.textbbox((0, 0), handle_text, font=handle_font)
        handle_w = h_bbox[2] - h_bbox[0]
        handle_h = h_bbox[3] - h_bbox[1]

        verified_size = 28
        gap1 = 18
        gap2 = 14

        total_row_w = badge_size + gap1 + handle_w + gap2 + verified_size
        start_x = (1080 - total_row_w) // 2

        # Render Badge
        if badge_img:
            canvas.paste(badge_img, (start_x, row_y), badge_img)
        else:
            draw.ellipse([start_x, row_y, start_x + badge_size, row_y + badge_size], fill=(0, 0, 0, 255), outline=neon_color, width=4)
            draw.text((start_x + 16, row_y + 20), "CULT", font=handle_font, fill=neon_color)

        # Render Handle Text
        handle_x = start_x + badge_size + gap1
        handle_y = row_y + (badge_size - handle_h) // 2 - 4
        draw.text((handle_x, handle_y), handle_text, font=handle_font, fill=white_color)

        # Render Blue Verified Badge
        vx = handle_x + handle_w + gap2
        vy = row_y + (badge_size - verified_size) // 2
        draw.ellipse([vx, vy, vx + verified_size, vy + verified_size], fill=(0, 149, 246, 255))
        draw.line([vx + 7, vy + 14, vx + 12, vy + 19], fill=(255, 255, 255, 255), width=3)
        draw.line([vx + 12, vy + 19, vx + 21, vy + 9], fill=(255, 255, 255, 255), width=3)

        # 5. Dynamic Theme Neon Highlights
        effective_highlight = self.compute_dynamic_highlights(hook_text, highlight_word)

        def parse_line_highlights(line: str, highlight_input: Optional[str]):
            import re
            if not highlight_input:
                return [(line, False)]
            raw_phrases = [p.strip() for p in re.split(r'[,;|\n]', str(highlight_input)) if p.strip()]
            if not raw_phrases:
                raw_phrases = [w.strip() for w in str(highlight_input).split() if w.strip()]
            if not raw_phrases:
                return [(line, False)]

            raw_phrases = sorted(raw_phrases, key=lambda x: len(x), reverse=True)
            pattern = '(' + '|'.join(re.escape(p) for p in raw_phrases) + ')'
            parts = re.split(pattern, line, flags=re.IGNORECASE)
            hl_set = set(p.lower().strip(".,!?:;\"'") for p in raw_phrases)
            
            result = []
            for part in parts:
                if not part:
                    continue
                clean_part = part.lower().strip(".,!?:;\"'")
                is_hl = clean_part in hl_set or any(w in hl_set for w in clean_part.split())
                result.append((part, is_hl))
            return result

        # 6. Render Centered Headline Lines
        y_cursor = y_text
        for line in wrapped_lines:
            line_parts = parse_line_highlights(line, effective_highlight)
            
            # Measure total width of line
            line_w = 0
            item_widths = []
            for text_part, is_hl in line_parts:
                bbox = draw.textbbox((0, 0), text_part, font=headline_font)
                w = bbox[2] - bbox[0]
                item_widths.append(w)
                line_w += w

            cur_x = (1080 - line_w) // 2
            for (text_part, is_hl), w in zip(line_parts, item_widths):
                c = neon_color if is_hl else white_color
                # Drop shadow for depth and contrast
                draw.text((cur_x + 2, y_cursor + 2), text_part, font=headline_font, fill=(0, 0, 0, 180))
                draw.text((cur_x, y_cursor), text_part, font=headline_font, fill=c)
                cur_x += w

            y_cursor += line_height

        # 7. Source Attribution Pill (optional, disabled by default per user request)
        if show_credit and credit_handle:
            clean_credit = credit_handle.strip().lstrip("@")
            credit_text = f"Source: @{clean_credit}"
            credit_y = y_cursor + 12
            c_bbox = draw.textbbox((0, 0), credit_text, font=credit_font)
            cw = c_bbox[2] - c_bbox[0]
            cx = (1080 - cw) // 2
            pill_bbox = [cx - 16, credit_y - 4, cx + cw + 16, credit_y + 28]
            draw.rounded_rectangle(pill_bbox, radius=12, fill=(15, 23, 42, 200), outline=(193, 240, 42, 140), width=1)
            draw.text((cx, credit_y), credit_text, font=credit_font, fill=neon_color)

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

        glow_hex = getattr(template, "highlight_color", "#FF1493") or "#FF1493"
        glow_rgb = self._hex_to_rgb(glow_hex)
        glow_rgba = glow_rgb + (255,)

        # Helper vector drawing methods
        import math
        def _draw_sparkle(draw, center, size, color):
            cx, cy = center
            pts = [
                (cx, cy - size), (cx + size * 0.26, cy - size * 0.26),
                (cx + size, cy), (cx + size * 0.26, cy + size * 0.26),
                (cx, cy + size), (cx - size * 0.26, cy + size * 0.26),
                (cx - size, cy), (cx - size * 0.26, cy - size * 0.26)
            ]
            draw.polygon(pts, fill=color)

        def _draw_heart(draw, center, size, color):
            cx, cy = center
            pts = []
            for step in range(0, 360, 10):
                t = math.radians(step)
                x = 16 * (math.sin(t) ** 3)
                y = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
                pts.append((cx + x * (size / 18.0), cy + y * (size / 18.0)))
            draw.polygon(pts, fill=color)

        # ---------------- 1. BACKGROUND, CUTE DECOR & OUTER GLOW SHADOW ----------------
        bg = Image.new("RGBA", (canvas_w, canvas_h), (10, 7, 14, 255))
        bg_draw = ImageDraw.Draw(bg)
        for y in range(canvas_h):
            t = abs(y - canvas_h // 2) / (canvas_h // 2)
            r = int(18 * (1 - 0.45 * t))
            g = int(9 * (1 - 0.45 * t))
            b = int(24 * (1 - 0.45 * t))
            bg_draw.line([(0, y), (canvas_w, y)], fill=(r, g, b, 255))

        # Cute aesthetic floating elements (sparkles and hearts) outside boundary box
        decor = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        d_draw = ImageDraw.Draw(decor)

        sparkle_items = [
            ((75, 80), 20, (255, 120, 200, 240)), ((1005, 85), 18, (255, 255, 255, 255)),
            ((180, 140), 14, (255, 160, 220, 210)), ((900, 145), 16, (220, 180, 255, 220)),
            ((40, 450), 16, (255, 140, 210, 220)), ((1040, 480), 18, (255, 255, 255, 240)),
            ((45, 880), 14, (255, 100, 180, 210)), ((1035, 920), 15, (220, 160, 255, 210)),
            ((40, 1320), 17, (255, 140, 210, 220)), ((1040, 1360), 18, (255, 255, 255, 230)),
            ((90, 1770), 22, (255, 120, 200, 240)), ((990, 1780), 20, (255, 255, 255, 255)),
            ((220, 1845), 15, (255, 160, 220, 210)), ((860, 1855), 16, (220, 180, 255, 220))
        ]
        for pos, sz, col in sparkle_items:
            if not (box_x - 8 <= pos[0] <= box_x + box_w + 8 and box_y - 8 <= pos[1] <= box_y + box_h + 8):
                _draw_sparkle(d_draw, pos, sz, col)

        heart_items = [
            ((70, 240), 14, (255, 40, 130, 230)), ((1010, 260), 16, (255, 80, 160, 240)),
            ((45, 680), 12, (255, 60, 150, 200)), ((1035, 720), 14, (255, 70, 160, 210)),
            ((50, 1540), 15, (255, 50, 140, 220)), ((1030, 1560), 16, (255, 80, 160, 230)),
            ((150, 1810), 13, (255, 50, 140, 220)), ((930, 1820), 14, (255, 80, 160, 230))
        ]
        for pos, sz, col in heart_items:
            if not (box_x - 8 <= pos[0] <= box_x + box_w + 8 and box_y - 8 <= pos[1] <= box_y + box_h + 8):
                _draw_heart(d_draw, pos, sz, col)

        decor_glow = decor.filter(ImageFilter.GaussianBlur(radius=5))
        bg.paste(decor_glow, (0, 0), decor_glow)
        bg.paste(decor, (0, 0), decor)

        # Multi-pass outer glowing shadow radiating OUTSIDE the box lines
        shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow_layer)
        s_draw.rectangle([box_x - 16, box_y - 16, box_x + box_w + 16, box_y + box_h + 16], fill=glow_rgb + (85,))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=28))

        mid_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        m_draw = ImageDraw.Draw(mid_glow)
        m_draw.rectangle([box_x - 4, box_y - 4, box_x + box_w + 4, box_y + box_h + 4], fill=glow_rgb + (180,))
        mid_glow = mid_glow.filter(ImageFilter.GaussianBlur(radius=10))

        bg.paste(shadow_layer, (0, 0), shadow_layer)
        bg.paste(mid_glow, (0, 0), mid_glow)

        if bg_output_path:
            bg.save(bg_output_path, "PNG")

        # ---------------- 2. FOREGROUND OVERLAY ----------------
        fg = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        fg_draw = ImageDraw.Draw(fg)

        # Crisp neon frame line bordering the video box
        fg_draw.rectangle([box_x, box_y, box_x + box_w, box_y + box_h], outline=glow_rgba, width=3)

        # Corner squarish notches
        c_len = 24
        fg_draw.line([(box_x - 4, box_y - 4), (box_x + c_len, box_y - 4)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x - 4, box_y - 4), (box_x - 4, box_y + c_len)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x + box_w + 4, box_y - 4), (box_x + box_w - c_len, box_y - 4)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x + box_w + 4, box_y - 4), (box_x + box_w + 4, box_y + c_len)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x - 4, box_y + box_h + 4), (box_x + c_len, box_y + box_h + 4)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x - 4, box_y + box_h + 4), (box_x - 4, box_y + box_h - c_len)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x + box_w + 4, box_y + box_h + 4), (box_x + box_w - c_len, box_y + box_h + 4)], fill=(255, 140, 210, 255), width=3)
        fg_draw.line([(box_x + box_w + 4, box_y + box_h + 4), (box_x + box_w + 4, box_y + box_h - c_len)], fill=(255, 140, 210, 255), width=3)

        # Fonts
        try:
            font_badge = ImageFont.truetype(self.font_bold_path, 30)
            font_sub = ImageFont.truetype(self.font_regular_path, 20)
            font_hook = ImageFont.truetype(self.font_bold_path, 42)
        except Exception:
            font_badge = font_sub = font_hook = ImageFont.load_default()

        # Top Badge in SQUARISH form: contains original handle (e.g. @cute.aarohi.007)
        handle_text = channel.handle
        if not handle_text.startswith("@"):
            handle_text = f"@{handle_text}"

        tb = fg_draw.textbbox((0, 0), handle_text, font=font_badge)
        badge_w = (tb[2] - tb[0]) + 44
        badge_h = 54
        badge_x1 = (canvas_w - badge_w) // 2
        badge_y1 = max(72, box_y - 82)
        badge_x2 = badge_x1 + badge_w
        badge_y2 = badge_y1 + badge_h

        # Squarish box glow
        b_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(b_glow)
        bg_draw.rounded_rectangle([badge_x1 - 3, badge_y1 - 3, badge_x2 + 3, badge_y2 + 3], radius=4, fill=glow_rgb + (140,))
        b_glow = b_glow.filter(ImageFilter.GaussianBlur(radius=8))
        fg.paste(b_glow, (0, 0), b_glow)

        # Draw clean squarish box (radius=4)
        fg_draw.rounded_rectangle([badge_x1, badge_y1, badge_x2, badge_y2], radius=4, fill=(24, 14, 32, 245), outline=glow_rgba, width=2)
        fg_draw.rectangle([badge_x1 + 4, badge_y1 + 4, badge_x1 + 7, badge_y1 + 7], fill=(255, 160, 220, 255))
        fg_draw.rectangle([badge_x2 - 7, badge_y2 - 7, badge_x2 - 4, badge_y2 - 4], fill=(255, 160, 220, 255))
        fg_draw.text((canvas_w // 2, badge_y1 + badge_h // 2), handle_text, font=font_badge, fill="#FFFFFF", anchor="mm")

        # Bottom subtle footer with glowing hearts
        footer_y = 1820
        fg_draw.line([(120, footer_y - 22), (canvas_w - 120, footer_y - 22)], fill=(45, 28, 55, 200), width=1)
        footer_text = (getattr(channel, "display_name", "") or handle_text.lstrip("@")).upper()
        ft_w = fg_draw.textlength(footer_text, font=font_sub)
        _draw_heart(fg_draw, (int(canvas_w // 2 - ft_w / 2 - 22), footer_y), 9, (255, 40, 130, 255))
        fg_draw.text((canvas_w // 2, footer_y), footer_text, font=font_sub, fill="#F0D5E8", anchor="mm")
        _draw_heart(fg_draw, (int(canvas_w // 2 + ft_w / 2 + 22), footer_y), 9, (255, 40, 130, 255))

        # Video interior is kept 100% clean and raw (no text written over the footage)
        if fg_output_path:
            fg.save(fg_output_path, "PNG")

        return bg_output_path, fg_output_path

    # ------------------------------------------------------------------
    # Lightweight overlays for full-bleed niches
    # (AI showcase, concerts, girls' dance) and the native meme format.
    # Instagram's Reels UI covers roughly the top ~150px and bottom ~420px,
    # plus a right-hand button rail, so all text stays inside a safe zone.
    # ------------------------------------------------------------------
    SAFE_TOP = 170
    SAFE_BOTTOM = 1500

    def _font(self, path: str, size: int):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def _hex_to_rgb(color: str, default=(255, 255, 255)) -> Tuple[int, int, int]:
        try:
            c = color.lstrip("#")
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return default

    @staticmethod
    def _clean_handle(channel: ChannelProfile) -> str:
        h = channel.handle or ""
        return h if h.startswith("@") else f"@{h}"

    def _wrap(self, draw: ImageDraw.ImageDraw, text: str, font, max_w: int):
        words, lines, cur = text.split(), [], ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def measure_meme_bar(self, caption: str, canvas_w: int = 1080) -> int:
        """Height of the white meme caption bar needed for this caption."""
        font = self._font(self.font_bold_path, 54)
        tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        lines = self._wrap(tmp, caption or "", font, canvas_w - 120) or [""]
        line_h = 68
        return max(220, len(lines) * line_h + 110)

    def render_minimal_overlay(
        self,
        profile: str,
        channel: ChannelProfile,
        output_path: Path,
        hook_text: str = "",
        credit_handle: Optional[str] = None,
        template: Optional[NicheTemplate] = None,
        meme_bar_y: int = 0,
        meme_bar_h: int = 0,
        canvas_w: int = 1080,
        canvas_h: int = 1920,
    ) -> Path:
        """
        Renders a transparent 1080x1920 overlay for the non-template render profiles:
        - 'light_brand'   : corner handle chip + optional short hook near the top
        - 'concert_tag'   : lower-third 'ARTIST • CITY • VENUE' + filmer credit + corner handle
        - 'raw_watermark' : semi-transparent micro watermark only (no on-video text)
        - 'meme_native'   : white caption bar (black text) + small grey handle inside the bar
        """
        accent = self._hex_to_rgb(getattr(template, "highlight_color", "#FFFFFF"))
        handle = self._clean_handle(channel)
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        def handle_chip(x: int, y: int, alpha: int = 150):
            f = self._font(self.font_bold_path, 28)
            tw = draw.textlength(handle, font=f)
            draw.rounded_rectangle([x, y, x + tw + 36, y + 50], radius=10, fill=(0, 0, 0, alpha))
            draw.rectangle([x, y + 10, x + 4, y + 40], fill=accent + (255,))
            draw.text((x + 20, y + 25), handle, font=f, fill=(255, 255, 255, 235), anchor="lm")

        def shadow_text(xy, text, font, fill, anchor="mm"):
            x, y = xy
            draw.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0, 170), anchor=anchor)
            draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

        if profile == "raw_full_bleed":
            # 100% clean video — no graphics, no watermark, no framework at all
            pass

        elif profile == "logo_only":
            # Live concerts: clean full-screen video with ONLY the logo watermark
            logo_path = self._find_logo_path(channel)
            logo_placed = False
            if logo_path and logo_path.exists():
                try:
                    logo_img = Image.open(logo_path).convert("RGBA")
                    # Maintain aspect ratio, max 64x64
                    logo_img.thumbnail((64, 64), Image.Resampling.LANCZOS)
                    # Apply subtle opacity (85%) for clean watermark look
                    r, g, b, a = logo_img.split()
                    a = a.point(lambda p: int(p * 0.85))
                    logo_img.putalpha(a)
                    # Paste with a soft subtle circular shadow behind for contrast
                    lx, ly = 52, self.SAFE_TOP
                    draw.ellipse([lx - 4, ly - 4, lx + logo_img.width + 4, ly + logo_img.height + 4], fill=(0, 0, 0, 90))
                    img.paste(logo_img, (lx, ly), logo_img)
                    logo_placed = True
                except Exception as e:
                    logger.warning(f"Could not load logo image for logo_only overlay: {e}")

            if not logo_placed:
                # Minimalist watermark logo badge fallback
                handle_chip(52, self.SAFE_TOP, alpha=130)

        elif profile == "light_brand":
            handle_chip(48, self.SAFE_TOP)
            if hook_text and hook_text.strip():
                f = self._font(self.font_bold_path, 50)
                lines = self._wrap(draw, hook_text.strip(), f, canvas_w - 200)[:2]
                y = self.SAFE_TOP + 120
                for ln in lines:
                    shadow_text((canvas_w // 2, y), ln, f, (255, 255, 255, 255))
                    y += 62

        elif profile == "concert_tag":
            handle_chip(48, self.SAFE_TOP, alpha=120)
            tag = (hook_text or "").strip().upper()
            credit = (credit_handle or "").strip()
            if credit and not credit.startswith("@"):
                credit = f"@{credit}"
            if tag or credit:
                f_tag = self._font(self.font_bold_path, 40)
                f_cr = self._font(self.font_regular_path, 26)
                tag_lines = self._wrap(draw, tag, f_tag, canvas_w - 260)[:2] if tag else []
                block_h = len(tag_lines) * 50 + (40 if credit else 0) + 30
                y0 = self.SAFE_BOTTOM - block_h - 40
                plate = Image.new("RGBA", (canvas_w, block_h + 60), (0, 0, 0, 0))
                pd = ImageDraw.Draw(plate)
                for i in range(block_h + 60):
                    a = int(140 * min(1.0, i / max(1, (block_h + 60) * 0.6)))
                    pd.line([(0, i), (canvas_w, i)], fill=(0, 0, 0, a))
                img.alpha_composite(plate, (0, y0 - 30))
                draw.rectangle([48, y0, 54, y0 + block_h - 20], fill=accent + (255,))
                y = y0 + 25
                for ln in tag_lines:
                    draw.text((76, y), ln, font=f_tag, fill=(255, 255, 255, 255), anchor="lm")
                    y += 50
                if credit:
                    draw.text((76, y), f"filmed by {credit}", font=f_cr, fill=accent + (255,), anchor="lm")

        elif profile == "raw_watermark":
            f = self._font(self.font_bold_path, 30)
            draw.text((52, self.SAFE_TOP + 10), handle, font=f, fill=(0, 0, 0, 60), anchor="lm")
            draw.text((50, self.SAFE_TOP + 8), handle, font=f, fill=(255, 255, 255, 110), anchor="lm")

        elif profile == "meme_native":
            bar_h = meme_bar_h or self.measure_meme_bar(hook_text, canvas_w)
            y0 = meme_bar_y
            draw.rectangle([0, y0, canvas_w, y0 + bar_h], fill=(255, 255, 255, 255))
            f = self._font(self.font_bold_path, 54)
            lines = self._wrap(draw, (hook_text or "").strip(), f, canvas_w - 120)
            line_h = 68
            text_h = len(lines) * line_h
            y = y0 + (bar_h - text_h) // 2 + line_h // 2 - 8
            for ln in lines:
                draw.text((canvas_w // 2, y), ln, font=f, fill=(0, 0, 0, 255), anchor="mm")
                y += line_h
            f_h = self._font(self.font_regular_path, 22)
            draw.text((canvas_w - 24, y0 + bar_h - 14), handle, font=f_h, fill=(140, 140, 140, 255), anchor="rb")

        img.save(output_path, "PNG")
        return output_path

    def render_viral_floating_hook(
        self,
        hook_text: str,
        channel: ChannelProfile,
        output_path: Path,
        credit_handle: Optional[str] = None,
        template: Optional[NicheTemplate] = None,
        canvas_w: int = 1080,
        canvas_h: int = 1920,
    ) -> Path:
        """
        Renders an ultra-modern, frosted-glass floating curiosity hook pill in the top safe zone.
        Leaves 90%+ of the vertical video completely clean while hooking viewers in the first 2-3s.
        Also places a subtle semi-transparent corner handle badge.
        """
        accent = self._hex_to_rgb(getattr(template, "highlight_color", "#FF4FA3"))
        handle = self._clean_handle(channel)
        img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. Subtle, stylish corner handle chip (top-left safe area)
        f_handle = self._font(self.font_bold_path, 26)
        tw = draw.textlength(handle, font=f_handle)
        chip_x, chip_y = 52, self.SAFE_TOP
        draw.rounded_rectangle([chip_x, chip_y, chip_x + tw + 34, chip_y + 46], radius=12, fill=(10, 10, 15, 140))
        draw.rectangle([chip_x, chip_y + 8, chip_x + 4, chip_y + 38], fill=accent + (255,))
        draw.text((chip_x + 18, chip_y + 23), handle, font=f_handle, fill=(255, 255, 255, 230), anchor="lm")

        # 2. Sleek Floating Frosted-Glass Curiosity Pill (Centered horizontally below chip)
        clean_hook = (hook_text or "").strip()
        if clean_hook:
            f_hook = self._font(self.font_bold_path, 42)
            lines = self._wrap(draw, clean_hook, f_hook, canvas_w - 220)[:2]
            if lines:
                line_h = 54
                block_h = len(lines) * line_h + 36
                max_line_w = max(draw.textlength(ln, font=f_hook) for ln in lines)
                pill_w = min(canvas_w - 120, int(max_line_w) + 64)
                pill_x1 = (canvas_w - pill_w) // 2
                pill_x2 = pill_x1 + pill_w
                pill_y1 = self.SAFE_TOP + 70
                pill_y2 = pill_y1 + block_h

                # Frosted glass background pill
                draw.rounded_rectangle(
                    [pill_x1, pill_y1, pill_x2, pill_y2],
                    radius=24,
                    fill=(12, 10, 18, 175),
                    outline=(255, 255, 255, 75),
                    width=2
                )

                # Render hook text with subtle shadow
                text_y = pill_y1 + 18 + line_h // 2
                for ln in lines:
                    draw.text((canvas_w // 2 + 1, text_y + 2), ln, font=f_hook, fill=(0, 0, 0, 180), anchor="mm")
                    draw.text((canvas_w // 2, text_y), ln, font=f_hook, fill=(255, 255, 255, 255), anchor="mm")
                    text_y += line_h

        img.save(output_path, "PNG")
        return output_path



