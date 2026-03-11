"""SettingsPage — Application settings: theme, output directory, clipboard watch, proxy."""
import tkinter as tk
from tkinter import ttk, filedialog

from limewire.core.theme import T
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, GroupBox, ClassicEntry)
from limewire.ui.toast import show_toast


class SettingsPage(ScrollFrame):
    """Application settings — theme, output directory, clipboard watch, proxy."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._build(self.inner)
    def _build(self,p):
        # -- Appearance --
        ag=GroupBox(p,"Appearance"); ag.pack(fill="x",padx=10,pady=(10,6))
        tr=tk.Frame(ag,bg=T.BG); tr.pack(fill="x",pady=(0,4))
        tk.Label(tr,text="Theme:",font=T.F_BOLD,bg=T.BG,fg=T.TEXT).pack(side="left")
        _theme_display=["LiveWire","Classic Light","Classic Dark","Modern Dark",
            "Synthwave","Dracula","Catppuccin","Tokyo Night","Spotify",
            "LimeWire Classic","Nord","Gruvbox","High Contrast",
            "Old School","Electric"]
        self._theme_var=tk.StringVar()
        self._theme_combo=ttk.Combobox(tr,textvariable=self._theme_var,
            values=_theme_display,state="readonly",width=18,font=T.F_BODY)
        self._theme_combo.pack(side="left",padx=(8,0))
        self._theme_combo.set(self.app._theme_key_map.get(
            self.app.settings.get("theme","livewire"),"LiveWire"))
        self._theme_combo.bind("<<ComboboxSelected>>",self.app._on_theme_select)
        tk.Label(ag,text="You can also cycle themes via the View menu or load a community theme JSON.",
                 font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w").pack(fill="x")
        # -- General --
        gg=GroupBox(p,"General"); gg.pack(fill="x",padx=10,pady=(0,6))
        # Output directory
        odr=tk.Frame(gg,bg=T.BG); odr.pack(fill="x",pady=(0,4))
        tk.Label(odr,text="Download Folder:",font=T.F_BOLD,bg=T.BG,fg=T.TEXT).pack(side="left")
        self._out_var=tk.StringVar(value=self.app.output_dir)
        ClassicEntry(odr,self._out_var,width=40).pack(side="left",padx=(8,4),fill="x",expand=True,ipady=2)
        ClassicBtn(odr,"Browse",self._browse_out).pack(side="left")
        # Clipboard watch
        cwr=tk.Frame(gg,bg=T.BG); cwr.pack(fill="x",pady=(0,4))
        self._clip_var=tk.BooleanVar(value=self.app.settings.get("clipboard_watch",True))
        ttk.Checkbutton(cwr,text="Auto-detect URLs from clipboard",variable=self._clip_var,
                        command=self._toggle_clip).pack(side="left")
        # Proxy
        pxr=tk.Frame(gg,bg=T.BG); pxr.pack(fill="x",pady=(0,4))
        tk.Label(pxr,text="Proxy:",font=T.F_BOLD,bg=T.BG,fg=T.TEXT).pack(side="left")
        self._proxy_var=tk.StringVar(value=self.app.settings.get("proxy",""))
        ClassicEntry(pxr,self._proxy_var,width=30).pack(side="left",padx=(8,4),ipady=2)
        ClassicBtn(pxr,"Apply",self._apply_proxy).pack(side="left")
        # Rate limit
        rlr=tk.Frame(gg,bg=T.BG); rlr.pack(fill="x",pady=(0,4))
        tk.Label(rlr,text="Rate Limit:",font=T.F_BOLD,bg=T.BG,fg=T.TEXT).pack(side="left")
        self._rate_var=tk.StringVar(value=self.app.settings.get("rate_limit",""))
        ClassicEntry(rlr,self._rate_var,width=15).pack(side="left",padx=(8,4),ipady=2)
        tk.Label(rlr,text="(e.g. 5M for 5 MB/s, empty = unlimited)",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM).pack(side="left")
        # Discord RPC
        drr=tk.Frame(gg,bg=T.BG); drr.pack(fill="x",pady=(0,4))
        self._rpc_var=tk.BooleanVar(value=self.app.settings.get("discord_rpc",True))
        ttk.Checkbutton(drr,text="Enable Discord Rich Presence",variable=self._rpc_var,
                        command=self._toggle_rpc).pack(side="left")
        # -- About --
        ab=GroupBox(p,"About"); ab.pack(fill="x",padx=10,pady=(0,6))
        tk.Label(ab,text="LimeWire v3.0.0 Studio Edition",font=T.F_BOLD,bg=T.BG,fg=T.LIME_DK).pack(anchor="w")
        tk.Label(ab,text="A modern music toolkit built with Python & tkinter.",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM).pack(anchor="w")
    def _browse_out(self):
        d=filedialog.askdirectory(initialdir=self.app.output_dir)
        if d:
            self.app.output_dir=d; self._out_var.set(d)
            self.app.settings["output_dir"]=d; self.app._save_settings()
            show_toast(self.app,f"Download folder: {d}","info")
    def _toggle_clip(self):
        self.app.settings["clipboard_watch"]=self._clip_var.get(); self.app._save_settings()
    def _apply_proxy(self):
        self.app.settings["proxy"]=self._proxy_var.get().strip(); self.app._save_settings()
        show_toast(self.app,"Proxy updated","info")
    def _toggle_rpc(self):
        self.app.settings["discord_rpc"]=self._rpc_var.get(); self.app._save_settings()
