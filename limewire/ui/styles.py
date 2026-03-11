"""TTK style initialization for LimeWire."""
from tkinter import ttk

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import S, SCROLLBAR_WIDTH, TREEVIEW_ROW_HEIGHT


def init_limewire_styles(root):
    """Configure all ttk widget styles to match current theme."""
    s = ttk.Style(root)
    s.theme_use("clam")

    # Combobox
    s.configure("TCombobox",
                fieldbackground=T.INPUT_BG, background=T.SURFACE_2,
                foreground=T.TEXT, arrowcolor=T.TEXT_DIM,
                selectbackground=T.BLUE_HL, selectforeground="#FFFFFF",
                bordercolor=T.INPUT_BORDER, borderwidth=1,
                relief="flat", padding=[S(10), S(7)])
    s.map("TCombobox",
          bordercolor=[("focus", T.INPUT_FOCUS)],
          lightcolor=[("focus", T.INPUT_FOCUS)],
          darkcolor=[("focus", T.INPUT_FOCUS)],
          fieldbackground=[("readonly", T.INPUT_BG)],
          foreground=[("readonly", T.TEXT)])
    root.option_add("*TCombobox*Listbox.background", T.INPUT_BG)
    root.option_add("*TCombobox*Listbox.foreground", T.TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", T.BLUE_HL)
    root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
    root.option_add("*TCombobox*Listbox.font", T.F_BODY)

    # Spinbox
    root.option_add("*Spinbox.background", T.INPUT_BG)
    root.option_add("*Spinbox.foreground", T.TEXT)
    root.option_add("*Spinbox.buttonBackground", T.BG)
    root.option_add("*Spinbox.insertBackground", T.LIME)
    root.option_add("*Spinbox.selectBackground", T.BLUE_HL)
    root.option_add("*Spinbox.selectForeground", "#FFFFFF")

    # Progress bars
    s.configure("Lime.Horizontal.TProgressbar",
                troughcolor=T.SURFACE_2, background=T.LIME,
                bordercolor=T.SURFACE_2, lightcolor=T.LIME_LT,
                darkcolor=T.LIME_DK, thickness=S(8), borderwidth=0)
    s.configure("Thin.Horizontal.TProgressbar",
                troughcolor=T.SURFACE_2, background=T.LIME,
                bordercolor=T.SURFACE_2, lightcolor=T.LIME_LT,
                darkcolor=T.LIME_DK, thickness=4, borderwidth=0)

    # Scale
    s.configure("TScale", background=T.BG, troughcolor=T.TROUGH,
                sliderlength=S(18), sliderrelief="flat", borderwidth=0)

    # Scrollbar
    s.configure("TScrollbar",
                background=_lerp_color(T.BORDER_L, T.BG, 0.3),
                troughcolor=T.SURFACE_3, bordercolor=T.SURFACE_3,
                arrowcolor=T.TEXT_DIM, relief="flat", borderwidth=0, width=S(SCROLLBAR_WIDTH))
    s.map("TScrollbar",
          background=[("active", T.BORDER_L), ("pressed", T.TEXT_DIM)])
    s.configure("Vertical.TScrollbar",
                background=_lerp_color(T.BORDER_L, T.BG, 0.3),
                troughcolor=T.SURFACE_3, width=S(SCROLLBAR_WIDTH))
    s.map("Vertical.TScrollbar",
          background=[("active", T.BORDER_L), ("pressed", T.TEXT_DIM)])

    # Notebook — completely hide the tab bar (icon toolbar is the navigation)
    s.configure("TNotebook", background=T.BG, borderwidth=0,
                tabmargins=[0, 0, 0, 0])
    s.layout("TNotebook", [("TNotebook.client", {"sticky": "nswe"})])
    s.configure("TNotebook.Tab",
                background=T.BG, foreground=T.BG, padding=[0, 0],
                width=0, font=("Segoe UI", 1), borderwidth=0)

    # Settings notebook — visible tabs for internal settings sections
    s.configure("Settings.TNotebook", background=T.BG, borderwidth=0)
    s.configure("Settings.TNotebook.Tab",
                background=T.SURFACE_2, foreground=T.TEXT,
                padding=[12, 6], font=T.F_BODY, borderwidth=0)
    s.map("Settings.TNotebook.Tab",
          background=[("selected", T.CARD_BG), ("!selected", T.SURFACE_2)],
          foreground=[("selected", T.LIME), ("!selected", T.TEXT_DIM)])

    # Treeview
    s.configure("Treeview",
                background=T.INPUT_BG, foreground=T.TEXT,
                fieldbackground=T.INPUT_BG, borderwidth=0,
                font=T.F_BODY, rowheight=S(TREEVIEW_ROW_HEIGHT), relief="flat")
    s.configure("Treeview.Heading",
                background=T.SURFACE_2, foreground=T.TEXT,
                font=T.F_BOLD, borderwidth=0, relief="flat",
                padding=[S(10), S(6)])
    s.map("Treeview",
          background=[("selected", T.BLUE_HL)],
          foreground=[("selected", "#FFFFFF")])
    s.map("Treeview.Heading",
          background=[("active", T.BTN_HOVER)])
