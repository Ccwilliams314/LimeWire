"""EditorPage — Non-destructive audio editor with trim, cut, fade, merge, and undo/redo."""
import os, threading, tempfile
import tkinter as tk
from tkinter import filedialog

from limewire.core.theme import T, _lerp_color
from limewire.core.constants import EDITOR_WAVEFORM_H, EDITOR_UNDO_MAX, EDITOR_FADE_DEFAULT_MS
from limewire.core.deps import _ensure_pydub, _ensure_librosa, HAS_PYDUB, AudioSegment
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicListbox,
                                  ClassicProgress, PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.services.audio_processing import (
    audio_segment_to_waveform, load_audio_pydub, export_audio_pydub,
)


class EditorPage(ScrollFrame):
    """Non-destructive audio editor with trim, cut, fade, merge, and undo/redo."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app
        self._segment=None; self._undo_stack=[]; self._redo_stack=[]
        self._sel_start_ms=0; self._sel_end_ms=0; self._drag_start=None
        self._merge_files=[]; self._bars=[]
        self._zoom=1.0; self._scroll_offset=0.0  # 0.0-1.0 normalized scroll
        self._build(self.inner)

    def _build(self,p):
        # Source file
        fg=GroupBox(p,"Source Audio File"); fg.pack(fill="x",padx=10,pady=(10,6))
        fr=tk.Frame(fg,bg=T.BG); fr.pack(fill="x")
        self.file_var=tk.StringVar()
        ClassicEntry(fr,self.file_var,width=55).pack(side="left",fill="x",expand=True,ipady=2,padx=(0,8))
        ClassicBtn(fr,"Browse...",self._browse).pack(side="left")
        self._settings_panel=PageSettingsPanel(p,"editor",self.app,[
            ("default_fade_ms","Default Fade (ms)","int",500,{"min":10,"max":5000}),
            ("max_zoom","Max Zoom","choice","32",{"choices":["8","16","32","64"]}),
            ("normalization_target_db","Normalize Target (dB)","float",-1.0,{"min":-6.0,"max":0.0,"increment":0.5}),
        ])
        self._gear=GearButton(fr,self._settings_panel)
        self._gear.pack(side="right")
        self.info_lbl=tk.Label(fg,text="Load an audio file to begin editing",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.info_lbl.pack(fill="x",pady=(4,0))

        # Waveform canvas
        wg=GroupBox(p,"Waveform"); wg.pack(fill="x",padx=10,pady=(0,6))
        self.wave_cv=tk.Canvas(wg,bg=T.CANVAS_BG,height=EDITOR_WAVEFORM_H,highlightthickness=0)
        self.wave_cv.pack(fill="x",padx=4,pady=4)
        self.wave_cv.bind("<ButtonPress-1>",self._on_press)
        self.wave_cv.bind("<B1-Motion>",self._on_drag)
        self.wave_cv.bind("<ButtonRelease-1>",self._on_release)
        self.wave_cv.bind("<MouseWheel>",self._on_zoom)  # Ctrl+scroll = zoom
        self.wave_cv.bind("<Shift-MouseWheel>",self._on_hscroll)  # Shift+scroll = pan
        # Zoom controls
        zf=tk.Frame(wg,bg=T.BG); zf.pack(fill="x",padx=4,pady=(0,2))
        ClassicBtn(zf,"Zoom In (+)",self._zoom_in).pack(side="left",padx=(0,4))
        ClassicBtn(zf,"Zoom Out (-)",self._zoom_out).pack(side="left",padx=(0,4))
        ClassicBtn(zf,"Fit All",self._zoom_reset).pack(side="left",padx=(0,8))
        self._zoom_lbl=tk.Label(zf,text="1.0x",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM)
        self._zoom_lbl.pack(side="left",padx=(0,8))
        self._color_freq=tk.BooleanVar(value=False)
        tk.Checkbutton(zf,text="Color by frequency",variable=self._color_freq,font=T.F_SMALL,
                       bg=T.BG,fg=T.TEXT,selectcolor=T.INPUT_BG,activebackground=T.BG,activeforeground=T.TEXT,
                       command=self._draw_waveform).pack(side="left",padx=(0,8))
        self._freq_colors=[]
        self._hscroll=tk.Scrollbar(wg,orient="horizontal",command=self._on_scrollbar)
        self._hscroll.pack(fill="x",padx=4)
        # Minimap — full waveform overview with viewport indicator
        self._minimap=tk.Canvas(wg,bg=T.CANVAS_BG,height=24,highlightthickness=0)
        self._minimap.pack(fill="x",padx=4,pady=(2,0))
        self._minimap.bind("<Button-1>",self._minimap_click)
        # Time labels
        tf=tk.Frame(wg,bg=T.BG); tf.pack(fill="x",padx=4)
        self.time_start_lbl=tk.Label(tf,text="Start: 0.000s",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM)
        self.time_start_lbl.pack(side="left")
        self.time_end_lbl=tk.Label(tf,text="End: 0.000s",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM)
        self.time_end_lbl.pack(side="right")
        self.sel_lbl=tk.Label(tf,text="Selection: none",font=T.F_SMALL,bg=T.BG,fg=T.LIME)
        self.sel_lbl.pack()

        # Selection controls
        sg=GroupBox(p,"Selection (ms)"); sg.pack(fill="x",padx=10,pady=(0,6))
        sr=tk.Frame(sg,bg=T.BG); sr.pack(fill="x")
        tk.Label(sr,text="Start:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.sel_start_var=tk.StringVar(value="0")
        self.sel_start_sp=tk.Spinbox(sr,textvariable=self.sel_start_var,from_=0,to=9999999,
            width=10,font=T.F_BODY,bg=T.INPUT_BG,fg=T.TEXT,relief="flat",bd=1)
        self.sel_start_sp.pack(side="left",padx=(0,10))
        tk.Label(sr,text="End:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.sel_end_var=tk.StringVar(value="0")
        self.sel_end_sp=tk.Spinbox(sr,textvariable=self.sel_end_var,from_=0,to=9999999,
            width=10,font=T.F_BODY,bg=T.INPUT_BG,fg=T.TEXT,relief="flat",bd=1)
        self.sel_end_sp.pack(side="left",padx=(0,10))
        ClassicBtn(sr,"Select All",self._select_all).pack(side="left",padx=(0,6))
        ClassicBtn(sr,"Apply",self._apply_sel).pack(side="left",padx=(0,6))
        ClassicBtn(sr,"Snap Zero-X",self._snap_zero_crossing).pack(side="left")

        # Operations
        og=GroupBox(p,"Operations"); og.pack(fill="x",padx=10,pady=(0,6))
        obr=tk.Frame(og,bg=T.BG); obr.pack(fill="x")
        for txt,cmd in [("Trim",self._trim),("Cut",self._cut),("Fade In",self._fade_in),
                        ("Fade Out",self._fade_out),("Normalize",self._normalize),
                        ("Reverse",self._reverse),("Silence",self._silence)]:
            LimeBtn(obr,txt,cmd,width=10).pack(side="left",padx=(0,4),pady=2)
        ubr=tk.Frame(og,bg=T.BG); ubr.pack(fill="x",pady=(4,0))
        ClassicBtn(ubr,"Undo (Ctrl+Z)",self._undo).pack(side="left",padx=(0,6))
        ClassicBtn(ubr,"Redo (Ctrl+Y)",self._redo).pack(side="left")

        # Merge
        mg=GroupBox(p,"Merge / Concatenate"); mg.pack(fill="x",padx=10,pady=(0,6))
        mr=tk.Frame(mg,bg=T.BG); mr.pack(fill="x")
        LimeBtn(mr,"Add File",self._merge_add).pack(side="left",padx=(0,6))
        OrangeBtn(mr,"Clear List",self._merge_clear).pack(side="left",padx=(0,6))
        LimeBtn(mr,"Merge All",self._merge_all).pack(side="left")
        self.merge_lb_frame,self.merge_lb=ClassicListbox(mg,height=4)
        self.merge_lb_frame.pack(fill="x",pady=(4,0))

        # Export
        eg=GroupBox(p,"Export"); eg.pack(fill="x",padx=10,pady=(0,10))
        er=tk.Frame(eg,bg=T.BG); er.pack(fill="x")
        tk.Label(er,text="Format:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,6))
        self.exp_fmt_var=tk.StringVar(value="mp3")
        ClassicCombo(er,self.exp_fmt_var,["mp3","wav","flac","ogg","aac","m4a"],width=8).pack(side="left",padx=(0,8))
        LimeBtn(er,"Export",self._export,width=12).pack(side="left",padx=(0,8))
        ClassicBtn(er,"Play Preview",self._play_preview).pack(side="left")
        self.exp_status=tk.Label(eg,text="",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.exp_status.pack(fill="x",pady=(4,0))
        self.exp_prog=ClassicProgress(eg); self.exp_prog.pack(fill="x",pady=(4,0))

    def _browse(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus"),("All","*.*")])
        if f: self.file_var.set(f); self._load_file(f)

    def _load_file(self,path):
        self.exp_status.config(text="Loading...",fg=T.YELLOW)
        def _do():
            seg,err=load_audio_pydub(path)
            if err:
                self.after(0,lambda:self.exp_status.config(text=f"Error: {err}",fg=T.RED))
                return
            self._segment=seg; self._undo_stack=[seg]; self._redo_stack=[]
            self._sel_start_ms=0; self._sel_end_ms=len(seg)
            dur=len(seg)/1000
            self.after(0,lambda:(
                self.info_lbl.config(text=f"{os.path.basename(path)}  |  {dur:.1f}s  |  {seg.channels}ch  {seg.frame_rate}Hz"),
                self.exp_status.config(text="Loaded",fg=T.LIME_DK),
                self._update_sel_labels(),
                self._draw_waveform()
            ))
        threading.Thread(target=_do,daemon=True).start()

    def _push_undo(self):
        if self._segment is not None:
            self._undo_stack.append(self._segment)
            if len(self._undo_stack)>EDITOR_UNDO_MAX:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def _draw_waveform(self):
        cv=self.wave_cv; cv.delete("all")
        if not self._segment: return
        cv.update_idletasks()
        w=cv.winfo_width() or 600; h=EDITOR_WAVEFORM_H
        dur_ms=len(self._segment)
        # Compute zoomed sample count — render more bars than canvas width for zoom
        total_bars=int(w*self._zoom)
        all_bars=audio_segment_to_waveform(self._segment,total_bars,h)
        if not all_bars: return
        # Visible window based on scroll offset
        visible=len(all_bars)/self._zoom if self._zoom>0 else len(all_bars)
        start_idx=int(self._scroll_offset*max(0,len(all_bars)-visible))
        end_idx=int(start_idx+visible)
        start_idx=max(0,min(start_idx,len(all_bars)-1))
        end_idx=max(start_idx+1,min(end_idx,len(all_bars)))
        visible_bars=all_bars[start_idx:end_idx]
        self._bars=all_bars; self._view_start=start_idx; self._view_end=end_idx
        # Compute frequency colors if enabled
        use_freq=self._color_freq.get() if hasattr(self,"_color_freq") else False
        if use_freq and len(self._freq_colors)!=len(all_bars):
            self._freq_colors=self._compute_freq_colors(self._segment,len(all_bars))
        # Draw bars scaled to canvas width
        mid=h//2
        n=len(visible_bars)
        for i,bh in enumerate(visible_bars):
            x=int(i*w/n) if n>0 else i
            if use_freq and self._freq_colors:
                ci=start_idx+i
                clr=self._freq_colors[ci] if ci<len(self._freq_colors) else T.LIME
            else:
                clr=T.LIME
            cv.create_line(x,mid-bh//2,x,mid+bh//2,fill=clr)
        # Draw selection overlay (mapped to visible range)
        if self._segment and self._sel_start_ms<self._sel_end_ms and dur_ms>0:
            # Map ms to bar index
            sel_bar_start=self._sel_start_ms/dur_ms*len(all_bars)
            sel_bar_end=self._sel_end_ms/dur_ms*len(all_bars)
            # Map to visible pixel range
            x1=int((sel_bar_start-start_idx)/(end_idx-start_idx)*w)
            x2=int((sel_bar_end-start_idx)/(end_idx-start_idx)*w)
            x1=max(0,min(x1,w)); x2=max(0,min(x2,w))
            if x2>x1: cv.create_rectangle(x1,0,x2,h,fill=T.LIME,stipple="gray25",outline="")
        # Update scrollbar
        if len(all_bars)>0:
            thumb_size=min(1.0,1.0/self._zoom)
            lo=self._scroll_offset*(1.0-thumb_size)
            self._hscroll.set(lo,lo+thumb_size)
        self._zoom_lbl.config(text=f"{self._zoom:.1f}x")
        # Update minimap
        self._draw_minimap(all_bars,start_idx,end_idx)

    def _compute_freq_colors(self,segment,num_bars):
        """Compute per-bar color based on spectral centroid (low=cyan, mid=green, high=orange)."""
        if not _ensure_librosa(): return [T.LIME]*num_bars
        try:
            import numpy as _np
            import limewire.core.deps as _d
            librosa = _d.librosa
            samples=_np.array(segment.get_array_of_samples(),dtype=_np.float32)
            if segment.channels>1: samples=samples[::segment.channels]
            sr=segment.frame_rate
            # Compute spectral centroid
            S=librosa.feature.spectral_centroid(y=samples,sr=sr,hop_length=max(1,len(samples)//num_bars))
            centroids=S[0]
            # Normalize to 0-1 range
            mn,mx=centroids.min(),centroids.max()
            if mx-mn<1: return [T.LIME]*num_bars
            norm=(centroids-mn)/(mx-mn)
            # Map to colors: 0=cyan(low), 0.5=lime(mid), 1.0=orange(high)
            colors=[]
            for v in norm:
                if v<0.33: colors.append(_lerp_color("#00CED1",T.LIME,v/0.33))
                elif v<0.66: colors.append(_lerp_color(T.LIME,T.YELLOW,(v-0.33)/0.33))
                else: colors.append(_lerp_color(T.YELLOW,T.ORANGE,(v-0.66)/0.34))
            # Pad/trim to match num_bars
            while len(colors)<num_bars: colors.append(T.LIME)
            return colors[:num_bars]
        except Exception:
            return [T.LIME]*num_bars

    def _px_to_ms(self,x):
        """Convert canvas pixel x to milliseconds, accounting for zoom/scroll."""
        if not self._segment: return 0
        cv=self.wave_cv; w=cv.winfo_width() or 600; dur_ms=len(self._segment)
        if not hasattr(self,"_view_start"): return int(x/w*dur_ms)
        total=len(self._bars) if self._bars else w
        bar_idx=self._view_start+(x/w)*(self._view_end-self._view_start)
        return int(max(0,min(dur_ms,bar_idx/total*dur_ms)))
    def _on_press(self,e):
        self._drag_start=e.x
    def _on_drag(self,e):
        if self._drag_start is None or not self._segment: return
        x1=min(self._drag_start,e.x); x2=max(self._drag_start,e.x)
        self._sel_start_ms=self._px_to_ms(x1)
        self._sel_end_ms=self._px_to_ms(x2)
        self._update_sel_labels(); self._draw_waveform()
    def _on_release(self,e):
        self._drag_start=None
        self._update_sel_labels()
    def _on_zoom(self,e):
        """Ctrl+mousewheel or plain mousewheel to zoom."""
        if e.delta>0: self._zoom_in()
        else: self._zoom_out()
    def _on_hscroll(self,e):
        """Shift+mousewheel to pan horizontally."""
        if self._zoom<=1.0: return
        step=0.05
        if e.delta>0: self._scroll_offset=max(0.0,self._scroll_offset-step)
        else: self._scroll_offset=min(1.0,self._scroll_offset+step)
        self._draw_waveform()
    def _on_scrollbar(self,*args):
        """Handle scrollbar commands."""
        if args[0]=="moveto":
            thumb_size=min(1.0,1.0/self._zoom)
            self._scroll_offset=min(1.0,float(args[1])/(1.0-thumb_size)) if thumb_size<1.0 else 0.0
            self._scroll_offset=max(0.0,min(1.0,self._scroll_offset))
            self._draw_waveform()
    def _zoom_in(self):
        self._zoom=min(32.0,self._zoom*1.5); self._draw_waveform()
    def _zoom_out(self):
        self._zoom=max(1.0,self._zoom/1.5)
        if self._zoom<=1.0: self._scroll_offset=0.0
        self._draw_waveform()
    def _zoom_reset(self):
        self._zoom=1.0; self._scroll_offset=0.0; self._draw_waveform()
    def _draw_minimap(self,all_bars,view_start,view_end):
        """Draw minimap showing full waveform with viewport rectangle."""
        mm=self._minimap; mm.delete("all")
        if not all_bars: return
        mm.update_idletasks()
        w=mm.winfo_width() or 600; h=24; mid=h//2; n=len(all_bars)
        # Draw full waveform (compressed)
        for i in range(w):
            bar_idx=int(i*n/w)
            if bar_idx<n:
                bh=max(1,all_bars[bar_idx])
                mm.create_line(i,mid-bh*mid//max(1,max(all_bars)),i,mid+bh*mid//max(1,max(all_bars)),fill=T.TEXT_DIM)
        # Draw viewport rectangle
        if self._zoom>1.0 and n>0:
            x1=int(view_start/n*w); x2=int(view_end/n*w)
            mm.create_rectangle(x1,0,x2,h,outline=T.LIME,width=2,fill="")
    def _minimap_click(self,e):
        """Click minimap to scroll to that position."""
        if self._zoom<=1.0: return
        mm=self._minimap; w=mm.winfo_width() or 600
        self._scroll_offset=max(0.0,min(1.0,e.x/w))
        self._draw_waveform()

    def _update_sel_labels(self):
        if not self._segment: return
        dur_ms=len(self._segment)
        self.time_start_lbl.config(text=f"Start: {self._sel_start_ms/1000:.3f}s")
        self.time_end_lbl.config(text=f"End: {dur_ms/1000:.3f}s")
        sel_dur=(self._sel_end_ms-self._sel_start_ms)/1000
        self.sel_lbl.config(text=f"Selection: {self._sel_start_ms}ms - {self._sel_end_ms}ms ({sel_dur:.3f}s)")
        self.sel_start_var.set(str(self._sel_start_ms))
        self.sel_end_var.set(str(self._sel_end_ms))

    def _select_all(self):
        if not self._segment: return
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()

    def _apply_sel(self):
        try:
            self._sel_start_ms=int(self.sel_start_var.get())
            self._sel_end_ms=int(self.sel_end_var.get())
            self._draw_waveform(); self._update_sel_labels()
        except ValueError: pass

    def _snap_zero_crossing(self):
        """Snap selection edges to nearest zero-crossing for clean cuts."""
        if not self._segment or not _ensure_pydub(): return
        samples=self._segment.get_array_of_samples()
        sr=self._segment.frame_rate; ch=self._segment.channels
        def _find_zero(ms,direction=1):
            idx=int(ms/1000*sr)*ch
            search=range(idx,min(idx+sr*ch//10,len(samples)-1)) if direction>0 else range(idx,max(idx-sr*ch//10,0),-1)
            for i in search:
                if i+1<len(samples) and samples[i]<=0<=samples[i+1] or samples[i]>=0>=samples[i+1]:
                    return int(i/ch/sr*1000)
            return ms
        self._sel_start_ms=_find_zero(self._sel_start_ms,1)
        self._sel_end_ms=_find_zero(self._sel_end_ms,-1)
        self._update_sel_labels(); self._draw_waveform()
        show_toast(self.app,"Snapped to zero-crossings","info")

    def _trim(self):
        if not self._segment: return
        self._push_undo()
        self._segment=self._segment[self._sel_start_ms:self._sel_end_ms]
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Trimmed",fg=T.LIME_DK)

    def _cut(self):
        if not self._segment: return
        self._push_undo()
        before=self._segment[:self._sel_start_ms]
        after=self._segment[self._sel_end_ms:]
        self._segment=before+after
        self._sel_end_ms=min(self._sel_start_ms,len(self._segment))
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Cut selection removed",fg=T.LIME_DK)

    def _fade_in(self):
        if not self._segment: return
        self._push_undo()
        dur=self._sel_end_ms-self._sel_start_ms
        if dur<=0: dur=EDITOR_FADE_DEFAULT_MS
        self._segment=self._segment.fade_in(dur)
        self._draw_waveform()
        self.exp_status.config(text=f"Fade in: {dur}ms",fg=T.LIME_DK)

    def _fade_out(self):
        if not self._segment: return
        self._push_undo()
        dur=self._sel_end_ms-self._sel_start_ms
        if dur<=0: dur=EDITOR_FADE_DEFAULT_MS
        self._segment=self._segment.fade_out(dur)
        self._draw_waveform()
        self.exp_status.config(text=f"Fade out: {dur}ms",fg=T.LIME_DK)

    def _normalize(self):
        if not self._segment: return
        self._push_undo()
        from pydub.effects import normalize
        self._segment=normalize(self._segment)
        self._draw_waveform()
        self.exp_status.config(text="Normalized",fg=T.LIME_DK)

    def _reverse(self):
        if not self._segment: return
        self._push_undo()
        self._segment=self._segment.reverse()
        self._draw_waveform()
        self.exp_status.config(text="Reversed",fg=T.LIME_DK)

    def _silence(self):
        if not self._segment: return
        self._push_undo()
        from pydub import AudioSegment as _AS
        dur=self._sel_end_ms-self._sel_start_ms
        if dur<=0: return
        silent=_AS.silent(duration=dur,frame_rate=self._segment.frame_rate)
        self._segment=self._segment[:self._sel_start_ms]+silent+self._segment[self._sel_end_ms:]
        self._draw_waveform()
        self.exp_status.config(text=f"Silenced {dur}ms",fg=T.LIME_DK)

    def _undo(self):
        if len(self._undo_stack)<=1: return
        self._redo_stack.append(self._undo_stack.pop())
        self._segment=self._undo_stack[-1]
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Undo",fg=T.TEXT_DIM)

    def _redo(self):
        if not self._redo_stack: return
        seg=self._redo_stack.pop()
        self._undo_stack.append(seg); self._segment=seg
        self._sel_start_ms=0; self._sel_end_ms=len(self._segment)
        self._update_sel_labels(); self._draw_waveform()
        self.exp_status.config(text="Redo",fg=T.TEXT_DIM)

    def _merge_add(self):
        f=filedialog.askopenfilename(filetypes=[("Audio","*.mp3 *.wav *.flac *.ogg *.m4a"),("All","*.*")])
        if f:
            self._merge_files.append(f)
            self.merge_lb.insert("end",os.path.basename(f))

    def _merge_clear(self):
        self._merge_files.clear(); self.merge_lb.delete(0,"end")

    def _merge_all(self):
        files=list(self._merge_files)
        if self._segment: files.insert(0,None)  # None = current segment
        if len(files)<2:
            self.exp_status.config(text="Add at least 2 files to merge",fg=T.YELLOW); return
        self.exp_status.config(text="Merging...",fg=T.YELLOW)
        def _do():
            try:
                _ensure_pydub()
                from pydub import AudioSegment as _AS
                combined=self._segment if self._segment else _AS.empty()
                for f in files:
                    if f is None: continue
                    seg,err=load_audio_pydub(f)
                    if err: self.after(0,lambda:self.exp_status.config(text=f"Error: {err}",fg=T.RED)); return
                    combined+=seg
                self._push_undo(); self._segment=combined
                self._sel_start_ms=0; self._sel_end_ms=len(combined)
                self.after(0,lambda:(self._update_sel_labels(),self._draw_waveform(),
                    self.exp_status.config(text=f"Merged {len(files)} files ({len(combined)/1000:.1f}s)",fg=T.LIME_DK)))
            except Exception as e:
                self.after(0,lambda:self.exp_status.config(text=f"Merge error: {str(e)[:60]}",fg=T.RED))
        threading.Thread(target=_do,daemon=True).start()

    def _export(self):
        if not self._segment: return
        fmt=self.exp_fmt_var.get()
        path=filedialog.asksaveasfilename(defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(),f"*.{fmt}"),("All","*.*")],
            initialdir=self.app.output_dir)
        if not path: return
        self.exp_status.config(text="Exporting...",fg=T.YELLOW)
        self.exp_prog["value"]=50
        def _do():
            out,err=export_audio_pydub(self._segment,path,fmt)
            if err:
                self.after(0,lambda:(self.exp_status.config(text=f"Error: {err}",fg=T.RED),
                    self.exp_prog.configure(value=0)))
            else:
                self.after(0,lambda:(self.exp_status.config(text=f"Exported: {os.path.basename(out)}",fg=T.LIME_DK),
                    self.exp_prog.configure(value=100),self.app.toast(f"Exported: {os.path.basename(out)}")))
        threading.Thread(target=_do,daemon=True).start()

    def _play_preview(self):
        if not self._segment: return
        seg=self._segment
        def _do_preview():
            fd,tmp=tempfile.mkstemp(suffix=".wav",prefix="_lw_edit_")
            os.close(fd)
            try:
                seg.export(tmp,format="wav")
                _audio.load(tmp); _audio.play()
                self.after(0,lambda:self.exp_status.config(text="Playing preview...",fg=T.LIME_DK))
            except Exception as e:
                self.after(0,lambda:self.exp_status.config(text=f"Preview error: {str(e)[:60]}",fg=T.RED))
            finally:
                try: os.unlink(tmp)
                except OSError: pass
        threading.Thread(target=_do_preview,daemon=True).start()
