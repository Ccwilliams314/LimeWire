"""EffectsPage — Pedalboard effects chain processor for audio files."""
import os, threading, tempfile, copy
import tkinter as tk
from tkinter import filedialog, messagebox

from limewire.core.theme import T
from limewire.core.config import load_json, save_json
from limewire.core.deps import HAS_PEDALBOARD, pedalboard
from limewire.core.platform import IS_MACOS
from limewire.core.audio_backend import _audio
from limewire.ui.scroll_frame import ScrollFrame
from limewire.ui.widgets import (ClassicBtn, LimeBtn, OrangeBtn, GroupBox,
                                  ClassicEntry, ClassicCombo, ClassicProgress,
                                  PageSettingsPanel, GearButton)
from limewire.ui.toast import show_toast
from limewire.services.plugins import _plugin_manager


class EffectsPage(ScrollFrame):
    """Pedalboard effects chain processor for audio files."""
    def __init__(self, parent, app):
        super().__init__(parent); self.app = app
        self._chain = []; self._undo_stack = []; self._redo_stack = []
        self._build(self.inner)

    def _build(self, p):
        fg = GroupBox(p, "Source Audio File"); fg.pack(fill="x", padx=10, pady=(10, 6))
        fr = tk.Frame(fg, bg=T.BG); fr.pack(fill="x")
        self.file_var = tk.StringVar()
        ClassicEntry(fr, self.file_var, width=55).pack(
            side="left", fill="x", expand=True, ipady=2, padx=(0, 8))
        ClassicBtn(fr, "Browse...", self._browse).pack(side="left")
        self._settings_panel = PageSettingsPanel(p, "effects", self.app, [
            ("preview_duration_s", "Preview Duration (s)", "int", 5, {"min": 1, "max": 30}),
            ("undo_max", "Undo Stack Size", "int", 30, {"min": 10, "max": 100}),
            ("output_suffix", "Output Suffix", "str", "_fx", None),
        ])
        self._gear = GearButton(fr, self._settings_panel)
        self._gear.pack(side="right")

        eg = GroupBox(p, "Effects Chain"); eg.pack(fill="x", padx=10, pady=(0, 6))
        if not HAS_PEDALBOARD:
            tk.Label(eg, text="pedalboard not installed. Run: pip install pedalboard",
                     font=T.F_BODY, bg=T.BG, fg=T.RED).pack(fill="x", padx=6, pady=6)
            return

        # Effect selector
        ar = tk.Frame(eg, bg=T.BG); ar.pack(fill="x", pady=(0, 6))
        tk.Label(ar, text="Add Effect:", font=T.F_BOLD, bg=T.BG, fg=T.TEXT).pack(
            side="left", padx=(0, 6))
        self._fx_names = [
            "Compressor", "Reverb", "Delay", "Distortion", "Gain", "NoiseGate",
            "HighpassFilter", "LowpassFilter", "HighShelfFilter", "LowShelfFilter",
            "Chorus", "Phaser",
        ]
        # Add loaded plugins to effects list
        for p_ in _plugin_manager.list_plugins():
            plugin_label = f"\U0001F9E9 {p_.name}"
            if plugin_label not in self._fx_names:
                self._fx_names.append(plugin_label)
        self._fx_var = tk.StringVar(value="Compressor")
        ClassicCombo(ar, self._fx_var, self._fx_names, width=16).pack(
            side="left", padx=(0, 6))
        LimeBtn(ar, "Add", self._add_fx).pack(side="left", padx=(0, 6))
        OrangeBtn(ar, "Clear All", self._clear_fx).pack(side="left", padx=(0, 6))
        ClassicBtn(ar, "Save Preset", self._save_preset).pack(side="left", padx=(0, 6))
        ClassicBtn(ar, "Load Preset", self._load_preset).pack(side="left", padx=(0, 6))
        ClassicBtn(ar, "\u21a9 Undo", self._undo).pack(side="left", padx=(0, 6))
        ClassicBtn(ar, "\u21aa Redo", self._redo).pack(side="left", padx=(0, 6))

        # Chain display
        self.chain_frame = tk.Frame(eg, bg=T.BG); self.chain_frame.pack(fill="x")
        self._render_chain()

        # Parameters
        pg = GroupBox(p, "Effect Parameters"); pg.pack(fill="x", padx=10, pady=(0, 6))
        self.param_frame = tk.Frame(pg, bg=T.BG); self.param_frame.pack(fill="x")
        self._param_vars = {}

        # Actions
        ag = GroupBox(p, "Process"); ag.pack(fill="x", padx=10, pady=(0, 6))
        abr = tk.Frame(ag, bg=T.BG); abr.pack(fill="x")
        LimeBtn(abr, "Apply Effects", self._apply, width=18).pack(
            side="left", padx=(0, 8))
        ClassicBtn(abr, "Preview (5s)", self._preview).pack(side="left", padx=(0, 8))
        OrangeBtn(abr, "Load VST3 Plugin", self._load_vst).pack(
            side="left", padx=(0, 8))
        ClassicBtn(abr, "Reload Plugins", self._reload_plugins).pack(side="left")
        self.fx_status = tk.Label(ag, text="Add effects above, then click Apply",
                                  font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM, anchor="w")
        self.fx_status.pack(fill="x", pady=(4, 0))
        self.fx_prog = ClassicProgress(ag); self.fx_prog.pack(fill="x", pady=(4, 0))

    def _browse(self):
        f = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a"), ("All", "*.*")])
        if f:
            self.file_var.set(f)

    # ── Undo / Redo ───────────────────────────────────────────────────────────
    def _push_undo(self):
        self._undo_stack.append(copy.deepcopy(self._chain))
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self):
        if not self._undo_stack:
            show_toast(self.app, "Nothing to undo", "info"); return
        self._redo_stack.append(copy.deepcopy(self._chain))
        self._chain = self._undo_stack.pop()
        self._render_chain(); show_toast(self.app, "Undone", "info")

    def _redo(self):
        if not self._redo_stack:
            show_toast(self.app, "Nothing to redo", "info"); return
        self._undo_stack.append(copy.deepcopy(self._chain))
        self._chain = self._redo_stack.pop()
        self._render_chain(); show_toast(self.app, "Redone", "info")

    # ── Chain management ──────────────────────────────────────────────────────
    def _add_fx(self):
        self._push_undo()
        name = self._fx_var.get()
        self._chain.append({"name": name, "params": self._default_params(name)})
        self._render_chain()

    def _default_params(self, name):
        defaults = {
            "Compressor": {"threshold_db": -20, "ratio": 4,
                           "attack_ms": 5, "release_ms": 100},
            "Reverb": {"room_size": 0.5, "wet_level": 0.3},
            "Delay": {"delay_seconds": 0.3, "feedback": 0.4, "mix": 0.3},
            "Distortion": {"drive_db": 15},
            "Gain": {"gain_db": 0},
            "NoiseGate": {"threshold_db": -40},
            "HighpassFilter": {"cutoff_frequency_hz": 100},
            "LowpassFilter": {"cutoff_frequency_hz": 8000},
            "HighShelfFilter": {"cutoff_frequency_hz": 4000, "gain_db": 3},
            "LowShelfFilter": {"cutoff_frequency_hz": 300, "gain_db": 3},
            "Chorus": {"rate_hz": 1.5, "depth": 0.5, "mix": 0.5},
            "Phaser": {"rate_hz": 1.0, "depth": 0.5, "mix": 0.5},
        }
        return defaults.get(name, {})

    def _render_chain(self):
        for w in self.chain_frame.winfo_children():
            w.destroy()
        if not self._chain:
            tk.Label(self.chain_frame, text="No effects in chain. Add effects above.",
                     font=T.F_SMALL, bg=T.BG, fg=T.TEXT_DIM).pack(pady=4)
            return
        for i, fx in enumerate(self._chain):
            r = tk.Frame(self.chain_frame, bg=T.CARD_BG, relief="flat", bd=0,
                         highlightthickness=1, highlightbackground=T.CARD_BORDER)
            r.pack(fill="x", pady=2, padx=4)
            tk.Label(r, text=f"  {i + 1}. {fx['name']}", font=T.F_BOLD,
                     bg=T.CARD_BG, fg=T.LIME).pack(side="left", padx=4)
            # Show key params inline
            params_str = " | ".join(f"{k}={v}" for k, v in fx["params"].items())
            tk.Label(r, text=params_str, font=T.F_SMALL, bg=T.CARD_BG,
                     fg=T.TEXT_DIM).pack(side="left", padx=8)
            ClassicBtn(r, "Edit", lambda i=i: self._edit_fx(i)).pack(
                side="right", padx=2)
            ClassicBtn(r, "X", lambda i=i: self._remove_fx(i)).pack(
                side="right", padx=2)

    def _remove_fx(self, idx):
        if idx < len(self._chain):
            self._push_undo(); self._chain.pop(idx); self._render_chain()

    def _edit_fx(self, idx):
        if idx >= len(self._chain):
            return
        fx = self._chain[idx]
        # Show edit dialog
        dlg = tk.Toplevel(self); dlg.title(f"Edit {fx['name']}")
        dlg.geometry("350x300")
        dlg.configure(bg=T.BG); dlg.transient(self); dlg.grab_set()
        tk.Label(dlg, text=fx["name"], font=T.F_HEADER, bg=T.BG,
                 fg=T.TEXT).pack(pady=(10, 6))
        vars_ = {}
        for k, v in fx["params"].items():
            r = tk.Frame(dlg, bg=T.BG); r.pack(fill="x", padx=20, pady=3)
            tk.Label(r, text=f"{k}:", font=T.F_BODY, bg=T.BG, fg=T.TEXT,
                     width=20, anchor="w").pack(side="left")
            sv = tk.StringVar(value=str(v)); vars_[k] = sv
            ClassicEntry(r, sv, width=10).pack(side="left", ipady=1)

        def _save():
            self._push_undo()
            for k, sv in vars_.items():
                try:
                    fx["params"][k] = float(sv.get())
                except Exception:
                    pass
            self._render_chain(); dlg.destroy()
        LimeBtn(dlg, "Save", _save).pack(pady=10)

    def _clear_fx(self):
        self._push_undo(); self._chain = []; self._render_chain()

    # ── Presets ───────────────────────────────────────────────────────────────
    def _save_preset(self):
        if not self._chain:
            show_toast(self.app, "No effects to save", "warning"); return
        f = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Effect Preset", "*.json")],
            initialfile="my_preset.json")
        if not f:
            return
        try:
            save_json(f, {"version": 1, "chain": self._chain})
            show_toast(self.app, f"Preset saved: {os.path.basename(f)}", "success")
        except Exception as e:
            show_toast(self.app, f"Save failed: {e}", "error")

    def _load_preset(self):
        f = filedialog.askopenfilename(
            filetypes=[("Effect Preset", "*.json"), ("All", "*.*")])
        if not f:
            return
        try:
            data = load_json(f, {})
            chain = data.get("chain", []) if isinstance(data, dict) else data
            if not isinstance(chain, list):
                show_toast(self.app, "Invalid preset file", "error"); return
            self._push_undo(); self._chain = chain; self._render_chain()
            show_toast(self.app, f"Loaded {len(chain)} effects from preset", "success")
        except Exception as e:
            show_toast(self.app, f"Load failed: {e}", "error")

    # ── VST loading ───────────────────────────────────────────────────────────
    def _load_vst(self):
        """Load a VST3/AU plugin file into the effects chain."""
        if not HAS_PEDALBOARD:
            show_toast(self.app, "pedalboard required for VST hosting", "error")
            return
        ftypes = [("VST3 Plugin", "*.vst3")]
        if IS_MACOS:
            ftypes.append(("Audio Unit", "*.component"))
        ftypes.append(("All", "*.*"))
        f = filedialog.askopenfilename(filetypes=ftypes,
                                       title="Select VST3/AU Plugin")
        if not f:
            return
        try:
            # Test loading the plugin
            vst = pedalboard.load_plugin(f)
            name = os.path.splitext(os.path.basename(f))[0]
            # Get plugin parameters
            params = {}
            for param_name in vst.parameters:
                p_ = vst.parameters[param_name]
                params[param_name] = getattr(p_, "default_value", 0.5)
            self._push_undo()
            self._chain.append({
                "name": f"VST:{name}", "params": params,
                "vst_path": f, "user_loaded": True,
            })
            self._render_chain()
            show_toast(self.app, f"Loaded VST: {name}", "success")
        except Exception as e:
            show_toast(self.app, f"VST load failed: {str(e)[:60]}", "error")

    def _reload_plugins(self):
        """Reload custom plugins from plugins directory."""
        _plugin_manager.discover()
        # Rebuild effects list
        base_fx = [
            "Compressor", "Reverb", "Delay", "Distortion", "Gain", "NoiseGate",
            "HighpassFilter", "LowpassFilter", "HighShelfFilter", "LowShelfFilter",
            "Chorus", "Phaser",
        ]
        for p_ in _plugin_manager.list_plugins():
            label = f"\U0001F9E9 {p_.name}"
            if label not in base_fx:
                base_fx.append(label)
        self._fx_names = base_fx
        errors = _plugin_manager.get_errors()
        if errors:
            show_toast(self.app, f"Loaded plugins ({len(errors)} errors)", "warning")
        else:
            show_toast(self.app,
                       f"Plugins reloaded: {len(_plugin_manager.list_plugins())} loaded",
                       "success")

    # ── Board building ────────────────────────────────────────────────────────
    _ALLOWED_EFFECTS = frozenset({
        "Reverb", "Compressor", "Delay", "Distortion", "Gain",
        "HighpassFilter", "LowpassFilter", "PeakFilter", "Phaser", "Chorus",
        "Limiter", "NoiseGate", "Clipping", "GSMFullRateCompressor",
        "MP3Compressor", "LadderFilter", "IIRFilter", "Bitcrush",
        "HighShelfFilter", "LowShelfFilter", "Convolution", "Resample",
    })

    def _build_board(self):
        """Build pedalboard.Pedalboard from current chain."""
        effects = []
        for fx in self._chain:
            # Handle VST plugins -- only from user-initiated load, not from presets
            if (fx["name"].startswith("VST:") and fx.get("vst_path")
                    and fx.get("user_loaded")):
                try:
                    vst = pedalboard.load_plugin(fx["vst_path"])
                    for k, v in fx.get("params", {}).items():
                        try:
                            setattr(vst, k, v)
                        except Exception:
                            pass
                    effects.append(vst); continue
                except Exception:
                    continue
            # Handle custom plugins (processed separately in _apply)
            if fx["name"].startswith("\U0001F9E9 "):
                continue
            if fx["name"] not in self._ALLOWED_EFFECTS:
                self.fx_status.config(
                    text=f"Blocked unknown effect: {fx['name']}", fg=T.RED)
                continue
            cls = getattr(pedalboard, fx["name"], None)
            if cls:
                # Map param names
                params = {}
                for k, v in fx["params"].items():
                    # Convert _ms to _seconds for pedalboard API
                    if k.endswith("_ms"):
                        params[k.replace("_ms", "_seconds")] = v / 1000.0
                    else:
                        params[k] = v
                try:
                    effects.append(cls(**params))
                except Exception as e:
                    self.fx_status.config(
                        text=f"Error creating {fx['name']}: {e}", fg=T.RED)
                    return None
        return pedalboard.Pedalboard(effects)

    # ── Apply / Preview ───────────────────────────────────────────────────────
    def _apply(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("LimeWire", "Select an audio file first."); return
        if not self._chain:
            messagebox.showinfo("LimeWire", "Add effects to the chain first."); return
        board = self._build_board()
        if not board:
            return
        self.fx_status.config(text="Processing...", fg=T.YELLOW)
        self.fx_prog.configure(value=0)

        def _do():
            try:
                base, ext = os.path.splitext(path)
                out = f"{base}_fx{ext}"
                with pedalboard.io.AudioFile(path) as f:
                    audio = f.read(f.frames); sr = f.samplerate
                self.after(0, lambda: self.fx_prog.configure(value=50))
                processed = board(audio, sample_rate=sr)
                with pedalboard.io.AudioFile(out, "w", sr, processed.shape[0]) as f:
                    f.write(processed)
                self.after(0, lambda: (
                    self.fx_prog.configure(value=100),
                    self.fx_status.config(
                        text=f"Saved: {os.path.basename(out)}", fg=T.LIME_DK),
                    self.app.toast(f"Effects applied: {os.path.basename(out)}")))
            except Exception as e:
                self.after(0, lambda: self.fx_status.config(
                    text=f"Error: {str(e)[:80]}", fg=T.RED))
        threading.Thread(target=_do, daemon=True).start()

    def _preview(self):
        path = self.file_var.get()
        if not path or not os.path.exists(path) or not self._chain:
            return
        board = self._build_board()
        if not board:
            return
        self.fx_status.config(text="Generating preview...", fg=T.YELLOW)

        def _do():
            try:
                with pedalboard.io.AudioFile(path) as f:
                    sr = f.samplerate
                    chunk = f.read(min(sr * 5, f.frames))
                processed = board(chunk, sample_rate=sr)
                fd, preview_path = tempfile.mkstemp(suffix=".wav", prefix="_lw_fx_")
                os.close(fd)
                try:
                    with pedalboard.io.AudioFile(preview_path, "w", sr,
                                                 processed.shape[0]) as f:
                        f.write(processed)
                    _audio.load(preview_path); _audio.play()
                finally:
                    try:
                        os.unlink(preview_path)
                    except OSError:
                        pass
                self.after(0, lambda: self.fx_status.config(
                    text="Playing 5s preview...", fg=T.LIME_DK))
            except Exception as e:
                self.after(0, lambda: self.fx_status.config(
                    text=f"Preview error: {str(e)[:80]}", fg=T.RED))
        threading.Thread(target=_do, daemon=True).start()
