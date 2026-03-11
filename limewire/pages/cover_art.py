"""CoverArtPage — Manage album cover art: view, add, fetch, batch-apply."""

import os
import threading
import tkinter as tk
from tkinter import filedialog
from io import BytesIO

import mutagen
from PIL import Image, ImageTk

from limewire.core.theme import T
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import ClassicBtn, LimeBtn, OrangeBtn, GroupBox, ClassicEntry, ClassicProgress, PageSettingsPanel, GearButton
from limewire.ui.toast import show_toast
from limewire.services.cover_art import (
    extract_cover_art, embed_cover_art, prepare_cover_image,
    fetch_itunes_art, fetch_musicbrainz_art,
)


class CoverArtPage(ScrollFrame):
    """Manage album cover art — view, add, fetch, and batch-apply to audio files."""

    AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma")

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._files = []
        self._new_art = None
        self._new_mime = None
        self._build(self.inner)

    def _build(self, p):
        # ── Source Files ──
        fg = GroupBox(p, "Source Files")
        fg.pack(fill="x", padx=10, pady=(10, 6))
        fr = tk.Frame(fg, bg=T.BG)
        fr.pack(fill="x")
        self._settings_panel = PageSettingsPanel(p, "coverart", self.app, [
            ("art_display_size", "Display Size (px)", "choice", "200", {"choices": ["150", "200", "300"]}),
            ("art_fetch_resolution", "Fetch Resolution (px)", "choice", "500", {"choices": ["300", "500", "600", "1000"]}),
        ])
        self._gear = GearButton(fr, self._settings_panel)
        self._gear.pack(side="right")
        self.file_var = tk.StringVar()
        ClassicEntry(fr, self.file_var, width=50).pack(side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(fr, "Browse File", self._browse_file).pack(side="left", padx=(0, 4))
        ClassicBtn(fr, "Add Folder", self._add_folder).pack(side="left", padx=(0, 4))
        ClassicBtn(fr, "Clear", self._clear_files).pack(side="left")
        self.file_lb = tk.Listbox(
            fg, font=T.F_MONO, bg=T.INPUT_BG, fg=T.TEXT,
            selectbackground=T.LIME_DK, selectforeground=T.WHITE,
            height=6, relief="flat", bd=1,
            highlightthickness=1, highlightcolor=T.BORDER_L,
            highlightbackground=T.BORDER_D,
        )
        self.file_lb.pack(fill="x", pady=(6, 0))
        self.file_lb.bind("<<ListboxSelect>>", self._on_select)

        # ── Current Cover Art ──
        row = tk.Frame(p, bg=T.BG)
        row.pack(fill="x", padx=10, pady=(0, 6))
        cg = GroupBox(row, "Current Cover Art")
        cg.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self.cur_art = tk.Label(
            cg, text="No file\nselected", font=T.F_BODY,
            bg=T.CARD_BG, fg=T.TEXT_DIM, width=26, height=12,
            relief="groove", bd=1,
        )
        self.cur_art.pack(pady=4)
        self.cur_info = tk.Label(cg, text="", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.cur_info.pack(fill="x")

        # ── New Cover Art ──
        ng = GroupBox(row, "New Cover Art")
        ng.pack(side="left", fill="both", expand=True)
        self.new_art = tk.Label(
            ng, text="No image\nselected", font=T.F_BODY,
            bg=T.CARD_BG, fg=T.TEXT_DIM, width=26, height=12,
            relief="groove", bd=1,
        )
        self.new_art.pack(pady=4)
        nbr = tk.Frame(ng, bg=T.BG)
        nbr.pack(fill="x", pady=(2, 0))
        ClassicBtn(nbr, "Browse Image", self._browse_image).pack(side="left", padx=(0, 4))
        LimeBtn(nbr, "Fetch from iTunes", self._fetch_itunes).pack(side="left", padx=(0, 4))
        ClassicBtn(nbr, "Fetch from MusicBrainz", self._fetch_mb).pack(side="left")

        # ── Search fields ──
        sf = tk.Frame(ng, bg=T.BG)
        sf.pack(fill="x", pady=(6, 0))
        tk.Label(sf, text="Artist:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left")
        self.artist_var = tk.StringVar()
        ClassicEntry(sf, self.artist_var, width=18).pack(side="left", padx=(4, 8), ipady=2)
        tk.Label(sf, text="Album/Title:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(side="left")
        self.album_var = tk.StringVar()
        ClassicEntry(sf, self.album_var, width=18).pack(side="left", padx=(4, 0), ipady=2)
        self.new_info = tk.Label(ng, text="", font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.new_info.pack(fill="x", pady=(2, 0))

        # ── Apply ──
        ag = GroupBox(p, "Apply")
        ag.pack(fill="x", padx=10, pady=(0, 6))
        abr = tk.Frame(ag, bg=T.BG)
        abr.pack(fill="x")
        LimeBtn(abr, "Apply to Selected", self._apply_selected, width=18).pack(side="left", padx=(0, 8))
        LimeBtn(abr, "Apply to All Files", self._apply_all, width=18).pack(side="left", padx=(0, 8))
        OrangeBtn(abr, "Remove Art", self._remove_art).pack(side="left", padx=(0, 8))
        self.status_lbl = tk.Label(
            ag, text="Select files and cover art above",
            font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w",
        )
        self.status_lbl.pack(fill="x", pady=(4, 0))
        self.prog = ClassicProgress(ag)
        self.prog.pack(fill="x", pady=(4, 0))

    # ── File management ──
    def _browse_file(self):
        f = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus"), ("All", "*.*")],
        )
        if f:
            self.file_var.set(f)
            if f not in self._files:
                self._files.append(f)
            self._refresh_list()
            self._select_file(len(self._files) - 1)

    def _add_folder(self):
        d = filedialog.askdirectory()
        if not d:
            return
        added = 0
        for fn in sorted(os.listdir(d)):
            fp = os.path.join(d, fn)
            if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in self.AUDIO_EXTS:
                if fp not in self._files:
                    self._files.append(fp)
                    added += 1
        self._refresh_list()
        show_toast(self.app, f"Added {added} audio files", "info")

    def _clear_files(self):
        self._files.clear()
        self.file_lb.delete(0, "end")
        self.cur_art.config(image="", text="No file\nselected")
        self.cur_info.config(text="")

    def _refresh_list(self):
        self.file_lb.delete(0, "end")
        for fp in self._files:
            art_data, _ = extract_cover_art(fp)
            icon = "\u2713" if art_data else "\u2717"
            self.file_lb.insert("end", f" {icon}  {os.path.basename(fp)}")

    def _select_file(self, idx):
        self.file_lb.selection_clear(0, "end")
        self.file_lb.selection_set(idx)
        self.file_lb.see(idx)
        self._show_current_art(self._files[idx])

    def _on_select(self, e=None):
        sel = self.file_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < len(self._files):
            fp = self._files[idx]
            self.file_var.set(fp)
            self._show_current_art(fp)
            try:
                mf = mutagen.File(fp)
                if mf and hasattr(mf, "tags") and mf.tags:
                    for k in ["TPE1", "artist", "ARTIST", "\u00a9ART"]:
                        if k in mf.tags:
                            v = mf.tags[k]
                            self.artist_var.set(str(v[0]) if isinstance(v, list) else str(v))
                            break
                    for k in ["TALB", "album", "ALBUM", "\u00a9alb"]:
                        if k in mf.tags:
                            v = mf.tags[k]
                            self.album_var.set(str(v[0]) if isinstance(v, list) else str(v))
                            break
                    for k in ["TIT2", "title", "TITLE", "\u00a9nam"]:
                        if k in mf.tags:
                            v = mf.tags[k]
                            if not self.album_var.get():
                                self.album_var.set(str(v[0]) if isinstance(v, list) else str(v))
                            break
            except Exception:
                pass

    # ── Display helpers ──
    def _show_current_art(self, filepath):
        art_data, mime = extract_cover_art(filepath)
        if art_data:
            self._display_art(self.cur_art, art_data)
            try:
                img = Image.open(BytesIO(art_data))
                self.cur_info.config(text=f"{img.size[0]}x{img.size[1]}  {mime or '?'}  {len(art_data) // 1024}KB")
            except Exception:
                self.cur_info.config(text=f"{len(art_data) // 1024}KB")
        else:
            self.cur_art.config(image="", text="No cover art\nembedded")
            self.cur_info.config(text="")

    def _display_art(self, label, img_bytes, size=200):
        try:
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            img.thumbnail((size, size), Image.LANCZOS)
            ph = ImageTk.PhotoImage(img)
            label.config(image=ph, text="", width=size, height=size)
            label._img = ph
        except Exception:
            label.config(image="", text="Error loading\nimage")

    def _show_new_art(self, img_bytes, mime):
        self._new_art = img_bytes
        self._new_mime = mime
        self._display_art(self.new_art, img_bytes)
        try:
            img = Image.open(BytesIO(img_bytes))
            self.new_info.config(text=f"{img.size[0]}x{img.size[1]}  {mime}  {len(img_bytes) // 1024}KB")
        except Exception:
            self.new_info.config(text=f"{len(img_bytes) // 1024}KB")

    # ── Image source actions ──
    def _browse_image(self):
        f = filedialog.askopenfilename(
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All", "*.*")],
        )
        if not f:
            return
        with open(f, "rb") as fh:
            data = fh.read()
        prepared = prepare_cover_image(data, size=500)
        self._show_new_art(prepared, "image/jpeg")
        show_toast(self.app, f"Loaded: {os.path.basename(f)}", "info")

    def _fetch_itunes(self):
        query = f"{self.artist_var.get()} {self.album_var.get()}".strip()
        if not query:
            sel = self.file_lb.curselection()
            if sel and sel[0] < len(self._files):
                query = os.path.splitext(os.path.basename(self._files[sel[0]]))[0]
        if not query:
            show_toast(self.app, "Enter artist/album or select a file", "warning")
            return
        self.status_lbl.config(text=f"Searching iTunes for '{query[:40]}'...", fg=T.YELLOW)

        def _do():
            data = fetch_itunes_art(query, size=600)
            if data:
                prepared = prepare_cover_image(data, size=500)
                self.after(0, lambda: (
                    self._show_new_art(prepared, "image/jpeg"),
                    self.status_lbl.config(text="iTunes cover art found!", fg=T.LIME_DK),
                ))
            else:
                self.after(0, lambda: self.status_lbl.config(text="No cover art found on iTunes", fg=T.RED))

        threading.Thread(target=_do, daemon=True).start()

    def _fetch_mb(self):
        query = f"{self.artist_var.get()} {self.album_var.get()}".strip()
        if not query:
            sel = self.file_lb.curselection()
            if sel and sel[0] < len(self._files):
                query = os.path.splitext(os.path.basename(self._files[sel[0]]))[0]
        if not query:
            show_toast(self.app, "Enter artist/album or select a file", "warning")
            return
        self.status_lbl.config(text=f"Searching MusicBrainz for '{query[:40]}'...", fg=T.YELLOW)

        def _do():
            data = fetch_musicbrainz_art(query, size=500)
            if data:
                prepared = prepare_cover_image(data, size=500)
                self.after(0, lambda: (
                    self._show_new_art(prepared, "image/jpeg"),
                    self.status_lbl.config(text="MusicBrainz cover art found!", fg=T.LIME_DK),
                ))
            else:
                self.after(0, lambda: self.status_lbl.config(text="No cover art found on MusicBrainz", fg=T.RED))

        threading.Thread(target=_do, daemon=True).start()

    # ── Apply / Remove ──
    def _apply_selected(self):
        if not self._new_art:
            show_toast(self.app, "Select or fetch cover art first", "warning")
            return
        sel = self.file_lb.curselection()
        if not sel:
            show_toast(self.app, "Select a file from the list", "warning")
            return
        idx = sel[0]
        if idx >= len(self._files):
            return
        fp = self._files[idx]
        try:
            embed_cover_art(fp, self._new_art, self._new_mime or "image/jpeg")
            show_toast(self.app, f"Cover art applied to {os.path.basename(fp)}", "success")
            self._refresh_list()
            self._select_file(idx)
            self._show_current_art(fp)
        except Exception as e:
            show_toast(self.app, f"Error: {str(e)[:60]}", "error")

    def _apply_all(self):
        if not self._new_art:
            show_toast(self.app, "Select or fetch cover art first", "warning")
            return
        if not self._files:
            show_toast(self.app, "Add files first", "warning")
            return
        total = len(self._files)
        self.prog.configure(value=0)
        self.status_lbl.config(text=f"Applying cover art to {total} files...", fg=T.YELLOW)

        def _do():
            ok = 0
            fail = 0
            for i, fp in enumerate(self._files):
                try:
                    embed_cover_art(fp, self._new_art, self._new_mime or "image/jpeg")
                    ok += 1
                except Exception:
                    fail += 1
                self.after(0, lambda p=int((i + 1) / total * 100): self.prog.configure(value=p))
            msg = f"Done! {ok} files updated" + (f", {fail} failed" if fail else "")
            self.after(0, lambda: (
                self.status_lbl.config(text=msg, fg=T.LIME_DK if fail == 0 else T.YELLOW),
                self._refresh_list(),
                show_toast(self.app, msg, "success" if fail == 0 else "warning"),
            ))

        threading.Thread(target=_do, daemon=True).start()

    def _remove_art(self):
        sel = self.file_lb.curselection()
        if not sel:
            show_toast(self.app, "Select a file first", "warning")
            return
        idx = sel[0]
        if idx >= len(self._files):
            return
        fp = self._files[idx]
        try:
            audio = mutagen.File(fp)
            if audio is None:
                return
            from mutagen.mp3 import MP3 as _MP3
            from mutagen.flac import FLAC as _FLAC
            from mutagen.mp4 import MP4 as _MP4
            from mutagen.wave import WAVE as _WAVE
            if isinstance(audio, (_MP3, _WAVE)):
                if audio.tags:
                    audio.tags.delall("APIC")
            elif isinstance(audio, _FLAC):
                audio.clear_pictures()
            elif isinstance(audio, _MP4):
                if audio.tags and "covr" in audio.tags:
                    del audio.tags["covr"]
            elif hasattr(audio, "tags") and audio.tags and "metadata_block_picture" in audio:
                del audio["metadata_block_picture"]
            audio.save()
            show_toast(self.app, f"Cover art removed from {os.path.basename(fp)}", "info")
            self._refresh_list()
            self._select_file(idx)
            self._show_current_art(fp)
        except Exception as e:
            show_toast(self.app, f"Error: {str(e)[:60]}", "error")
