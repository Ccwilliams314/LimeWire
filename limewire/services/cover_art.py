"""Cover art utilities — extract, embed, prepare, and fetch album artwork."""
import base64
from io import BytesIO

import requests
import mutagen
from mutagen.id3 import APIC
from PIL import Image

from limewire.core.deps import HAS_MB

# MusicBrainz is optional
try:
    import musicbrainzngs
    HAS_MUSICBRAINZ = True
except Exception:
    musicbrainzngs = None
    HAS_MUSICBRAINZ = False


def extract_cover_art(filepath):
    """Extract embedded cover art bytes from any audio format.

    Returns (bytes, mime_str) or (None, None).
    """
    try:
        audio = mutagen.File(filepath)
        if audio is None:
            return None, None
        # MP3 / WAV — ID3 APIC
        if hasattr(audio, 'tags') and audio.tags:
            for k in audio.tags:
                if str(k).startswith("APIC"):
                    frame = audio.tags[k]
                    return frame.data, getattr(frame, 'mime', 'image/jpeg')
        # FLAC pictures
        if hasattr(audio, 'pictures') and audio.pictures:
            pic = audio.pictures[0]
            return pic.data, pic.mime or 'image/jpeg'
        # M4A — covr atom
        if hasattr(audio, 'tags') and audio.tags and 'covr' in audio.tags:
            covr = audio.tags['covr']
            if covr:
                return bytes(covr[0]), 'image/jpeg'
        # OGG — metadata_block_picture
        if (hasattr(audio, 'tags') and audio.tags
                and 'metadata_block_picture' in audio):
            from mutagen.flac import Picture
            raw = base64.b64decode(audio['metadata_block_picture'][0])
            pic = Picture(raw)
            return pic.data, pic.mime or 'image/jpeg'
    except Exception:
        pass
    return None, None


def embed_cover_art(filepath, img_bytes, mime='image/jpeg'):
    """Embed cover art into any supported audio file."""
    audio = mutagen.File(filepath)
    if audio is None:
        raise ValueError(f"Unsupported: {filepath}")
    from mutagen.mp3 import MP3 as _MP3
    from mutagen.flac import FLAC as _FLAC, Picture as _Picture
    from mutagen.mp4 import MP4 as _MP4, MP4Cover as _MP4Cover
    from mutagen.oggvorbis import OggVorbis as _OGG
    from mutagen.wave import WAVE as _WAVE

    if isinstance(audio, (_MP3, _WAVE)):
        try:
            audio.add_tags()
        except Exception:
            pass
        audio.tags.delall("APIC")
        audio.tags.add(APIC(encoding=3, mime=mime, type=3,
                            desc="Cover", data=img_bytes))
    elif isinstance(audio, _FLAC):
        pic = _Picture()
        pic.type = 3; pic.mime = mime; pic.desc = "Cover"; pic.data = img_bytes
        audio.clear_pictures()
        audio.add_picture(pic)
    elif isinstance(audio, _OGG):
        pic = _Picture()
        pic.type = 3; pic.mime = mime; pic.desc = "Cover"; pic.data = img_bytes
        try:
            im = Image.open(BytesIO(img_bytes))
            pic.width, pic.height = im.size
            pic.depth = 24
        except Exception:
            pic.width = pic.height = 500
            pic.depth = 24
        encoded = base64.b64encode(pic.write()).decode('ascii')
        audio['metadata_block_picture'] = [encoded]
    elif isinstance(audio, _MP4):
        fmt = (_MP4Cover.FORMAT_PNG if mime == 'image/png'
               else _MP4Cover.FORMAT_JPEG)
        audio.tags['covr'] = [_MP4Cover(img_bytes, imageformat=fmt)]
    else:
        raise ValueError(f"Unsupported tag type: {type(audio)}")
    audio.save()


def prepare_cover_image(img_bytes, size=500, quality=90):
    """Center-crop to square, resize, return JPEG bytes."""
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img = img.resize((size, size), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def fetch_itunes_art(query, size=600):
    """Fetch album art from iTunes Search API (no auth). Returns bytes or None."""
    try:
        url = "https://itunes.apple.com/search"
        resp = requests.get(url, params={"term": query, "entity": "album",
                                         "limit": 5}, timeout=10)
        if resp.status_code != 200:
            return None
        for r in resp.json().get("results", []):
            art_url = r.get("artworkUrl100", "")
            if art_url:
                art_url = art_url.replace("100x100bb", f"{size}x{size}bb")
                img_resp = requests.get(art_url, timeout=15)
                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                    return img_resp.content
    except Exception:
        pass
    return None


def fetch_musicbrainz_art(query, size=500):
    """Fetch cover art from MusicBrainz Cover Art Archive (no auth).

    Returns bytes or None.
    """
    if not HAS_MUSICBRAINZ or musicbrainzngs is None:
        return None
    try:
        results = musicbrainzngs.search_releases(query=query, limit=5)
        for rel in results.get("release-list", []):
            mbid = rel["id"]
            try:
                data = musicbrainzngs.get_image_front(mbid, size=str(size))
                if data and len(data) > 1000:
                    return data
            except Exception:
                continue
    except Exception:
        pass
    return None
