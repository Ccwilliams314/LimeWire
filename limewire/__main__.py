"""python -m limewire  — launch LimeWire Studio Edition."""

import os
import sys
import time

from limewire.core.theme import apply_theme


def _run_screenshots():
    """Capture all 20 tabs to screenshots/ directory."""
    from PIL import ImageGrab
    from limewire.app import App

    app = App()
    # Anonymize: clear personal data before capturing
    app.history = []
    app.schedule = []
    anon_dir = os.path.join("C:\\", "LimeWire", "Downloads")
    app.output_dir = anon_dir
    for page in app.pages.values():
        if hasattr(page, "file_var"):
            page.file_var.set("")
        if hasattr(page, "url_var"):
            page.url_var.set("")
        for attr in ("folder_var", "folder", "pl_folder", "out_f", "sc_f", "_out_var"):
            if hasattr(page, attr):
                getattr(page, attr).set(anon_dir)
        if hasattr(page, "out_var"):
            page.out_var.set(os.path.join(anon_dir, "Stems"))
        if hasattr(page, "out_dir_var"):
            page.out_dir_var.set(os.path.join(anon_dir, "Batch"))
    # Force LiveWire theme
    apply_theme("livewire")
    app.settings["theme"] = "livewire"
    sp = app.pages.get("settings")
    if sp and hasattr(sp, "_theme_combo"):
        sp._theme_combo.set("LiveWire")
    pp = app.pages.get("player")
    if pp:
        pp._playlist = []
        pp._playlist_set = set()
        try:
            pp.plb.delete(0, "end")
        except Exception:
            pass
    hp = app.pages.get("history")
    if hp:
        try:
            hp.tree.delete(*hp.tree.get_children())
        except Exception:
            pass
    # Force a fixed window size so screenshots don't include the OS taskbar
    app.state("normal")
    app.geometry("960x820+50+30")
    app.update_idletasks()
    app.update()
    time.sleep(1.5)
    tabs = [
        ("search", "01_search"), ("download", "02_download"),
        ("playlist", "03_playlist"), ("converter", "04_converter"),
        ("player", "05_player"), ("analyze", "06_analyze"),
        ("stems", "07_stems"), ("effects", "08_effects"),
        ("discovery", "09_discovery"), ("samples", "10_samples"),
        ("editor", "11_editor"), ("recorder", "12_recorder"),
        ("spectrogram", "13_spectrogram"), ("pitchtime", "14_pitchtime"),
        ("remixer", "15_remixer"), ("batch", "16_batch"),
        ("schedule", "17_schedule"), ("history", "18_history"),
        ("coverart", "19_coverart"), ("settings", "20_settings"),
    ]
    ss_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
    os.makedirs(ss_dir, exist_ok=True)
    for key, fname in tabs:
        app._show_tab(key)
        app.update_idletasks()
        app.update()
        time.sleep(0.4)
        x, y_ = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        img = ImageGrab.grab(bbox=(x, y_, x + w, y_ + h))
        out = os.path.join(ss_dir, f"{fname}.png")
        img.save(out)
        print(f"  Saved {fname}.png ({w}x{h})")
    print(f"Done — {len(tabs)} screenshots in {ss_dir}")
    app.destroy()
    sys.exit(0)


def main():
    if "--screenshots" in sys.argv:
        _run_screenshots()
        return

    from tkinter import messagebox
    from limewire.app import App

    try:
        app = App()
        app.mainloop()
    except Exception as e:
        import traceback
        crash_log = os.path.join(os.path.expanduser("~"), ".limewire_crash.log")
        try:
            with open(crash_log, "w") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        try:
            messagebox.showerror(
                "LimeWire Error",
                f"LimeWire encountered an error:\n{str(e)[:200]}\n\n"
                f"Details saved to:\n{crash_log}"
            )
        except Exception:
            print(f"ERROR: {e}\nCrash log: {crash_log}")


if __name__ == "__main__":
    main()
