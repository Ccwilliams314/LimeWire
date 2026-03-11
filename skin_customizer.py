"""
LimeWire Skin Customizer — Visual theme editor with live preview.

Create, edit, and export custom themes for LimeWire Studio Edition.
Saves themes as JSON files compatible with LimeWire's community theme loader
(Tools > Load Community Theme).

Usage:
    python skin_customizer.py
"""

import json
import os
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

# ─── Theme Data ──────────────────────────────────────────────────────────────
# All 37 semantic color keys used by LimeWire themes, organized by category.

CATEGORIES = {
    "Backgrounds": [
        ("BG", "Main background"),
        ("BG_DARK", "Darker background"),
        ("PANEL", "Panel / section background"),
        ("TOOLBAR", "Toolbar background"),
        ("CANVAS_BG", "Audio visualization canvas"),
    ],
    "Text": [
        ("TEXT", "Primary text"),
        ("TEXT_DIM", "Secondary / dimmed text"),
        ("TEXT_BLUE", "Accent text / links"),
    ],
    "Accents": [
        ("LIME", "Primary accent"),
        ("LIME_DK", "Darker accent"),
        ("LIME_LT", "Lighter accent"),
        ("BLUE_HL", "Blue highlight"),
        ("RED", "Red / danger"),
        ("YELLOW", "Yellow / warning"),
        ("ORANGE", "Orange accent"),
    ],
    "Borders & Input": [
        ("BORDER_L", "Light border"),
        ("BORDER_D", "Dark border"),
        ("INPUT_BG", "Input background"),
        ("INPUT_BORDER", "Input border"),
        ("INPUT_FOCUS", "Input focus ring"),
        ("TROUGH", "Scrollbar trough"),
    ],
    "Cards & Buttons": [
        ("CARD_BG", "Card background"),
        ("CARD_BORDER", "Card border"),
        ("CARD_SHADOW", "Card shadow"),
        ("BTN_HOVER", "Button hover"),
        ("BTN_PRESSED", "Button pressed"),
        ("LIME_HOVER", "Accent button hover"),
        ("ORANGE_HOVER", "Orange button hover"),
    ],
    "Surfaces & Layout": [
        ("WHITE", "White equivalent"),
        ("BLACK", "Black equivalent"),
        ("SURFACE", "Elevation surface 1"),
        ("SURFACE_2", "Elevation surface 2"),
        ("SURFACE_3", "Elevation surface 3"),
        ("DIVIDER", "Divider / separator"),
        ("FOCUS_RING", "Focus ring"),
    ],
    "Status & States": [
        ("TAB_ACTIVE", "Active tab indicator"),
        ("SUCCESS", "Success state"),
        ("WARNING", "Warning state"),
        ("ERROR", "Error state"),
        ("INFO", "Info state"),
        ("ACCENT_START", "Gradient start"),
        ("ACCENT_END", "Gradient end"),
    ],
}

ALL_KEYS = []
for keys in CATEGORIES.values():
    for k, _ in keys:
        ALL_KEYS.append(k)

# ─── Built-in Themes ────────────────────────────────────────────────────────

