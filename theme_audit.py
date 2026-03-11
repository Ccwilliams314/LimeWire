"""Capture one representative page across all themes + the 4 missing pages."""
import os, sys, time
from PIL import ImageGrab

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from limewire.core.theme import THEMES, THEME_DARK, apply_theme
from limewire.app import App
from limewire.ui.styles import init_limewire_styles

app = App()
app.state("normal")
app.geometry("960x820+50+30")
app.update_idletasks(); app.update(); time.sleep(1.5)

ss_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots", "audit")
os.makedirs(ss_dir, exist_ok=True)

def snap(name):
    app.update_idletasks(); app.update(); time.sleep(0.3)
    x, y_ = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    img = ImageGrab.grab(bbox=(x, y_, x + w, y_ + h))
    out = os.path.join(ss_dir, f"{name}.png")
    img.save(out)
    print(f"  {name}.png")

def switch_theme(new_name):
    cur = app.settings.get("theme", "livewire")
    old = THEMES.get(cur, THEME_DARK)
    apply_theme(new_name)
    new = THEMES.get(new_name, THEME_DARK)
    app.settings["theme"] = new_name
    cmap = {}
    for k, v in old.items():
        if isinstance(v, str) and v.startswith("#"):
            nv = new.get(k, v)
            if isinstance(nv, str):
                cmap[v.lower()] = nv.lower()
    init_limewire_styles(app)
    app._reconfig_all(app, cmap)
    if hasattr(app, "_logo_bar"):
        app._logo_bar.event_generate("<Configure>")

# 1) Capture the 4 missing pages on LiveWire
for key in ["lyrics", "visualizer", "library", "dj"]:
    app._show_tab(key)
    snap(f"page_{key}")

# 2) Capture Search page across all themes
theme_names = sorted(THEMES.keys())
for tname in theme_names:
    switch_theme(tname)
    app._show_tab("search")
    snap(f"theme_{tname}")

# 3) Capture a few pages on dark/synthwave/spotify to check contrast
for tname in ["dark", "synthwave", "spotify"]:
    switch_theme(tname)
    for page in ["player", "editor", "settings"]:
        app._show_tab(page)
        snap(f"{tname}_{page}")

print(f"\nDone — files in {ss_dir}")
app.destroy()
