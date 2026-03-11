"""Tests for limewire.core.theme — T namespace, apply_theme, _lerp_color."""

import pytest

from limewire.core.theme import (
    T,
    THEMES,
    THEME_LIVEWIRE,
    _THEME_KEYS,
    _lerp_color,
    apply_theme,
)


class TestThemeNamespace:
    def test_t_has_bg(self):
        assert hasattr(T, "BG")

    def test_t_has_text(self):
        assert hasattr(T, "TEXT")

    def test_t_has_fonts(self):
        assert hasattr(T, "F_TITLE")
        assert hasattr(T, "F_BODY")
        assert hasattr(T, "F_MONO")

    def test_initial_values_are_livewire(self):
        # Apply livewire to reset any prior test mutations
        apply_theme("livewire")
        assert T.BG == THEME_LIVEWIRE["BG"]
        assert T.TEXT == THEME_LIVEWIRE["TEXT"]
        assert T.LIME == THEME_LIVEWIRE["LIME"]


class TestApplyTheme:
    def test_switches_to_dark(self):
        apply_theme("dark")
        assert T.BG == "#1A1D21"
        assert T.TEXT == "#E8EAED"

    def test_switches_to_light(self):
        apply_theme("light")
        assert T.BG == "#F0F2F5"
        assert T.TEXT == "#1A1A2E"

    def test_switches_back_to_livewire(self):
        apply_theme("light")
        apply_theme("livewire")
        assert T.BG == THEME_LIVEWIRE["BG"]

    def test_backward_compat_bool_true(self):
        apply_theme(True)  # should map to "dark"
        assert T.BG == "#1A1D21"

    def test_backward_compat_bool_false(self):
        apply_theme(False)  # should map to "light"
        assert T.BG == "#F0F2F5"

    def test_unknown_theme_falls_back_to_livewire(self):
        apply_theme("nonexistent_theme")
        assert T.BG == THEME_LIVEWIRE["BG"]

    def test_all_themes_apply_without_error(self):
        for name in THEMES:
            apply_theme(name)
            assert hasattr(T, "BG")
            assert hasattr(T, "TEXT")
            assert T.BG.startswith("#")

    def test_fonts_set_after_apply(self):
        apply_theme("dark")
        assert isinstance(T.F_TITLE, tuple)
        assert len(T.F_TITLE) == 2
        assert isinstance(T.F_TITLE[1], int)

    def test_theme_keys_only_allowed(self):
        """apply_theme should only set keys in _THEME_KEYS."""
        apply_theme("livewire")
        for key in THEME_LIVEWIRE:
            assert key in _THEME_KEYS

    def test_backward_compat_defaults(self):
        """Community themes missing new keys get computed defaults."""
        apply_theme("livewire")
        assert hasattr(T, "BTN_PRESSED")
        assert hasattr(T, "CARD_SHADOW")
        assert hasattr(T, "DIVIDER")
        assert hasattr(T, "FOCUS_RING")

    def test_all_themes_exist(self):
        assert len(THEMES) == 15
        expected = {"livewire", "light", "dark", "modern", "synthwave", "dracula",
                    "catppuccin", "tokyo", "spotify", "classic", "nord", "gruvbox",
                    "highcontrast", "oldschool", "electric"}
        assert set(THEMES.keys()) == expected


class TestLerpColor:
    def test_start_returns_c1(self):
        assert _lerp_color("#000000", "#FFFFFF", 0) == "#000000"

    def test_end_returns_c2(self):
        assert _lerp_color("#000000", "#FFFFFF", 1) == "#ffffff"

    def test_midpoint(self):
        result = _lerp_color("#000000", "#FFFFFF", 0.5)
        # Should be approximately #7f7f7f or #808080
        r = int(result[1:3], 16)
        assert 126 <= r <= 128  # allow rounding

    def test_same_color(self):
        assert _lerp_color("#FF0000", "#FF0000", 0.5) == "#ff0000"

    def test_returns_hex_string(self):
        result = _lerp_color("#112233", "#445566", 0.3)
        assert result.startswith("#")
        assert len(result) == 7
