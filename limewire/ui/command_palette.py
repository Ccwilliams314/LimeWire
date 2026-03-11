"""Command palette & shortcut registry — Ctrl+K global search."""
import os
import tkinter as tk

from limewire.core.theme import T
from limewire.core.constants import SP_XS, SP_SM, SP_MD, SP_LG
from limewire.ui.widgets import ClassicBtn, LimeBtn, OrangeBtn
from limewire.ui.toast import show_toast


class ShortcutRegistry:
    """Central registry of keyboard shortcuts with help display and customization."""

    def __init__(self):
        self._shortcuts = []    # [(combo, desc, callback, action_id), ...]
        self._custom_bindings = {}  # action_id → custom combo (from settings)

    def register(self, combo, desc, callback, action_id=None):
        aid = action_id or desc.lower().replace(" ", "_")
        effective = self._custom_bindings.get(aid, combo)
        self._shortcuts.append((effective, desc, callback, aid))

    def load_custom(self, bindings_dict):
        """Load custom keybindings from settings."""
        if bindings_dict:
            self._custom_bindings = dict(bindings_dict)

    def get_combo(self, action_id):
        for combo, desc, cb, aid in self._shortcuts:
            if aid == action_id:
                return combo
        return None

    def all(self):
        return [(c, d, cb) for c, d, cb, _ in self._shortcuts]

    def show_help(self, parent):
        w = tk.Toplevel(parent)
        w.title("Keyboard Shortcuts")
        w.geometry("400x420")
        w.configure(bg=T.BG)
        w.transient(parent)
        w.grab_set()
        tk.Label(w, text="Keyboard Shortcuts", font=T.F_H3,
                 bg=T.BG, fg=T.TEXT).pack(pady=(SP_LG, SP_SM))
        f = tk.Frame(w, bg=T.BG)
        f.pack(fill="both", expand=True, padx=SP_LG, pady=SP_SM)
        for combo, desc, _, _ in self._shortcuts:
            row = tk.Frame(f, bg=T.BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=combo, font=T.F_MONO, bg=T.SURFACE_2,
                     fg=T.LIME, padx=SP_SM, pady=2).pack(side="left")
            tk.Label(row, text=desc, font=T.F_BODY, bg=T.BG,
                     fg=T.TEXT).pack(side="left", padx=(SP_SM, 0))
        br = tk.Frame(w, bg=T.BG)
        br.pack(pady=SP_MD)
        ClassicBtn(br, "Customize...",
                   lambda: [w.destroy(),
                            self.show_customize(parent)]).pack(
                       side="left", padx=(0, 8))
        ClassicBtn(br, "Close", w.destroy).pack(side="left")

    def show_customize(self, parent):
        """Show shortcut customization dialog."""
        dlg = tk.Toplevel(parent)
        dlg.title("Customize Shortcuts")
        dlg.geometry("520x500")
        dlg.configure(bg=T.BG)
        dlg.transient(parent)
        dlg.grab_set()
        tk.Label(dlg, text="Customize Keyboard Shortcuts", font=T.F_H3,
                 bg=T.BG, fg=T.TEXT).pack(pady=(SP_LG, SP_SM))
        tk.Label(dlg, text="Click a shortcut to rebind it. Press Escape to cancel.",
                 font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM).pack()
        sf = tk.Frame(dlg, bg=T.BG)
        sf.pack(fill="both", expand=True, padx=SP_LG, pady=SP_SM)
        cv = tk.Canvas(sf, bg=T.BG, highlightthickness=0)
        vsb = tk.Scrollbar(sf, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=T.BG)
        cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: cv.configure(scrollregion=cv.bbox("all")))
        entries = {}
        for combo, desc, cb, aid in self._shortcuts:
            row = tk.Frame(inner, bg=T.BG)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=desc, font=T.F_BODY, bg=T.BG, fg=T.TEXT,
                     width=25, anchor="w").pack(side="left")
            var = tk.StringVar(value=combo)
            ent = tk.Entry(row, textvariable=var, font=T.F_MONO,
                           bg=T.INPUT_BG, fg=T.LIME, width=18,
                           relief="flat", bd=0, insertbackground=T.TEXT,
                           highlightthickness=2,
                           highlightbackground=T.INPUT_BORDER,
                           highlightcolor=T.INPUT_FOCUS)
            ent.pack(side="left", padx=SP_SM)
            entries[aid] = var

            def _capture(e, entry=ent, v=var):
                parts = []
                if e.state & 0x4:
                    parts.append("Ctrl")
                if e.state & 0x8:
                    parts.append("Alt")
                if e.state & 0x1:
                    parts.append("Shift")
                key = e.keysym
                if key in ("Control_L", "Control_R", "Alt_L", "Alt_R",
                           "Shift_L", "Shift_R"):
                    return
                if key == "Escape":
                    entry.selection_clear()
                    return
                parts.append(key.capitalize() if len(key) == 1 else key)
                v.set("+".join(parts))
                entry.selection_clear()
                dlg.focus_set()
                return "break"

            ent.bind("<KeyPress>", _capture)

        def _save():
            new_binds = {}
            for aid, var in entries.items():
                new_binds[aid] = var.get()
            self._custom_bindings = new_binds
            if hasattr(parent, "settings"):
                parent.settings["custom_shortcuts"] = new_binds
                parent._save_settings()
            if hasattr(parent, "_rebind_shortcuts"):
                parent._rebind_shortcuts()
            show_toast(parent, "Shortcuts saved — restart for full effect",
                       "info")
            dlg.destroy()

        def _reset():
            self._custom_bindings = {}
            if hasattr(parent, "settings"):
                parent.settings.pop("custom_shortcuts", None)
                parent._save_settings()
            if hasattr(parent, "_rebind_shortcuts"):
                parent._rebind_shortcuts()
            show_toast(parent, "Shortcuts reset to defaults", "info")
            dlg.destroy()

        br = tk.Frame(dlg, bg=T.BG)
        br.pack(pady=SP_MD)
        LimeBtn(br, "Save", _save).pack(side="left", padx=(0, 8))
        OrangeBtn(br, "Reset Defaults", _reset).pack(side="left", padx=(0, 8))
        ClassicBtn(br, "Cancel", dlg.destroy).pack(side="left")


