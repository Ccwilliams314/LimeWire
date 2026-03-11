"""Audio processing — waveform, demucs, pydub helpers, spectrogram, pitch/time."""
import os, sys, subprocess, struct

import numpy as np
from PIL import Image

from limewire.core.deps import (
    HAS_NUMPY, HAS_DEMUCS, HAS_FFMPEG,
    _ensure_librosa, _ensure_loudness, _ensure_pydub, _ensure_rubberband,
)
from limewire.core.constants import (
    WAVEFORM_W, WAVEFORM_H,
    SPECTROGRAM_FFT, SPECTROGRAM_HOP, SPECTROGRAM_CMAP,
)


def generate_waveform_data(filepath, width=WAVEFORM_W, height=WAVEFORM_H):
    """Generate waveform amplitude data for visualization using ffmpeg."""
    try:
        cmd = ["ffmpeg", "-i", filepath, "-ac", "1", "-ar", "8000",
               "-f", "s16le", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        raw = r.stdout
        if not raw:
            return []
        if HAS_NUMPY:
            samples = np.frombuffer(raw, dtype=np.int16)
            chunk = max(1, len(samples) // width)
            trim = (len(samples) // chunk) * chunk
            reshaped = np.abs(samples[:trim].reshape(-1, chunk))
            bars = (reshaped.max(axis=1) / 32768.0).tolist()
        else:
            samples = struct.unpack(f"<{len(raw) // 2}h", raw)
            chunk = max(1, len(samples) // width)
            bars = []
            for i in range(0, len(samples), chunk):
                seg = samples[i:i + chunk]
                if seg:
                    peak = max(abs(min(seg)), abs(max(seg)))
                    bars.append(peak / 32768.0)
        return bars[:width]
    except Exception:
        return []


# ── Demucs stem separation ───────────────────────────────────────────────────

def _demucs_cli_error(e):
    """Extract a useful error message from a subprocess error."""
    if hasattr(e, "stderr") and e.stderr:
        msg = (e.stderr.decode("utf-8", errors="replace")
               if isinstance(e.stderr, bytes) else str(e.stderr))
        lines = [l.strip() for l in msg.strip().splitlines() if l.strip()]
        return "\n".join(lines[-5:]) if lines else str(e)[:200]
    return str(e)[:200]


def _patch_torchaudio_save():
    """Monkey-patch torchaudio.save to use soundfile when torchcodec is broken.

    torchaudio 2.9+ hardcodes save() → save_with_torchcodec() which needs
    FFmpeg shared DLLs (not just the CLI). Patch it to use soundfile instead.
    """
    try:
        import torchaudio
        try:
            import torchcodec  # noqa
            return  # torchcodec works, no patch needed
        except Exception:
            pass
        # torchcodec broken — replace save with soundfile-based version
        if _ensure_loudness():
            import limewire.core.deps as _d
            _sf = _d.sf
            import torch
            _orig_save = torchaudio.save

            def _sf_save(uri, src, sample_rate, channels_first=True, **kw):
                if isinstance(src, torch.Tensor):
                    data = src.numpy()
                    if channels_first and data.ndim == 2:
                        data = data.T
                    _sf.write(str(uri), data, sample_rate)
                else:
                    _orig_save(uri, src, sample_rate,
                               channels_first=channels_first, **kw)

            torchaudio.save = _sf_save
    except Exception:
        pass


def run_demucs(filepath, output_dir, model="htdemucs", two_stems=None):
    """Run Demucs stem separation."""
    _patch_torchaudio_save()

    def _build_cmd():
        cmd = [sys.executable, "-m", "demucs", "-n", model, "-o", output_dir]
        if two_stems:
            cmd += ["--two-stems", two_stems]
        cmd.append(filepath)
        return cmd

    if not HAS_DEMUCS:
        try:
            subprocess.run(_build_cmd(), check=True,
                           capture_output=True, timeout=600)
            return True
        except Exception as e:
            return (f"Demucs not installed. Run: pip install demucs\n"
                    f"{_demucs_cli_error(e)}")
    # Try Python API first, catch SystemExit too
    try:
        import demucs.separate
        args = ["-n", model, "-o", output_dir]
        if two_stems:
            args += ["--two-stems", two_stems]
        args.append(filepath)
        demucs.separate.main(args)
        return True
    except (Exception, SystemExit) as e:
        api_err = str(e)[:200]
        try:
            subprocess.run(_build_cmd(), check=True,
                           capture_output=True, timeout=600)
            return True
        except Exception as e2:
            cli_err = _demucs_cli_error(e2)
            return f"Python API: {api_err}\nCLI: {cli_err}"


# ── Pydub helpers ────────────────────────────────────────────────────────────

def load_audio_pydub(filepath):
    """Load audio file into pydub AudioSegment."""
    if not _ensure_pydub():
        return None, "pydub not installed. Run: pip install pydub"
    if not HAS_FFMPEG:
        return None, "FFmpeg required for audio loading"
    try:
        import limewire.core.deps as _d
        AudioSegment = _d.AudioSegment
        return AudioSegment.from_file(filepath), None
    except Exception as e:
        return None, str(e)[:80]


def export_audio_pydub(seg, path, fmt="mp3"):
    """Export pydub AudioSegment to file."""
    try:
        seg.export(path, format=fmt)
        return path, None
    except Exception as e:
        return None, str(e)[:80]


def audio_segment_to_waveform(seg, width=600, height=80):
    """Convert pydub AudioSegment to list of bar heights for waveform drawing."""
    samples = seg.get_array_of_samples()
    if not samples:
        return []
    chunk = max(1, len(samples) // width)
    bars = []
    for i in range(0, len(samples), chunk):
        sl = samples[i:i + chunk]
        if sl:
            bars.append(max(abs(min(sl)), abs(max(sl))))
    mx = max(bars) if bars else 1
    return [int(v / max(1, mx) * height) for v in bars]


# ── Spectrogram ──────────────────────────────────────────────────────────────

def _get_colormap(name="viridis"):
    """Generate 256x3 RGB LUT for spectrogram coloring (no matplotlib needed)."""
    anchors = {
        "viridis": [(68, 1, 84), (59, 82, 139), (33, 145, 140),
                    (94, 201, 98), (253, 231, 37)],
        "magma":   [(0, 0, 4), (81, 18, 124), (183, 55, 121),
                    (254, 159, 109), (252, 253, 191)],
        "plasma":  [(13, 8, 135), (126, 3, 168), (204, 71, 120),
                    (248, 149, 64), (240, 249, 33)],
        "inferno": [(0, 0, 4), (87, 16, 110), (188, 55, 84),
                    (249, 142, 9), (252, 255, 164)],
    }
    pts = anchors.get(name, anchors["viridis"])
    lut = np.zeros((256, 3), dtype=np.uint8)
    seg_len = 256 // (len(pts) - 1)
    for i in range(len(pts) - 1):
        for j in range(seg_len):
            t = j / seg_len
            idx = i * seg_len + j
            if idx < 256:
                lut[idx] = [int(pts[i][c] + (pts[i + 1][c] - pts[i][c]) * t)
                            for c in range(3)]
    for idx in range((len(pts) - 1) * seg_len, 256):
        lut[idx] = pts[-1]
    return lut


def generate_spectrogram_image(filepath, fft_size=SPECTROGRAM_FFT,
                                hop=SPECTROGRAM_HOP, cmap=SPECTROGRAM_CMAP,
                                width=800, height=400):
    """Generate spectrogram as PIL Image using librosa + custom colormap."""
    if not _ensure_librosa():
        return None, "librosa not installed"
    if not HAS_NUMPY:
        return None, "numpy not installed"
    import limewire.core.deps as _d
    librosa = _d.librosa
    try:
        y, sr = librosa.load(filepath, sr=22050, mono=True)
        S = librosa.amplitude_to_db(
            np.abs(librosa.stft(y, n_fft=fft_size, hop_length=hop)),
            ref=np.max)
        S_norm = np.clip((S + 80) / 80 * 255, 0, 255).astype(np.uint8)
        lut = _get_colormap(cmap)
        rgb = lut[S_norm]
        img = Image.fromarray(rgb[::-1].astype(np.uint8))
        return img.resize((width, height), Image.LANCZOS), None
    except Exception as e:
        return None, str(e)[:80]


# ── Pitch / Time ─────────────────────────────────────────────────────────────

def pitch_shift_audio(filepath, semitones, output_path=None):
    """Shift pitch by N semitones using pyrubberband."""
    if not _ensure_rubberband():
        return None, "pyrubberband not installed. Run: pip install pyrubberband"
    if not _ensure_loudness():
        return None, "soundfile not installed"
    import limewire.core.deps as _d
    sf = _d.sf; pyrubberband = _d.pyrubberband
    try:
        y, sr = sf.read(filepath)
        shifted = pyrubberband.pitch_shift(y, sr, semitones)
        if not output_path:
            base, ext = os.path.splitext(filepath)
            output_path = f"{base}_pitch{semitones:+d}.wav"
        sf.write(output_path, shifted, sr)
        return output_path, None
    except Exception as e:
        return None, str(e)[:80]


def time_stretch_audio(filepath, rate, output_path=None):
    """Time-stretch audio by rate factor using pyrubberband."""
    if not _ensure_rubberband():
        return None, "pyrubberband not installed. Run: pip install pyrubberband"
    if not _ensure_loudness():
        return None, "soundfile not installed"
    import limewire.core.deps as _d
    sf = _d.sf; pyrubberband = _d.pyrubberband
    try:
        y, sr = sf.read(filepath)
        stretched = pyrubberband.time_stretch(y, sr, rate)
        if not output_path:
            base, ext = os.path.splitext(filepath)
            output_path = f"{base}_tempo{rate:.2f}x.wav"
        sf.write(output_path, stretched, sr)
        return output_path, None
    except Exception as e:
        return None, str(e)[:80]


def _srt_timestamp(s):
    """Format seconds to SRT timestamp (HH:MM:SS,mmm)."""
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
