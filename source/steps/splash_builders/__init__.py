# source/steps/splash_builders/__init__.py
"""
Splash video builders package.

This package contains focused modules for generating intro and outro sequences:
- collage_builder: Grid layout and image composition
- video_encoder: FFmpeg clip creation and encoding
- animation_renderer: Flip animation frame generation
- intro_builder: Intro sequence assembly
- outro_builder: Outro sequence assembly
"""

from .collage_builder import CollageBuilder
from .video_encoder import VideoEncoder
from .animation_renderer import AnimationRenderer
from .intro_builder import IntroBuilder
from .outro_builder import OutroBuilder

__all__ = [
    "CollageBuilder",
    "VideoEncoder",
    "AnimationRenderer",
    "IntroBuilder",
    "OutroBuilder",
]