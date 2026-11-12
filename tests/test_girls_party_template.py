from pathlib import Path
from config import ChannelProfile
from renderers.niche_templates import get_template_for_niche, get_template_by_id
from renderers.card_renderer import CardRenderer
from processors.anti_shadowban import AntiShadowbanEngine
from PIL import Image

def test_girls_party_template_resolution():
    tpl = get_template_for_niche("girls_party")
    assert tpl.id == "girls_party_neon"
    assert tpl.overlay_layout == "full_screen_neon_hud"
    assert tpl.highlight_color == "#FF007F"
    assert "🪩" in tpl.badge_icon

def test_girls_party_overlay_generation(tmp_path):
    renderer = CardRenderer()
    channel = ChannelProfile(
        handle="@cute.aarohi.007",
        display_name="Cute Aarohi",
        niche="girls_party",
        logo_filename="logo_cute_aarohi_007.png",
        subreddits=[],
        default_hashtags=[],
        cta_link="bit.ly/cute-aarohi"
    )
    overlay_out = tmp_path / "test_girls_overlay.png"
    renderer.render_header_overlay(
        hook_text="Party anthem with the girls squad",
        channel=channel,
        output_path=overlay_out
    )
    assert overlay_out.exists()
    img = Image.open(overlay_out)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"

def test_girls_party_anti_shadowban_captions():
    caption = AntiShadowbanEngine.mutate_caption(
        base_caption="Unhinged party night with the girls!",
        hook_headline="Unhinged party night with the girls",
        account_handle="@cute.aarohi.007",
        niche="girls_party",
        account_index=0
    )
    assert "@cute.aarohi.007" in caption
    assert any(tag in caption for tag in ["#girlsparty", "#clubbing", "#nightlife", "#weekendmood", "#viralreels"])