BUILTIN_THEMES = {
    "livewire": {
        "BG":"#080C12","BG_DARK":"#040810","PANEL":"#101820","WHITE":"#142030","BLACK":"#020408",
        "TEXT":"#E0F4FF","TEXT_DIM":"#4A7A90","TEXT_BLUE":"#48F7FF",
        "LIME":"#00E5FF","LIME_DK":"#00B8D4","LIME_LT":"#48F7FF",
        "BLUE_HL":"#0066FF","RED":"#FF1744","YELLOW":"#FFD600","ORANGE":"#FFAB00",
        "TOOLBAR":"#0A1018","BORDER_L":"#1A2A38","BORDER_D":"#040810","INPUT_BG":"#101820","TROUGH":"#1A2A38",
        "CARD_BG":"#121C28","CARD_BORDER":"#1A2A38","BTN_HOVER":"#1A2A38",
        "LIME_HOVER":"#00B8D4","ORANGE_HOVER":"#E09600",
        "INPUT_BORDER":"#1A2A38","INPUT_FOCUS":"#00E5FF","TAB_ACTIVE":"#00E5FF",
        "SUCCESS":"#00E676","WARNING":"#FFD600","ERROR":"#FF1744","INFO":"#48F7FF",
        "SURFACE":"#101820","SURFACE_2":"#080C12","SURFACE_3":"#040810",
        "ACCENT_START":"#00E5FF","ACCENT_END":"#0066FF",
        "CANVAS_BG":"#020408",
        "BTN_PRESSED":"#0A1218","CARD_SHADOW":"#020406","DIVIDER":"#162230","FOCUS_RING":"#00E5FF",
    },
    "light": {
        "BG":"#F0F2F5","BG_DARK":"#E4E6EA","PANEL":"#FFFFFF","WHITE":"#FFFFFF","BLACK":"#1A1A2E",
        "TEXT":"#1A1A2E","TEXT_DIM":"#4A5568","TEXT_BLUE":"#0A58CA",
        "LIME":"#27AE60","LIME_DK":"#1E8449","LIME_LT":"#82E0AA",
        "BLUE_HL":"#0D6EFD","RED":"#DC3545","YELLOW":"#E0A800","ORANGE":"#E8590C",
        "TOOLBAR":"#FFFFFF","BORDER_L":"#D0D5DD","BORDER_D":"#BFC5CF","INPUT_BG":"#FFFFFF","TROUGH":"#DEE2E6",
        "CARD_BG":"#FFFFFF","CARD_BORDER":"#D0D5DD","BTN_HOVER":"#E4E6EA",
        "LIME_HOVER":"#1E8449","ORANGE_HOVER":"#C74E0A",
        "INPUT_BORDER":"#BFC5CF","INPUT_FOCUS":"#6EA8FE","TAB_ACTIVE":"#27AE60",
        "SUCCESS":"#27AE60","WARNING":"#E0A800","ERROR":"#DC3545","INFO":"#0A85D1",
        "SURFACE":"#FFFFFF","SURFACE_2":"#F5F6F8","SURFACE_3":"#E4E6EA",
        "ACCENT_START":"#27AE60","ACCENT_END":"#17A589",
        "CANVAS_BG":"#161B22",
        "BTN_PRESSED":"#D0D5DD","CARD_SHADOW":"#C8CDD5","DIVIDER":"#E2E6EB","FOCUS_RING":"#0D6EFD",
    },
    "dark": {
        "BG":"#1A1D21","BG_DARK":"#13161A","PANEL":"#22262B","WHITE":"#2A2E33","BLACK":"#0D0F12",
        "TEXT":"#E8EAED","TEXT_DIM":"#9CA3AF","TEXT_BLUE":"#6EA8FE",
        "LIME":"#2ECC71","LIME_DK":"#27AE60","LIME_LT":"#56D384",
        "BLUE_HL":"#4A90D9","RED":"#EF4444","YELLOW":"#FBBF24","ORANGE":"#F97316",
        "TOOLBAR":"#1E2227","BORDER_L":"#343A40","BORDER_D":"#13161A","INPUT_BG":"#22262B","TROUGH":"#343A40",
        "CARD_BG":"#242930","CARD_BORDER":"#343A40","BTN_HOVER":"#2C3035",
        "LIME_HOVER":"#25A35A","ORANGE_HOVER":"#EA6C0E",
        "INPUT_BORDER":"#343A40","INPUT_FOCUS":"#4A90D9","TAB_ACTIVE":"#2ECC71",
        "SUCCESS":"#2ECC71","WARNING":"#FBBF24","ERROR":"#EF4444","INFO":"#22D3EE",
        "SURFACE":"#22262B","SURFACE_2":"#1A1D21","SURFACE_3":"#13161A",
        "ACCENT_START":"#2ECC71","ACCENT_END":"#1ABC9C",
        "CANVAS_BG":"#0D0F12",
        "BTN_PRESSED":"#1A1D21","CARD_SHADOW":"#0D0F12","DIVIDER":"#2C3035","FOCUS_RING":"#4A90D9",
    },
    "modern": {
        "BG":"#0D1117","BG_DARK":"#010409","PANEL":"#161B22","WHITE":"#21262D","BLACK":"#010409",
        "TEXT":"#F0F6FC","TEXT_DIM":"#A0ADB8","TEXT_BLUE":"#58A6FF",
        "LIME":"#3FB950","LIME_DK":"#2EA043","LIME_LT":"#56D364",
        "BLUE_HL":"#1F6FEB","RED":"#F85149","YELLOW":"#D29922","ORANGE":"#DB6D28",
        "TOOLBAR":"#161B22","BORDER_L":"#30363D","BORDER_D":"#21262D","INPUT_BG":"#0D1117","TROUGH":"#21262D",
        "CARD_BG":"#161B22","CARD_BORDER":"#30363D","BTN_HOVER":"#30363D",
        "LIME_HOVER":"#2EA043","ORANGE_HOVER":"#C05010",
        "INPUT_BORDER":"#30363D","INPUT_FOCUS":"#1F6FEB","TAB_ACTIVE":"#3FB950",
        "SUCCESS":"#3FB950","WARNING":"#D29922","ERROR":"#F85149","INFO":"#58A6FF",
        "SURFACE":"#161B22","SURFACE_2":"#0D1117","SURFACE_3":"#010409",
        "ACCENT_START":"#3FB950","ACCENT_END":"#1ABC9C",
        "CANVAS_BG":"#010409",
        "BTN_PRESSED":"#21262D","CARD_SHADOW":"#010409","DIVIDER":"#262C36","FOCUS_RING":"#1F6FEB",
    },
    "synthwave": {
        "BG":"#0C0C0C","BG_DARK":"#060606","PANEL":"#1A1A2E","WHITE":"#16213E","BLACK":"#060606",
        "TEXT":"#EF9AF2","TEXT_DIM":"#7C52A8","TEXT_BLUE":"#00BFFF",
        "LIME":"#FF2975","LIME_DK":"#D41E60","LIME_LT":"#FF6B9D",
        "BLUE_HL":"#8C1EFF","RED":"#FF1744","YELLOW":"#FF901F","ORANGE":"#F222FF",
        "TOOLBAR":"#1A1A2E","BORDER_L":"#2D2060","BORDER_D":"#0C0C0C","INPUT_BG":"#16213E","TROUGH":"#2D2060",
        "CARD_BG":"#1A1A2E","CARD_BORDER":"#2D2060","BTN_HOVER":"#2D2060",
        "LIME_HOVER":"#D41E60","ORANGE_HOVER":"#C918D4",
        "INPUT_BORDER":"#2D2060","INPUT_FOCUS":"#8C1EFF","TAB_ACTIVE":"#FF2975",
        "SUCCESS":"#FF2975","WARNING":"#FF901F","ERROR":"#FF1744","INFO":"#00BFFF",
        "SURFACE":"#1A1A2E","SURFACE_2":"#0C0C0C","SURFACE_3":"#060606",
        "ACCENT_START":"#FF2975","ACCENT_END":"#8C1EFF",
        "CANVAS_BG":"#060606",
        "BTN_PRESSED":"#190830","CARD_SHADOW":"#060606","DIVIDER":"#1C1640","FOCUS_RING":"#8C1EFF",
    },
    "dracula": {
        "BG":"#282A36","BG_DARK":"#21222C","PANEL":"#44475A","WHITE":"#44475A","BLACK":"#191A21",
        "TEXT":"#F8F8F2","TEXT_DIM":"#6272A4","TEXT_BLUE":"#8BE9FD",
        "LIME":"#FF79C6","LIME_DK":"#D962A8","LIME_LT":"#FFB2DD",
        "BLUE_HL":"#BD93F9","RED":"#FF5555","YELLOW":"#F1FA8C","ORANGE":"#FFB86C",
        "TOOLBAR":"#21222C","BORDER_L":"#44475A","BORDER_D":"#191A21","INPUT_BG":"#44475A","TROUGH":"#44475A",
        "CARD_BG":"#44475A","CARD_BORDER":"#6272A4","BTN_HOVER":"#6272A4",
        "LIME_HOVER":"#D962A8","ORANGE_HOVER":"#E89C50",
        "INPUT_BORDER":"#6272A4","INPUT_FOCUS":"#BD93F9","TAB_ACTIVE":"#FF79C6",
        "SUCCESS":"#50FA7B","WARNING":"#F1FA8C","ERROR":"#FF5555","INFO":"#8BE9FD",
        "SURFACE":"#44475A","SURFACE_2":"#282A36","SURFACE_3":"#21222C",
        "ACCENT_START":"#FF79C6","ACCENT_END":"#BD93F9",
        "CANVAS_BG":"#191A21",
        "BTN_PRESSED":"#4A4D62","CARD_SHADOW":"#191A21","DIVIDER":"#383A4A","FOCUS_RING":"#BD93F9",
    },
    "catppuccin": {
        "BG":"#1E1E2E","BG_DARK":"#181825","PANEL":"#313244","WHITE":"#313244","BLACK":"#11111B",
        "TEXT":"#CDD6F4","TEXT_DIM":"#6C7086","TEXT_BLUE":"#89DCEB",
        "LIME":"#CBA6F7","LIME_DK":"#B490E0","LIME_LT":"#DFC0FF",
        "BLUE_HL":"#89B4FA","RED":"#F38BA8","YELLOW":"#F9E2AF","ORANGE":"#FAB387",
        "TOOLBAR":"#181825","BORDER_L":"#45475A","BORDER_D":"#11111B","INPUT_BG":"#313244","TROUGH":"#45475A",
        "CARD_BG":"#313244","CARD_BORDER":"#45475A","BTN_HOVER":"#45475A",
        "LIME_HOVER":"#B490E0","ORANGE_HOVER":"#E09070",
        "INPUT_BORDER":"#45475A","INPUT_FOCUS":"#89B4FA","TAB_ACTIVE":"#CBA6F7",
        "SUCCESS":"#A6E3A1","WARNING":"#F9E2AF","ERROR":"#F38BA8","INFO":"#89DCEB",
        "SURFACE":"#313244","SURFACE_2":"#1E1E2E","SURFACE_3":"#181825",
        "ACCENT_START":"#CBA6F7","ACCENT_END":"#F5C2E7",
        "CANVAS_BG":"#11111B",
        "BTN_PRESSED":"#333548","CARD_SHADOW":"#11111B","DIVIDER":"#383A4F","FOCUS_RING":"#89B4FA",
    },
    "tokyo": {
        "BG":"#1A1B26","BG_DARK":"#16161E","PANEL":"#292E42","WHITE":"#292E42","BLACK":"#0D0E16",
        "TEXT":"#C0CAF5","TEXT_DIM":"#565F89","TEXT_BLUE":"#7DCFFF",
        "LIME":"#7AA2F7","LIME_DK":"#5D7FD4","LIME_LT":"#A0BEF9",
        "BLUE_HL":"#BB9AF7","RED":"#F7768E","YELLOW":"#E0AF68","ORANGE":"#FF9E64",
        "TOOLBAR":"#16161E","BORDER_L":"#3B4261","BORDER_D":"#0D0E16","INPUT_BG":"#292E42","TROUGH":"#3B4261",
        "CARD_BG":"#292E42","CARD_BORDER":"#3B4261","BTN_HOVER":"#3B4261",
        "LIME_HOVER":"#5D7FD4","ORANGE_HOVER":"#E0844A",
        "INPUT_BORDER":"#3B4261","INPUT_FOCUS":"#BB9AF7","TAB_ACTIVE":"#7AA2F7",
        "SUCCESS":"#9ECE6A","WARNING":"#E0AF68","ERROR":"#F7768E","INFO":"#7DCFFF",
        "SURFACE":"#292E42","SURFACE_2":"#1A1B26","SURFACE_3":"#16161E",
        "ACCENT_START":"#7AA2F7","ACCENT_END":"#BB9AF7",
        "CANVAS_BG":"#0D0E16",
        "BTN_PRESSED":"#2A3050","CARD_SHADOW":"#0D0E16","DIVIDER":"#2A2F44","FOCUS_RING":"#BB9AF7",
    },
    "spotify": {
        "BG":"#121212","BG_DARK":"#0A0A0A","PANEL":"#212121","WHITE":"#282828","BLACK":"#060606",
        "TEXT":"#FFFFFF","TEXT_DIM":"#B3B3B3","TEXT_BLUE":"#1ED760",
        "LIME":"#1DB954","LIME_DK":"#169C46","LIME_LT":"#4ADE80",
        "BLUE_HL":"#1DB954","RED":"#E91429","YELLOW":"#F59B23","ORANGE":"#E8590C",
        "TOOLBAR":"#0A0A0A","BORDER_L":"#333333","BORDER_D":"#0A0A0A","INPUT_BG":"#282828","TROUGH":"#333333",
        "CARD_BG":"#212121","CARD_BORDER":"#333333","BTN_HOVER":"#333333",
        "LIME_HOVER":"#169C46","ORANGE_HOVER":"#C74E0A",
        "INPUT_BORDER":"#333333","INPUT_FOCUS":"#1DB954","TAB_ACTIVE":"#1DB954",
        "SUCCESS":"#1DB954","WARNING":"#F59B23","ERROR":"#E91429","INFO":"#1ED760",
        "SURFACE":"#212121","SURFACE_2":"#121212","SURFACE_3":"#0A0A0A",
        "ACCENT_START":"#1DB954","ACCENT_END":"#1ED760",
        "CANVAS_BG":"#060606",
        "BTN_PRESSED":"#242424","CARD_SHADOW":"#060606","DIVIDER":"#282828","FOCUS_RING":"#1DB954",
    },
    "classic": {
        "BG":"#000000","BG_DARK":"#000000","PANEL":"#1A1A1A","WHITE":"#1A1A1A","BLACK":"#000000",
        "TEXT":"#E0E0E0","TEXT_DIM":"#999999","TEXT_BLUE":"#3CFF3C",
        "LIME":"#1EFF00","LIME_DK":"#18CC00","LIME_LT":"#5AFF3C",
        "BLUE_HL":"#32CD32","RED":"#FF3333","YELLOW":"#FFFF00","ORANGE":"#FF8C00",
        "TOOLBAR":"#0A0A0A","BORDER_L":"#2D2D2D","BORDER_D":"#000000","INPUT_BG":"#1A1A1A","TROUGH":"#2D2D2D",
        "CARD_BG":"#1A1A1A","CARD_BORDER":"#2D2D2D","BTN_HOVER":"#2D2D2D",
        "LIME_HOVER":"#18CC00","ORANGE_HOVER":"#D47200",
        "INPUT_BORDER":"#2D2D2D","INPUT_FOCUS":"#1EFF00","TAB_ACTIVE":"#1EFF00",
        "SUCCESS":"#1EFF00","WARNING":"#FFFF00","ERROR":"#FF3333","INFO":"#3CFF3C",
        "SURFACE":"#1A1A1A","SURFACE_2":"#0A0A0A","SURFACE_3":"#000000",
        "ACCENT_START":"#1EFF00","ACCENT_END":"#02E102",
        "CANVAS_BG":"#000000",
        "BTN_PRESSED":"#1A1A1A","CARD_SHADOW":"#000000","DIVIDER":"#222222","FOCUS_RING":"#1EFF00",
    },
    "nord": {
        "BG":"#2E3440","BG_DARK":"#272C36","PANEL":"#3B4252","WHITE":"#3B4252","BLACK":"#242933",
        "TEXT":"#D8DEE9","TEXT_DIM":"#4C566A","TEXT_BLUE":"#88C0D0",
        "LIME":"#88C0D0","LIME_DK":"#6EA8B8","LIME_LT":"#8FBCBB",
        "BLUE_HL":"#5E81AC","RED":"#BF616A","YELLOW":"#EBCB8B","ORANGE":"#D08770",
        "TOOLBAR":"#272C36","BORDER_L":"#434C5E","BORDER_D":"#242933","INPUT_BG":"#3B4252","TROUGH":"#434C5E",
        "CARD_BG":"#3B4252","CARD_BORDER":"#434C5E","BTN_HOVER":"#434C5E",
        "LIME_HOVER":"#6EA8B8","ORANGE_HOVER":"#B8705C",
        "INPUT_BORDER":"#434C5E","INPUT_FOCUS":"#5E81AC","TAB_ACTIVE":"#88C0D0",
        "SUCCESS":"#A3BE8C","WARNING":"#EBCB8B","ERROR":"#BF616A","INFO":"#88C0D0",
        "SURFACE":"#3B4252","SURFACE_2":"#2E3440","SURFACE_3":"#272C36",
        "ACCENT_START":"#88C0D0","ACCENT_END":"#5E81AC",
        "CANVAS_BG":"#242933",
        "BTN_PRESSED":"#353B49","CARD_SHADOW":"#242933","DIVIDER":"#3C4350","FOCUS_RING":"#5E81AC",
    },
    "gruvbox": {
        "BG":"#282828","BG_DARK":"#1D2021","PANEL":"#3C3836","WHITE":"#3C3836","BLACK":"#1D2021",
        "TEXT":"#EBDBB2","TEXT_DIM":"#665C54","TEXT_BLUE":"#83A598",
        "LIME":"#D79921","LIME_DK":"#B57B14","LIME_LT":"#FABD2F",
        "BLUE_HL":"#458588","RED":"#CC241D","YELLOW":"#FABD2F","ORANGE":"#D65D0E",
        "TOOLBAR":"#1D2021","BORDER_L":"#504945","BORDER_D":"#1D2021","INPUT_BG":"#3C3836","TROUGH":"#504945",
        "CARD_BG":"#3C3836","CARD_BORDER":"#504945","BTN_HOVER":"#504945",
        "LIME_HOVER":"#B57B14","ORANGE_HOVER":"#AF4E0D",
        "INPUT_BORDER":"#504945","INPUT_FOCUS":"#458588","TAB_ACTIVE":"#D79921",
        "SUCCESS":"#98971A","WARNING":"#FABD2F","ERROR":"#CC241D","INFO":"#83A598",
        "SURFACE":"#3C3836","SURFACE_2":"#282828","SURFACE_3":"#1D2021",
        "ACCENT_START":"#D79921","ACCENT_END":"#D65D0E",
        "CANVAS_BG":"#1D2021",
        "BTN_PRESSED":"#3A3530","CARD_SHADOW":"#1D2021","DIVIDER":"#3C3732","FOCUS_RING":"#458588",
    },
    "highcontrast": {
        "BG":"#000000","BG_DARK":"#000000","PANEL":"#0A0A0A","WHITE":"#FFFFFF","BLACK":"#000000",
        "TEXT":"#FFFFFF","TEXT_DIM":"#E0E0E0","TEXT_BLUE":"#00CCFF",
        "LIME":"#00FF00","LIME_DK":"#00CC00","LIME_LT":"#66FF66",
        "BLUE_HL":"#0088FF","RED":"#FF0000","YELLOW":"#FFFF00","ORANGE":"#FF8800",
        "TOOLBAR":"#111111","BORDER_L":"#FFFFFF","BORDER_D":"#FFFFFF","INPUT_BG":"#111111","TROUGH":"#333333",
        "CARD_BG":"#111111","CARD_BORDER":"#FFFFFF","BTN_HOVER":"#333333",
        "LIME_HOVER":"#00AA00","ORANGE_HOVER":"#CC6600",
        "INPUT_BORDER":"#FFFFFF","INPUT_FOCUS":"#00FF00","TAB_ACTIVE":"#00FF00",
        "SUCCESS":"#00FF00","WARNING":"#FFFF00","ERROR":"#FF0000","INFO":"#00CCFF",
        "SURFACE":"#111111","SURFACE_2":"#000000","SURFACE_3":"#000000",
        "ACCENT_START":"#00FF00","ACCENT_END":"#00CCFF",
        "CANVAS_BG":"#000000",
        "BTN_PRESSED":"#222222","CARD_SHADOW":"#000000","DIVIDER":"#444444","FOCUS_RING":"#FFFF00",
    },
}