class CommandPalette(tk.Toplevel):
    """Ctrl+K command palette with fuzzy search."""

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=T.CARD_BORDER)
        # Position centered over app
        aw = app.winfo_width()
        ax = app.winfo_rootx()
        ay = app.winfo_rooty()
        pw = 500; ph = 400
        self.geometry(f"{pw}x{ph}+{ax + aw // 2 - pw // 2}+{ay + 80}")
        inner = tk.Frame(self, bg=T.BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        # Search entry
        sf = tk.Frame(inner, bg=T.SURFACE_2)
        sf.pack(fill="x", padx=SP_SM, pady=SP_SM)
        tk.Label(sf, text="\U0001F50D", font=("Segoe UI", 14),
                 bg=T.SURFACE_2, fg=T.TEXT_DIM).pack(
                     side="left", padx=(SP_SM, SP_XS))
        self._var = tk.StringVar()
        self._entry = tk.Entry(
            sf, textvariable=self._var, font=T.F_H4, bg=T.SURFACE_2,
            fg=T.TEXT, relief="flat", bd=0, insertbackground=T.TEXT,
            highlightthickness=0)
        self._entry.pack(side="left", fill="x", expand=True,
                         padx=SP_XS, pady=SP_SM)
        self._entry.focus_set()

        # Results list
        self._lb = tk.Listbox(
            inner, font=T.F_BODY, bg=T.BG, fg=T.TEXT,
            selectbackground=T.BLUE_HL, selectforeground="#FFFFFF",
            relief="flat", bd=0, highlightthickness=0, activestyle="none")
        self._lb.pack(fill="both", expand=True, padx=SP_SM, pady=(0, SP_SM))

        # Build commands
        self._commands = []
        page_icons = {
            "search": "\U0001F50D", "download": "\U0001F4E5",
            "playlist": "\U0001F4CB", "converter": "\U0001F504",
            "player": "\U0001F3B5", "analyze": "\U0001F4CA",
            "stems": "\U0001F39A", "effects": "\U0001F3A8",
            "discovery": "\U0001F30D", "samples": "\U0001F4E6",
            "editor": "\u2702", "recorder": "\U0001F3A4",
            "spectrogram": "\U0001F308", "pitchtime": "\U0001F3B9",
            "schedule": "\u23F0", "history": "\U0001F4DC",
        }
        for name, page in app.pages.items():
            ico = page_icons.get(name, "\u25CF")
            self._commands.append(
                (f"{ico}  Go to {name.title()}",
                 lambda n=name: app._show_tab(n)))

        self._commands.append(
            ("\U0001F4C2  Open Downloads Folder", app._open_dl_folder))
        self._commands.append(
            ("\U0001F3A8  Cycle Theme", app._toggle_dark_mode))
        if hasattr(app, '_shortcut_reg'):
            self._commands.append(
                ("\u2328  Show Shortcuts",
                 lambda: app._shortcut_reg.show_help(app)))

        # Global search: history entries
        for entry in (app.history or [])[:100]:
            title = entry.get("title", "")
            if not title:
                continue
            url = entry.get("url", "")
            src = entry.get("source", "")[:10]

            def _go_hist(u=url):
                sp = app.pages.get("search")
                if sp and u:
                    sp.url_var.set(u)
                    app._show_tab("search")

            self._commands.append(
                (f"\U0001F4DC  {title[:40]}  ({src})", _go_hist))

        # Global search: discovery library
        disc = app.pages.get("discovery")
        if disc and hasattr(disc, "_library"):
            for fp, info in list(disc._library.items())[:100]:
                bpm = info.get("bpm", "?")
                key = info.get("key", "?")
                fname = os.path.basename(fp)[:35]

                def _go_play(f=fp):
                    pp = app.pages.get("player")
                    if pp:
                        if f not in pp._playlist_set:
                            pp._playlist.append(f)
                            pp._playlist_set.add(f)
                            pp.plb.insert("end", os.path.basename(f))
                        app._show_tab("player")

                self._commands.append(
                    (f"\U0001F3B5  {fname}  BPM:{bpm} Key:{key}", _go_play))

        self._filtered = list(self._commands)
        self._refresh_list()
        self._var.trace_add("write", lambda *a: self._filter())
        self._entry.bind("<Return>", self._execute)
        self._entry.bind("<Escape>", lambda e: self.destroy())
        self._entry.bind("<Down>", lambda e: self._move(1))
        self._entry.bind("<Up>", lambda e: self._move(-1))
        self._lb.bind("<Double-Button-1>", self._execute)
        self.bind("<FocusOut>",
                  lambda e: self.after(100, self._check_focus))

    def _check_focus(self):
        try:
            if self.focus_get() not in (self._entry, self._lb):
                self.destroy()
        except Exception:
            pass

    def _filter(self):
        q = self._var.get().lower()
        self._filtered = [(t, cb) for t, cb in self._commands
                          if q in t.lower()]
        self._refresh_list()

    def _refresh_list(self):
        self._lb.delete(0, "end")
        for text, _ in self._filtered:
            self._lb.insert("end", text)
        if self._filtered:
            self._lb.selection_set(0)

    def _move(self, delta):
        if not self._filtered:
            return
        cur = self._lb.curselection()
        idx = (cur[0] if cur else 0) + delta
        idx = max(0, min(idx, len(self._filtered) - 1))
        self._lb.selection_clear(0, "end")
        self._lb.selection_set(idx)
        self._lb.see(idx)

    def _execute(self, e=None):
        cur = self._lb.curselection()
        if cur and cur[0] < len(self._filtered):
            _, cb = self._filtered[cur[0]]
            self.destroy()
            cb()
