"""Audio playback backend — pyglet wrapper."""
import os
from limewire.core.deps import pyglet


class AudioPlayer:
    """Thin wrapper around pyglet.media.Player for audio playback."""
    def __init__(self):
        self._player = None
        self._volume = 0.8

    def load(self, path):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Audio file not found: {path}")
        self.stop()
        src = pyglet.media.load(path)
        self._player = pyglet.media.Player()
        self._player.volume = self._volume
        self._player.queue(src)

    def play(self, start=0):
        if self._player:
            try:
                if start > 0: self._player.seek(start)
            except Exception: pass
            self._player.play()

    def pause(self):
        if self._player:
            self._player.pause()

    def stop(self):
        if self._player:
            try:
                self._player.pause()
                self._player.delete()
            except Exception: pass
            self._player = None

    def set_volume(self, v):
        self._volume = v
        if self._player:
            self._player.volume = v

    def get_busy(self):
        return self._player.playing if self._player else False

    def get_pos(self):
        return self._player.time if self._player else 0


# Singleton
_audio = AudioPlayer()
