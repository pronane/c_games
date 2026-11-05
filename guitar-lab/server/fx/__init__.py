"""Guitar / production effects library: render, feature templates, classify, undo."""

from .features import extract_features, FEATURE_NAMES
from .classify import EffectMatcher, match_effects
from .undo import undo_effects, acoustic_playback
from .renderers import apply_effect, EFFECT_NAMES
from .playback import render_acoustic, render_distorted

__all__ = [
    'extract_features', 'FEATURE_NAMES',
    'EffectMatcher', 'match_effects',
    'undo_effects', 'acoustic_playback',
    'apply_effect', 'EFFECT_NAMES',
    'render_acoustic', 'render_distorted',
]
