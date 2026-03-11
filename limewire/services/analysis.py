"""Audio analysis — BPM/key detection, loudness measurement, noise reduction, effects."""
import os
import numpy as np

from limewire.core.deps import (
    _ensure_librosa, _ensure_loudness,
    HAS_NOISEREDUCE, HAS_PEDALBOARD, HAS_NUMPY,
)
from limewire.services.dj_integrations import (
    KEY_NAMES, CAMELOT_MAP, CAMELOT_REVERSE,
    key_to_camelot, key_to_serato_tkey,
)

# Re-export key helpers so callers can import from analysis
__all__ = [
    "KEY_NAMES", "CAMELOT_MAP", "CAMELOT_REVERSE",
    "key_to_camelot", "key_to_serato_tkey",
    "analyze_bpm_key", "analyze_loudness", "reduce_noise",
    "apply_effects_chain", "get_harmonic_matches",
]


def analyze_bpm_key(filepath):
    """Detect BPM and musical key using librosa."""
    if not _ensure_librosa():
        return {"bpm": None, "key": None, "error": "librosa not installed"}
    # Access lazily-loaded modules via deps
    import limewire.core.deps as _d
    librosa = _d.librosa
    try:
        y, sr = librosa.load(filepath, sr=22050, mono=True, duration=120)
        # BPM
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)
        # Key detection via chroma
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_avg = chroma.mean(axis=1)
        # Major/minor estimation (Krumhansl-Schmuckler profiles)
        major_profile = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                         2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
        minor_profile = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                         2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
        best_corr_maj = -1; best_corr_min = -1
        best_maj = 0; best_min = 0
        for i in range(12):
            rolled = np.roll(chroma_avg, -i)
            cmaj = float(np.corrcoef(rolled, major_profile)[0, 1])
            cmin = float(np.corrcoef(rolled, minor_profile)[0, 1])
            if cmaj > best_corr_maj:
                best_corr_maj = cmaj; best_maj = i
            if cmin > best_corr_min:
                best_corr_min = cmin; best_min = i
        if best_corr_maj >= best_corr_min:
            key_str = f"{KEY_NAMES[best_maj]} Major"
        else:
            key_str = f"{KEY_NAMES[best_min]} Minor"
        return {"bpm": round(bpm, 1), "key": key_str}
    except Exception as e:
        return {"bpm": None, "key": None, "error": str(e)[:80]}


def analyze_loudness(filepath):
    """Measure LUFS and peak using pyloudnorm."""
    if not _ensure_loudness():
        return {"lufs": None, "peak": None, "error": "pyloudnorm not installed"}
    import limewire.core.deps as _d
    sf = _d.sf; pyln = _d.pyln
    try:
        data, rate = sf.read(filepath)
        if len(data.shape) == 1:
            data = data.reshape(-1, 1)
        meter = pyln.Meter(rate)
        lufs = meter.integrated_loudness(data)
        peak_db = 20 * np.log10(np.max(np.abs(data)) + 1e-10)
        return {"lufs": round(lufs, 1), "peak": round(peak_db, 1)}
    except Exception as e:
        return {"lufs": None, "peak": None, "error": str(e)[:80]}


def reduce_noise(filepath, output_path=None):
    """Apply AI noise reduction to audio file."""
    if not HAS_NOISEREDUCE:
        return None, "noisereduce not installed. Run: pip install noisereduce"
    try:
        if not _ensure_loudness():
            return None, "soundfile not installed"
        import limewire.core.deps as _d
        sf = _d.sf
        import noisereduce as nr
        data, rate = sf.read(filepath)
        reduced = nr.reduce_noise(y=data, sr=rate)
        if not output_path:
            base, ext = os.path.splitext(filepath)
            output_path = f"{base}_clean{ext}"
        sf.write(output_path, reduced, rate)
        return output_path, None
    except Exception as e:
        return None, str(e)[:80]


def apply_effects_chain(filepath, effects_list, output_path=None):
    """Apply a chain of pedalboard effects to audio file.

    effects_list: list of pedalboard effect instances.
    """
    if not HAS_PEDALBOARD:
        return None, "pedalboard not installed. Run: pip install pedalboard"
    try:
        import pedalboard
        with pedalboard.io.AudioFile(filepath) as f:
            audio = f.read(f.frames)
            sr = f.samplerate
        board = pedalboard.Pedalboard(effects_list)
        processed = board(audio, sample_rate=sr)
        if not output_path:
            base, ext = os.path.splitext(filepath)
            output_path = f"{base}_fx{ext}"
        with pedalboard.io.AudioFile(output_path, "w", sr, processed.shape[0]) as f:
            f.write(processed)
        return output_path, None
    except Exception as e:
        return None, str(e)[:80]


def get_harmonic_matches(key_str, library_keys):
    """Find harmonically compatible tracks from a library of {file: key_str} entries.

    Returns list of (file, key, camelot, compatibility) sorted by compatibility.
    """
    if not key_str:
        return []
    camelot = key_to_camelot(key_str)
    if not camelot:
        return []
    num = int(camelot[:-1])
    letter = camelot[-1]
    # Compatible Camelot codes: same, ±1 on wheel, same number other letter
    compat = set()
    compat.add(camelot)                               # same key
    compat.add(f"{(num % 12) + 1}{letter}")            # +1
    compat.add(f"{((num - 2) % 12) + 1}{letter}")      # -1
    other = "A" if letter == "B" else "B"
    compat.add(f"{num}{other}")                         # parallel major/minor
    results = []
    for f, k in library_keys.items():
        c = key_to_camelot(k)
        if c and c in compat:
            lvl = "perfect" if c == camelot else "harmonic"
            results.append((f, k, c, lvl))
    return results