THEME_NAMES = list(BUILTIN_THEMES.keys())


# ─── Helper ──────────────────────────────────────────────────────────────────

def _lerp_color(c1, c2, t):
    """Linear interpolate between two hex colors."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _contrast_text(hex_color):
    """Return black or white text depending on background luminance."""
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if lum > 140 else "#FFFFFF"


# ─── Main Application ────────────────────────────────────────────────────────

class SkinCustomizer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LimeWire Skin Customizer")
        self.geometry("1280x820")
        self.minsize(1000, 700)
        self.configure(bg="#1A1D21")

        # Current color values
        self.colors = dict(BUILTIN_THEMES["livewire"])
        self.swatch_widgets = {}  # key -> (frame, label, entry)
        self._modified = False

        self._build_ui()
        self._refresh_preview()

    # ── UI Construction ──────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self, bg="#13161A", height=50)
        toolbar.pack(fill="x", side="top")
        toolbar.pack_propagate(False)

        tk.Label(toolbar, text="LimeWire Skin Customizer", font=("Segoe UI Semibold", 14),
                 bg="#13161A", fg="#00E5FF").pack(side="left", padx=12)

        # Theme name
        tk.Label(toolbar, text="Theme Name:", font=("Segoe UI", 10),
                 bg="#13161A", fg="#E0F4FF").pack(side="left", padx=(20, 4))
        self.name_var = tk.StringVar(value="my_custom_theme")
        name_entry = tk.Entry(toolbar, textvariable=self.name_var, width=20,
                              font=("Segoe UI", 10), bg="#101820", fg="#E0F4FF",
                              insertbackground="#00E5FF", relief="flat", bd=0,
                              highlightthickness=1, highlightcolor="#00E5FF",
                              highlightbackground="#1A2A38")
        name_entry.pack(side="left", padx=4, ipady=3)

        # Base theme selector
        tk.Label(toolbar, text="Base:", font=("Segoe UI", 10),
                 bg="#13161A", fg="#E0F4FF").pack(side="left", padx=(20, 4))
        self.base_var = tk.StringVar(value="livewire")
        base_combo = ttk.Combobox(toolbar, textvariable=self.base_var,
                                  values=THEME_NAMES, state="readonly", width=14)
        base_combo.pack(side="left", padx=4)
        base_combo.bind("<<ComboboxSelected>>", self._on_base_change)

        # Buttons
        btn_style = {"font": ("Segoe UI Semibold", 9), "relief": "flat", "bd": 0,
                     "cursor": "hand2", "padx": 12, "pady": 4}

        save_btn = tk.Button(toolbar, text="Save Theme JSON", bg="#00E5FF", fg="#080C12",
                             activebackground="#00B8D4", command=self._save_theme, **btn_style)
        save_btn.pack(side="right", padx=8)

        load_btn = tk.Button(toolbar, text="Load JSON", bg="#1A2A38", fg="#E0F4FF",
                             activebackground="#2A3A48", command=self._load_theme, **btn_style)
        load_btn.pack(side="right", padx=4)

        reset_btn = tk.Button(toolbar, text="Reset to Base", bg="#1A2A38", fg="#E0F4FF",
                              activebackground="#2A3A48", command=self._reset_to_base, **btn_style)
        reset_btn.pack(side="right", padx=4)

        # Main content: left editor + right preview
        content = tk.PanedWindow(self, orient="horizontal", bg="#1A1D21",
                                 sashwidth=4, sashrelief="flat")
        content.pack(fill="both", expand=True, padx=0, pady=0)

        # Left: color editor (scrollable)
        left_frame = tk.Frame(content, bg="#1A1D21")
        content.add(left_frame, width=620, minsize=400)

        self._build_editor(left_frame)

        # Right: live preview
        right_frame = tk.Frame(content, bg="#1A1D21")
        content.add(right_frame, width=660, minsize=400)

        self._build_preview(right_frame)

    def _build_editor(self, parent):
        """Build the scrollable color editor panel."""
        # Canvas + scrollbar for scrolling
        canvas = tk.Canvas(parent, bg="#1A1D21", highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.editor_frame = tk.Frame(canvas, bg="#1A1D21")

        self.editor_frame.bind("<Configure>",
                               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.editor_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Mousewheel scrolling
        def _on_mousewheel(e):
            canvas.yview_scroll(-1 * (e.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Build category sections
        for cat_name, keys in CATEGORIES.items():
            # Category header
            header = tk.Frame(self.editor_frame, bg="#101820")
            header.pack(fill="x", padx=8, pady=(12, 2))
            tk.Label(header, text=cat_name, font=("Segoe UI Semibold", 11),
                     bg="#101820", fg="#00E5FF").pack(side="left", padx=8, pady=4)

            # Color rows
            for key, desc in keys:
                self._build_color_row(self.editor_frame, key, desc)

    def _build_color_row(self, parent, key, desc):
        """Build a single color editor row: swatch + key name + hex entry."""
        row = tk.Frame(parent, bg="#1A1D21")
        row.pack(fill="x", padx=12, pady=1)

        # Clickable color swatch
        color = self.colors.get(key, "#000000")
        swatch = tk.Frame(row, bg=color, width=28, height=28, cursor="hand2",
                          highlightthickness=1, highlightbackground="#343A40")
        swatch.pack(side="left", padx=(0, 8), pady=2)
        swatch.pack_propagate(False)
        swatch.bind("<Button-1>", lambda e, k=key: self._pick_color(k))

        # Key name + description
        info = tk.Frame(row, bg="#1A1D21")
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=key, font=("Cascadia Code", 9), bg="#1A1D21",
                 fg="#E0F4FF", anchor="w").pack(side="left")
        tk.Label(info, text=f"  {desc}", font=("Segoe UI", 8), bg="#1A1D21",
                 fg="#4A7A90", anchor="w").pack(side="left")

        # Hex entry
        var = tk.StringVar(value=color)
        entry = tk.Entry(row, textvariable=var, width=9, font=("Cascadia Code", 9),
                         bg="#101820", fg="#E0F4FF", insertbackground="#00E5FF",
                         relief="flat", bd=0, highlightthickness=1,
                         highlightcolor="#00E5FF", highlightbackground="#1A2A38")
        entry.pack(side="right", padx=4, ipady=2)
        entry.bind("<Return>", lambda e, k=key, v=var: self._on_hex_enter(k, v))
        entry.bind("<FocusOut>", lambda e, k=key, v=var: self._on_hex_enter(k, v))

        self.swatch_widgets[key] = (swatch, var, entry)

    def _build_preview(self, parent):
        """Build the live preview panel showing sample UI elements."""
        self.preview_canvas = tk.Canvas(parent, bg="#080C12", highlightthickness=0, bd=0)
        self.preview_canvas.pack(fill="both", expand=True, padx=4, pady=4)

    # ── Color Editing ────────────────────────────────────────────────────

    def _pick_color(self, key):
        """Open system color chooser for a key."""
        current = self.colors.get(key, "#000000")
        result = colorchooser.askcolor(color=current, title=f"Pick color for {key}")
        if result and result[1]:
            hex_color = result[1].upper()
            if len(hex_color) == 4:  # #RGB -> #RRGGBB
                hex_color = f"#{hex_color[1]*2}{hex_color[2]*2}{hex_color[3]*2}"
            self.colors[key] = hex_color
            self._update_swatch(key)
            self._refresh_preview()
            self._modified = True

    def _on_hex_enter(self, key, var):
        """Update color from hex entry."""
        val = var.get().strip()
        if not val.startswith("#"):
            val = "#" + val
        if len(val) == 4:
            val = f"#{val[1]*2}{val[2]*2}{val[3]*2}"
        if len(val) == 7:
            try:
                int(val[1:], 16)
                self.colors[key] = val.upper()
                self._update_swatch(key)
                self._refresh_preview()
                self._modified = True
                return
            except ValueError:
                pass
        var.set(self.colors.get(key, "#000000"))

    def _update_swatch(self, key):
        """Update the swatch color and entry text for a key."""
        if key in self.swatch_widgets:
            swatch, var, entry = self.swatch_widgets[key]
            color = self.colors[key]
            swatch.configure(bg=color)
            var.set(color)

    def _update_all_swatches(self):
        """Refresh all swatches from self.colors."""
        for key in self.swatch_widgets:
            self._update_swatch(key)

    # ── Preview Rendering ────────────────────────────────────────────────

    def _refresh_preview(self):
        """Redraw the live preview panel."""
        c = self.preview_canvas
        c.delete("all")
        c.update_idletasks()
        w = max(c.winfo_width(), 400)
        h = max(c.winfo_height(), 600)

        C = self.colors  # shorthand
        c.configure(bg=C["BG"])

        pad = 16
        y = pad

        # ── Gradient header bar ──
        bar_h = 50
        steps = 60
        for i in range(steps):
            t = i / max(steps - 1, 1)
            col = _lerp_color(C["ACCENT_START"], C["ACCENT_END"], t)
            x0 = pad + int(t * (w - 2 * pad))
            x1 = pad + int((t + 1 / steps) * (w - 2 * pad)) + 1
            c.create_rectangle(x0, y, x1, y + bar_h, fill=col, outline="")
        c.create_text(pad + 16, y + bar_h // 2, text="LimeWire Studio Edition",
                      font=("Segoe UI Semibold", 16), fill="#FFFFFF", anchor="w")
        c.create_text(w - pad - 16, y + bar_h // 2, text="v2.0.2",
                      font=("Segoe UI", 10), fill="#FFFFFFBB", anchor="e")
        y += bar_h + 12

        # ── Toolbar ──
        c.create_rectangle(pad, y, w - pad, y + 36, fill=C["TOOLBAR"], outline=C["BORDER_L"])
        tabs = ["Search", "Player", "Analyze", "Stems", "Effects", "Editor"]
        tx = pad + 12
        for i, tab in enumerate(tabs):
            is_active = (i == 0)
            fg = C["TAB_ACTIVE"] if is_active else C["TEXT_DIM"]
            c.create_text(tx, y + 18, text=tab, font=("Segoe UI Semibold", 9),
                          fill=fg, anchor="w")
            tw = len(tab) * 7 + 16
            if is_active:
                c.create_rectangle(tx - 4, y + 32, tx + tw - 12, y + 36,
                                   fill=C["TAB_ACTIVE"], outline="")
            tx += tw + 4
        y += 48

        # ── Card: Input section ──
        card_h = 130
        c.create_rectangle(pad, y, w - pad, y + card_h,
                           fill=C["CARD_BG"], outline=C["CARD_BORDER"])
        # Accent stripe
        c.create_rectangle(pad, y, pad + 3, y + card_h, fill=C["LIME"], outline="")

        cy = y + 14
        c.create_text(pad + 16, cy, text="Search & Grab", font=("Segoe UI Semibold", 12),
                      fill=C["TEXT"], anchor="w")
        cy += 24
        c.create_text(pad + 16, cy, text="Paste a URL to download audio in any format",
                      font=("Segoe UI", 9), fill=C["TEXT_DIM"], anchor="w")
        cy += 28

        # Input field
        inp_w = w - 2 * pad - 140
        c.create_rectangle(pad + 16, cy, pad + 16 + inp_w, cy + 30,
                           fill=C["INPUT_BG"], outline=C["INPUT_BORDER"])
        c.create_text(pad + 24, cy + 15, text="https://youtube.com/watch?v=...",
                      font=("Segoe UI", 9), fill=C["TEXT_DIM"], anchor="w")

        # Download button
        bx = pad + 16 + inp_w + 12
        c.create_rectangle(bx, cy, w - pad - 16, cy + 30,
                           fill=C["LIME"], outline="")
        c.create_text((bx + w - pad - 16) // 2, cy + 15, text="Download",
                      font=("Segoe UI Semibold", 9),
                      fill=_contrast_text(C["LIME"]), anchor="center")
        y += card_h + 12

        # ── Card: Analysis results ──
        card_h = 120
        c.create_rectangle(pad, y, w - pad, y + card_h,
                           fill=C["CARD_BG"], outline=C["CARD_BORDER"])
        c.create_rectangle(pad, y, pad + 3, y + card_h, fill=C["BLUE_HL"], outline="")

        cy = y + 14
        c.create_text(pad + 16, cy, text="Analysis Results",
                      font=("Segoe UI Semibold", 12), fill=C["TEXT"], anchor="w")
        cy += 28

        # Metric badges
        metrics = [
            ("128 BPM", C["LIME"]),
            ("A Minor", C["BLUE_HL"]),
            ("5A Camelot", C["ORANGE"]),
            ("-14.2 LUFS", C["YELLOW"]),
        ]
        mx = pad + 16
        for label, color in metrics:
            tw = len(label) * 7 + 20
            c.create_rectangle(mx, cy, mx + tw, cy + 26, fill=color, outline="")
            c.create_text(mx + tw // 2, cy + 13, text=label,
                          font=("Segoe UI Semibold", 9),
                          fill=_contrast_text(color), anchor="center")
            mx += tw + 8

        cy += 38
        c.create_text(pad + 16, cy, text="Identified: Artist - Track Name",
                      font=("Segoe UI", 9), fill=C["TEXT_BLUE"], anchor="w")
        y += card_h + 12

        # ── Status messages ──
        statuses = [
            ("Download complete", C["SUCCESS"], "SUCCESS"),
            ("Low bitrate detected", C["WARNING"], "WARNING"),
            ("Connection failed", C["ERROR"], "ERROR"),
            ("Analyzing BPM...", C["INFO"], "INFO"),
        ]
        for msg, color, label in statuses:
            c.create_rectangle(pad, y, w - pad, y + 28,
                               fill=_lerp_color(C["BG"], color, 0.15), outline="")
            c.create_rectangle(pad, y, pad + 3, y + 28, fill=color, outline="")
            c.create_text(pad + 14, y + 14, text=f"{label}: {msg}",
                          font=("Segoe UI", 9), fill=color, anchor="w")
            y += 32

        y += 8

        # ── Surface elevation demo ──
        sx = pad
        for i, (surf, label) in enumerate([
            (C["SURFACE_3"], "Surface 3"),
            (C["SURFACE_2"], "Surface 2"),
            (C["SURFACE"], "Surface 1"),
            (C["PANEL"], "Panel"),
        ]):
            sw = (w - 2 * pad - 36) // 4
            c.create_rectangle(sx, y, sx + sw, y + 50, fill=surf,
                               outline=C["BORDER_L"])
            c.create_text(sx + sw // 2, y + 25, text=label,
                          font=("Segoe UI", 8), fill=C["TEXT_DIM"], anchor="center")
            sx += sw + 12
        y += 62

        # ── Button row ──
        buttons = [
            ("Primary", C["LIME"], _contrast_text(C["LIME"])),
            ("Secondary", C["BTN_HOVER"], C["TEXT"]),
            ("Danger", C["RED"], "#FFFFFF"),
            ("Info", C["BLUE_HL"], "#FFFFFF"),
            ("Orange", C["ORANGE"], _contrast_text(C["ORANGE"])),
        ]
        bx = pad
        for label, bg, fg in buttons:
            bw = (w - 2 * pad - 48) // 5
            c.create_rectangle(bx, y, bx + bw, y + 32, fill=bg, outline="")
            c.create_text(bx + bw // 2, y + 16, text=label,
                          font=("Segoe UI Semibold", 9), fill=fg, anchor="center")
            bx += bw + 12
        y += 44

        # ── Canvas BG demo (waveform area) ──
        c.create_rectangle(pad, y, w - pad, y + 60,
                           fill=C["CANVAS_BG"], outline=C["BORDER_D"])
        c.create_text(pad + 16, y + 12, text="Waveform Canvas",
                      font=("Segoe UI", 8), fill=C["TEXT_DIM"], anchor="w")
        # Draw fake waveform
        import math
        for i in range(0, w - 2 * pad - 32, 3):
            amp = 18 * abs(math.sin(i * 0.04)) * (0.5 + 0.5 * math.sin(i * 0.01))
            wx = pad + 16 + i
            wy = y + 38
            c.create_line(wx, wy - amp, wx, wy + amp, fill=C["LIME"], width=1.5)
        y += 72

        # ── Focus ring + divider ──
        c.create_rectangle(pad, y, w - pad, y + 1, fill=C["DIVIDER"], outline="")
        y += 12
        c.create_rectangle(pad, y, pad + 200, y + 30,
                           fill=C["INPUT_BG"], outline=C["FOCUS_RING"], width=2)
        c.create_text(pad + 10, y + 15, text="Focused input",
                      font=("Segoe UI", 9), fill=C["TEXT"], anchor="w")

    # ── Actions ──────────────────────────────────────────────────────────

    def _on_base_change(self, event=None):
        """Load a built-in theme as the base."""
        name = self.base_var.get()
        if name in BUILTIN_THEMES:
            self.colors = dict(BUILTIN_THEMES[name])
            self._update_all_swatches()
            self._refresh_preview()
            self._modified = True

    def _reset_to_base(self):
        """Reset all colors to the selected base theme."""
        self._on_base_change()

    def _save_theme(self):
        """Export the current theme as a JSON file."""
        name = self.name_var.get().strip().lower().replace(" ", "_")
        if not name:
            name = "custom_theme"

        default_dir = os.path.expanduser("~")
        f = filedialog.asksaveasfilename(
            initialdir=default_dir,
            initialfile=f"{name}.json",
            defaultextension=".json",
            filetypes=[("Theme JSON", "*.json"), ("All", "*.*")],
            title="Save LimeWire Theme"
        )
        if not f:
            return

        # Build the theme dict (only the 37 color keys)
        theme = {}
        for key in ALL_KEYS:
            theme[key] = self.colors.get(key, "#000000")

        try:
            with open(f, "w", encoding="utf-8") as fp:
                json.dump(theme, fp, indent=2)
            self._modified = False
            messagebox.showinfo("Saved",
                                f"Theme saved to:\n{f}\n\n"
                                f"Load it in LimeWire via:\n"
                                f"Tools > Load Community Theme")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def _load_theme(self):
        """Import a theme JSON file."""
        f = filedialog.askopenfilename(
            filetypes=[("Theme JSON", "*.json"), ("All", "*.*")],
            title="Load Theme JSON"
        )
        if not f:
            return

        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            if not isinstance(data, dict) or "BG" not in data:
                messagebox.showerror("Invalid", "Not a valid LimeWire theme file.\n"
                                     "Must contain BG, TEXT, LIME, etc. keys.")
                return

            # Fill missing keys from current base
            base = BUILTIN_THEMES.get(self.base_var.get(), BUILTIN_THEMES["dark"])
            for k, v in base.items():
                if k not in data:
                    data[k] = v

            self.colors = {k: data.get(k, "#000000") for k in ALL_KEYS}

            # Set name from filename
            name = os.path.splitext(os.path.basename(f))[0]
            self.name_var.set(name)

            self._update_all_swatches()
            self._refresh_preview()
            self._modified = True

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")


def main():
    app = SkinCustomizer()
    app.mainloop()


if __name__ == "__main__":
    main()
