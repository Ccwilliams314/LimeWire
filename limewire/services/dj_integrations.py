"""FL Studio & Serato integration helpers."""
import os, sys, subprocess, struct

from limewire.core.deps import HAS_PYFLP, HAS_SERATO
try:
    from serato_tools.crate import Crate as SeratoCrate
except Exception:
    SeratoCrate = None
from mutagen.id3 import ID3, APIC, GEOB, TBPM, TKEY

# ── Camelot / Key helpers ────────────────────────────────────────────────────

KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CAMELOT_MAP = {
    "C Major": "8B", "C Minor": "5A", "C# Major": "3B", "C# Minor": "12A",
    "D Major": "10B", "D Minor": "7A", "D# Major": "5B", "D# Minor": "2A",
    "E Major": "12B", "E Minor": "9A", "F Major": "7B", "F Minor": "4A",
    "F# Major": "2B", "F# Minor": "11A", "G Major": "9B", "G Minor": "6A",
    "G# Major": "4B", "G# Minor": "1A", "A Major": "11B", "A Minor": "8A",
    "A# Major": "6B", "A# Minor": "3A", "B Major": "1B", "B Minor": "10A",
}
CAMELOT_REVERSE = {v: k for k, v in CAMELOT_MAP.items()}


def key_to_camelot(key_str):
    """Convert standard key notation to Camelot. 'A Minor' -> '8A'."""
    return CAMELOT_MAP.get(key_str) if key_str else None


def key_to_serato_tkey(key_str):
    """Convert 'A Minor' -> 'Am', 'C Major' -> 'C' for Serato TKEY."""
    if not key_str:
        return None
    parts = key_str.split()
    if len(parts) != 2:
        return key_str
    root, mode = parts
    return root + "m" if mode == "Minor" else root


# ── FL Studio ────────────────────────────────────────────────────────────────

FL_STUDIO_PATHS = [
    r"C:\Program Files\Image-Line\FL Studio 2025\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 2024\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 21\FL64.exe",
    r"C:\Program Files\Image-Line\FL Studio 20\FL64.exe",
    r"C:\Program Files (x86)\Image-Line\FL Studio 20\FL64.exe",
]


def find_fl_studio():
    """Auto-detect FL Studio installation path on Windows."""
    for p in FL_STUDIO_PATHS:
        if os.path.exists(p):
            return p
    if sys.platform == "win32":
        try:
            import winreg
            for kp in [r"SOFTWARE\Image-Line\FL Studio",
                       r"SOFTWARE\WOW6432Node\Image-Line\FL Studio"]:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, kp) as key:
                        val, _ = winreg.QueryValueEx(key, "InstallPath")
                        exe = os.path.join(val, "FL64.exe")
                        if os.path.exists(exe):
                            return exe
                except Exception:
                    continue
        except Exception:
            pass
    return None


def open_in_fl_studio(filepath=None, fl_path=None):
    """Launch FL Studio, optionally with a project file."""
    fl = fl_path or find_fl_studio()
    if not fl:
        return False, "FL Studio not found. Set path in Tools menu."
    try:
        if filepath and filepath.lower().endswith(".flp"):
            subprocess.Popen([fl, filepath])
        else:
            subprocess.Popen([fl])
        return True, None
    except Exception as e:
        return False, str(e)[:80]


def export_stems_for_fl(stem_dir, track_name, bpm=None, key=None, output_dir=None):
    """Organize Demucs stems for FL Studio import with numbered prefixes."""
    import shutil
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(stem_dir), "FL_Export", track_name)
    os.makedirs(output_dir, exist_ok=True)
    stem_names = {
        "vocals": "01_Vocals", "drums": "02_Drums", "bass": "03_Bass",
        "other": "04_Other", "piano": "05_Piano", "guitar": "06_Guitar",
    }
    copied = []
    for wav in sorted(os.listdir(stem_dir)):
        if not wav.endswith(".wav"):
            continue
        stem_type = os.path.splitext(wav)[0]
        prefix = stem_names.get(stem_type, stem_type)
        suffix = ""
        if bpm:
            suffix += f"_{int(bpm)}bpm"
        if key:
            suffix += f"_{key.replace(' ', '')}"
        new_name = f"{prefix}{suffix}.wav"
        shutil.copy2(os.path.join(stem_dir, wav), os.path.join(output_dir, new_name))
        copied.append(new_name)
    return output_dir, copied


