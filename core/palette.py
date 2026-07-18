"""
HERMES Omnimind Absolute Edition
Palette definitions and helper functions for color blending, brightness, and UI mode transitions.
"""

import math
from typing import Tuple

from core.config import UIMode

Color = Tuple[int, int, int]
AlphaColor = Tuple[int, int, int, int]


def _clamp(value: float, minimum: int = 0, maximum: int = 255) -> int:
    return max(minimum, min(maximum, int(round(value))))


def mix(a: Color, b: Color, t: float) -> Color:
    """Return the clamped linear interpolation between two RGB colors."""
    t = max(0.0, min(1.0, t))
    return (
        _clamp(a[0] + (b[0] - a[0]) * t),
        _clamp(a[1] + (b[1] - a[1]) * t),
        _clamp(a[2] + (b[2] - a[2]) * t),
    )


def with_alpha(color: Color, alpha: int) -> AlphaColor:
    """Return an RGBA tuple from an RGB color and alpha value."""
    return (
        _clamp(color[0]),
        _clamp(color[1]),
        _clamp(color[2]),
        _clamp(alpha),
    )


def depth_shade(near: Color, far: Color, depth_t: float) -> Color:
    """Blend between near and far colors based on depth ratio."""
    depth_t = max(0.0, min(1.0, depth_t))
    return mix(near, far, depth_t)


def brightness(color: Color, factor: float) -> Color:
    """Scale the brightness of an RGB color."""
    return (
        _clamp(color[0] * factor),
        _clamp(color[1] * factor),
        _clamp(color[2] * factor),
    )


def pulse(color: Color, t: float) -> Color:
    """Return a pulsing version of a color for a time parameter."""
    intensity = 0.8 + 0.2 * math.sin(2.0 * math.pi * t)
    return brightness(color, intensity)


_current_mode = UIMode.BOTH
_target_mode = UIMode.BOTH
_transition_progress = 1.0
_transition_speed = 0.08


def set_mode(mode: str) -> None:
    """Request a UI palette mode transition."""
    global _target_mode, _transition_progress
    if mode not in (UIMode.ARCHER, UIMode.HUDSON, UIMode.BOTH):
        return
    if mode == _target_mode:
        return
    _target_mode = mode
    _transition_progress = 0.0


def tick_transition() -> None:
    """Advance the internal palette mode transition state."""
    global _current_mode, _transition_progress
    if _current_mode == _target_mode:
        _transition_progress = 1.0
        return

    _transition_progress += _transition_speed
    if _transition_progress >= 1.0:
        _transition_progress = 1.0
        _current_mode = _target_mode


def get_mode() -> str:
    """Return the current effective UI mode."""
    return _current_mode


class Palette:
    BLACK = (0, 0, 0)
    WHITE = (255, 255, 255)
    CYAN = (0, 255, 255)
    AMBER = (255, 191, 0)
    GRID = (48, 58, 78)
    INK = (18, 24, 36)
    ALERT = (255, 80, 80)
    LIGHT_GRAY = (210, 210, 220)
    DARK_GRAY = (80, 85, 95)
    SOFT_WHITE = (240, 240, 240)


# Expose the palette helpers on module import
__all__ = [
    "UIMode",
    "Palette",
    "mix",
    "with_alpha",
    "depth_shade",
    "brightness",
    "pulse",
    "set_mode",
    "tick_transition",
    "get_mode",
]
