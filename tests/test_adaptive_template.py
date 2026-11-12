import pytest
from pathlib import Path
from PIL import Image
from config import ChannelProfile
from processors.video_vision import VideoVisionInspector
from renderers.card_renderer import CardRenderer
from renderers.video_compositor import VideoCompositor
from renderers.niche_templates import get_template_for_niche
import subprocess

@pytest.fixture
def test_channel():
    return ChannelProfile(
        handle='@cute.aarohi.007',
        display_name='Cute Aarohi',
        niche='girls_party',
        logo_filename='logo_cute_aarohi_007.png',
        subreddits=[],
        default_hashtags=[],
        cta_link='bit.ly/cute-aarohi'
    )

def test_adaptive_box_layer_generation(tmp_path, test_channel):
    renderer = CardRenderer()
    template = get_template_for_niche('girls_party')
    
    bg_out = tmp_path / 'bg.png'
    fg_out = tmp_path / 'fg.png'
    
    # Test for square box coords: 960x960
    box_coords = (60, 480, 960, 960)
    renderer.render_adaptive_box_layers(
        box_coords=box_coords,
        channel=test_channel,
        hook_text='Party night vibes with the girls squad',
        hook_placement='bottom',
        template=template,
        bg_output_path=bg_out,
        fg_output_path=fg_out
    )
    
    assert bg_out.exists()
    assert fg_out.exists()
    
    with Image.open(bg_out) as bg_img:
        assert bg_img.size == (1080, 1920)
        assert bg_img.mode == 'RGBA'
        
    with Image.open(fg_out) as fg_img:
        assert fg_img.size == (1080, 1920)
        assert fg_img.mode == 'RGBA'

def test_adaptive_video_compositor_square(tmp_path, test_channel):
    # Generate 1-second synthetic square video
    sample_square = tmp_path / 'synth_square.mp4'
    subprocess.run([
        'ffmpeg', '-y', '-f', 'lavfi', '-i',
        'color=c=purple:s=720x720:d=1',
        '-pix_fmt', 'yuv420p', str(sample_square)
    ], check=True, capture_output=True)
    
    compositor = VideoCompositor()
    compositor.output_dir = tmp_path
    
    out_reel = compositor.build_reel(
        raw_video_path=sample_square,
        channel=test_channel,
        hook_text='Square clip party vibes',
        output_filename='output_square_reel.mp4',
        account_index=0
    )
    
    assert out_reel is not None
    assert Path(out_reel).exists()
    assert Path(out_reel).stat().st_size > 10000
    
    meta = VideoVisionInspector.get_video_metadata(out_reel)
    assert meta['width'] == 1080
    assert meta['height'] == 1920