def create_fl_project(stem_dir, track_name, bpm=None, output_path=None):
    """Generate an FL Studio .flp project with stems loaded on channels."""
    if not HAS_PYFLP:
        return None, "pyflp not installed. Run: pip install pyflp"
    try:
        import pyflp
        project = pyflp.Project()
        if bpm:
            project.tempo = float(bpm)
        stem_files = sorted([f for f in os.listdir(stem_dir) if f.endswith(".wav")])
        for sf in stem_files:
            stem_path = os.path.abspath(os.path.join(stem_dir, sf))
            ch = project.channels.add_sampler()
            ch.name = os.path.splitext(sf)[0].capitalize()
            ch.sample_path = stem_path
        if not output_path:
            output_path = os.path.join(os.path.dirname(stem_dir),
                                       f"{track_name}_stems.flp")
        project.save(output_path)
        return output_path, None
    except Exception as e:
        return None, str(e)[:120]


# ── Serato ───────────────────────────────────────────────────────────────────

SERATO_BASE = os.path.join(os.path.expanduser("~"), "Music", "_Serato_")
SERATO_SUBCRATES = os.path.join(SERATO_BASE, "Subcrates")


def write_serato_tags(filepath, bpm=None, key=None):
    """Write Serato-compatible BPM/Key tags to an MP3 file."""
    try:
        audio = ID3(filepath)
        if key:
            serato_key = key_to_serato_tkey(key)
            if serato_key:
                audio["TKEY"] = TKEY(encoding=3, text=serato_key)
        if bpm:
            audio["TBPM"] = TBPM(encoding=3, text=str(int(round(bpm))))
            bpm_s = f"{bpm:.2f}\x00"
            gain_s = f"0.000\x00"
            gaindb_s = f"0.000\x00"
            autotag_data = (b"\x01\x01" + bpm_s.encode("ascii")
                            + gain_s.encode("ascii") + gaindb_s.encode("ascii"))
            audio["GEOB:Serato Autotags"] = GEOB(
                encoding=0, mime="application/octet-stream",
                desc="Serato Autotags", data=autotag_data)
        audio.save()
        return True, None
    except Exception as e:
        return False, str(e)[:80]


def add_to_serato_crate(filepath, crate_name="LimeWire"):
    """Add a track to a Serato crate. Creates crate if it doesn't exist."""
    if HAS_SERATO and SeratoCrate is not None:
        try:
            crate_path = os.path.join(SERATO_SUBCRATES, f"{crate_name}.crate")
            os.makedirs(SERATO_SUBCRATES, exist_ok=True)
            crate = (SeratoCrate(crate_path)
                     if os.path.exists(crate_path) else SeratoCrate())
            crate.add_track(filepath)
            crate.save(crate_path)
            return True, None
        except Exception as e:
            return False, str(e)[:80]
    return _write_crate_manual(filepath, crate_name)


def _write_crate_tag(f, tag_name, string_value):
    encoded = string_value.encode("utf-16-be")
    f.write(tag_name.encode("ascii"))
    f.write(struct.pack(">I", len(encoded)))
    f.write(encoded)


def _write_crate_tag_raw(f, tag_name, raw_data):
    f.write(tag_name.encode("ascii"))
    f.write(struct.pack(">I", len(raw_data)))
    f.write(raw_data)


def _encode_crate_str(tag_name, string_value):
    encoded = string_value.encode("utf-16-be")
    return tag_name.encode("ascii") + struct.pack(">I", len(encoded)) + encoded


def _read_crate_tracks(crate_path):
    tracks = []
    try:
        with open(crate_path, "rb") as f:
            data = f.read()
        pos = 0
        while pos < len(data) - 8:
            tag = data[pos:pos + 4].decode("ascii", errors="replace")
            length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
            payload = data[pos + 8:pos + 8 + length]
            if tag == "otrk":
                ip = 0
                while ip < len(payload) - 8:
                    it = payload[ip:ip + 4].decode("ascii", errors="replace")
                    il = struct.unpack(">I", payload[ip + 4:ip + 8])[0]
                    if it == "ptrk":
                        tracks.append(payload[ip + 8:ip + 8 + il].decode("utf-16-be"))
                    ip += 8 + il
            pos += 8 + length
    except Exception:
        pass
    return tracks


def _write_crate_manual(filepath, crate_name="LimeWire"):
    """Write Serato .crate file manually without serato-tools."""
    crate_path = os.path.join(SERATO_SUBCRATES, f"{crate_name}.crate")
    os.makedirs(SERATO_SUBCRATES, exist_ok=True)
    existing = (_read_crate_tracks(crate_path)
                if os.path.exists(crate_path) else [])
    drive, rel_path = os.path.splitdrive(filepath)
    serato_path = rel_path.lstrip(os.sep).replace("\\", "/")
    if serato_path in existing:
        return True, "Already in crate"
    existing.append(serato_path)
    tmp_path = crate_path + ".tmp"
    with open(tmp_path, "wb") as f:
        _write_crate_tag(f, "vrsn", "1.0/Serato ScratchLive Crate")
        for track in existing:
            track_data = _encode_crate_str("ptrk", track)
            _write_crate_tag_raw(f, "otrk", track_data)
    os.replace(tmp_path, crate_path)
    return True, None
