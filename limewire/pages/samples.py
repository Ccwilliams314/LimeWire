"""SamplesPage — Freesound.org sample browser and downloader."""
import os, threading, tempfile, urllib.parse, webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox

import requests

from limewire.core.theme import T
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicListbox,
                                  PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.utils.helpers import sanitize_filename


class SamplesPage(ScrollFrame):
    """Freesound.org sample browser and downloader."""
    def __init__(self,parent,app):
        super().__init__(parent); self.app=app; self._results=[]; self._build(self.inner)
    def _build(self,p):
        sg=GroupBox(p,"Freesound Sample Search"); sg.pack(fill="x",padx=10,pady=(10,6))
        sr=tk.Frame(sg,bg=T.BG); sr.pack(fill="x")
        self._settings_panel=PageSettingsPanel(p,"samples",self.app,[
            ("results_per_page","Results Per Page","int",30,{"min":10,"max":100}),
            ("request_timeout","Request Timeout (s)","int",15,{"min":5,"max":60}),
        ])
        self._gear=GearButton(sr,self._settings_panel)
        self._gear.pack(side="right")
        tk.Label(sr,text="Search:",font=T.F_BOLD,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,6))
        self.query_var=tk.StringVar()
        self.query_e=ClassicEntry(sr,self.query_var,width=30)
        self.query_e.pack(side="left",fill="x",expand=True,ipady=2,padx=(0,6))
        self.query_e.bind("<Return>",lambda e:self._search())
        LimeBtn(sr,"Search",self._search).pack(side="left",padx=(0,6))
        # Filters
        fr=tk.Frame(sg,bg=T.BG); fr.pack(fill="x",pady=(4,0))
        tk.Label(fr,text="Duration:",font=T.F_SMALL,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.dur_var=tk.StringVar(value="any")
        ClassicCombo(fr,self.dur_var,["any","0-5s","5-30s","30s-2m","2m+"],width=8).pack(side="left",padx=(0,12))
        tk.Label(fr,text="Sort:",font=T.F_SMALL,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,4))
        self.sort_var=tk.StringVar(value="score")
        ClassicCombo(fr,self.sort_var,["score","downloads_desc","rating_desc","duration_asc","created_desc"],width=16).pack(side="left")

        self.search_status=tk.Label(sg,text="Search Freesound.org for samples, loops, and sound effects (API key required)",
                                    font=T.F_SMALL,bg=T.BG,fg=T.TEXT_DIM,anchor="w")
        self.search_status.pack(fill="x",pady=(4,0))

        # Results
        rg=GroupBox(p,"Results"); rg.pack(fill="both",padx=10,pady=(0,6),expand=True)
        cols=tk.Frame(rg,bg=T.CARD_BG,bd=0); cols.pack(fill="x")
        tk.Frame(rg,bg=T.CARD_BORDER,height=1).pack(fill="x")
        for col,w in [("Name",30),("Duration",10),("Rate",8),("Downloads",10),("License",15)]:
            tk.Label(cols,text=col,font=T.F_BOLD,bg=T.CARD_BG,fg=T.TEXT,width=w,anchor="w").pack(side="left")
        self.res_frame,self.res_lb=ClassicListbox(rg,height=12)
        self.res_frame.pack(fill="both",expand=True)

        # Actions
        ag=tk.Frame(rg,bg=T.BG); ag.pack(fill="x",pady=(6,0))
        OrangeBtn(ag,"Preview",self._preview).pack(side="left",padx=(0,6))
        LimeBtn(ag,"Download Selected",self._download).pack(side="left",padx=(0,6))
        ClassicBtn(ag,"Open in Browser",self._open_web).pack(side="left")

        # API Key
        kg=GroupBox(p,"Freesound API Key"); kg.pack(fill="x",padx=10,pady=(0,10))
        kr=tk.Frame(kg,bg=T.BG); kr.pack(fill="x")
        tk.Label(kr,text="API Key:",font=T.F_BODY,bg=T.BG,fg=T.TEXT).pack(side="left",padx=(0,6))
        self.key_var=tk.StringVar(value=self.app.settings.get("freesound_api_key",""))
        ClassicEntry(kr,self.key_var,width=40).pack(side="left",fill="x",expand=True,ipady=1,padx=(0,6))
        ClassicBtn(kr,"Save Key",self._save_key).pack(side="left")
        tk.Label(kg,text="Get a free key at freesound.org/apiv2/apply/",font=T.F_SMALL,bg=T.BG,fg=T.TEXT_BLUE).pack(anchor="w",pady=(2,0))

    def _save_key(self):
        self.app.settings["freesound_api_key"]=self.key_var.get().strip()
        self.app._save_settings(); self.app.toast("Freesound API key saved")

    def _search(self):
        query=self.query_var.get().strip()
        if not query: return
        key=self.key_var.get().strip() or self.app.settings.get("freesound_api_key","")
        if not key:
            messagebox.showinfo("LimeWire","Set your Freesound API key first."); return
        self.search_status.config(text=f"Searching: {query}...",fg=T.YELLOW)
        threading.Thread(target=self._do_search,args=(query,key),daemon=True).start()

    def _do_search(self,query,api_key):
        try:
            dur_filter=""
            dur=self.dur_var.get() if hasattr(self,"dur_var") else "any"
            if dur=="0-5s": dur_filter="&filter=duration:[0 TO 5]"
            elif dur=="5-30s": dur_filter="&filter=duration:[5 TO 30]"
            elif dur=="30s-2m": dur_filter="&filter=duration:[30 TO 120]"
            elif dur=="2m+": dur_filter="&filter=duration:[120 TO *]"
            sort=self.sort_var.get() if hasattr(self,"sort_var") else "score"
            url=(f"https://freesound.org/apiv2/search/text/?query={requests.utils.quote(query)}"
                 f"&fields=id,name,duration,samplerate,download_count,license,previews,url"
                 f"&page_size=30&sort={sort}{dur_filter}&token={api_key}")
            resp=requests.get(url,timeout=15)
            if resp.status_code==200:
                data=resp.json()
                self._results=data.get("results",[])
                self.after(0,lambda:self._render_results(data.get("count",0)))
            elif resp.status_code==401:
                self.after(0,lambda:self.search_status.config(text="Invalid API key",fg=T.RED))
            else:
                self.after(0,lambda:self.search_status.config(text=f"Error: HTTP {resp.status_code}",fg=T.RED))
        except Exception as e:
            self.after(0,lambda:self.search_status.config(text=f"Error: {str(e)[:60]}",fg=T.RED))

    def _render_results(self,total):
        self.res_lb.delete(0,"end")
        for r in self._results:
            dur=r.get("duration",0)
            dur_s=f"{dur:.1f}s" if dur<60 else f"{dur/60:.1f}m"
            sr=f"{r.get('samplerate',0)//1000}k"
            dl=str(r.get("download_count",0))
            lic=r.get("license","").split("/")[-2] if "/" in r.get("license","") else "?"
            name=r.get("name","")[:30]
            self.res_lb.insert("end",f" {name:30s} {dur_s:>10s} {sr:>8s} {dl:>10s} {lic:15s}")
        self.search_status.config(text=f"Found {total} results, showing {len(self._results)}",fg=T.LIME_DK)

    def _get_selected(self):
        sel=self.res_lb.curselection()
        if sel and sel[0]<len(self._results): return self._results[sel[0]]
        return None

    def _preview(self):
        r=self._get_selected()
        if not r: return
        preview_url=r.get("previews",{}).get("preview-lq-mp3","") or r.get("previews",{}).get("preview-hq-mp3","")
        if not preview_url:
            self.search_status.config(text="No preview available",fg=T.RED); return
        self.search_status.config(text=f"Loading preview: {r.get('name','')}...",fg=T.YELLOW)
        def _do():
            try:
                fd,tmp=tempfile.mkstemp(suffix=".mp3",prefix="_lw_samp_")
                os.close(fd)
                try:
                    resp=requests.get(preview_url,timeout=15)
                    with open(tmp,"wb") as f: f.write(resp.content)
                    _audio.load(tmp); _audio.play()
                finally:
                    try: os.unlink(tmp)
                    except OSError: pass
                self.after(0,lambda:self.search_status.config(text=f"Playing: {r.get('name','')}",fg=T.LIME_DK))
            except Exception as e:
                self.after(0,lambda:self.search_status.config(text=f"Preview error: {str(e)[:60]}",fg=T.RED))
        threading.Thread(target=_do,daemon=True).start()

    def _download(self):
        r=self._get_selected()
        if not r: return
        key=self.key_var.get().strip() or self.app.settings.get("freesound_api_key","")
        if not key: messagebox.showinfo("LimeWire","Set API key first."); return
        # Freesound download requires OAuth2, use preview as fallback
        preview_url=r.get("previews",{}).get("preview-hq-mp3","")
        if not preview_url:
            messagebox.showinfo("LimeWire","No download available for this sample."); return
        out_dir=os.path.join(self.app.output_dir,"Samples")
        os.makedirs(out_dir,exist_ok=True)
        name=sanitize_filename(r.get("name","sample"))
        out_path=os.path.join(out_dir,f"{name}.mp3")
        self.search_status.config(text=f"Downloading: {name}...",fg=T.YELLOW)
        def _do():
            try:
                resp=requests.get(preview_url,timeout=30)
                with open(out_path,"wb") as f: f.write(resp.content)
                self.after(0,lambda:(self.search_status.config(text=f"Saved: {os.path.basename(out_path)}",fg=T.LIME_DK),
                    self.app.toast(f"Sample: {name}")))
            except Exception as e:
                self.after(0,lambda:self.search_status.config(text=f"Download error: {str(e)[:60]}",fg=T.RED))
        threading.Thread(target=_do,daemon=True).start()

    def _open_web(self):
        r=self._get_selected()
        if not r: return
        url=r.get("url","")
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme in ("http","https") and parsed.netloc:
            webbrowser.open(url)
