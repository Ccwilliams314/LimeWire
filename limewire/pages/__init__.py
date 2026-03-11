"""Page modules — each tab's ScrollFrame subclass lives in its own file."""

from limewire.pages.search import SearchPage
from limewire.pages.analyze import AnalyzePage
from limewire.pages.stems import StemsPage
from limewire.pages.download import DownloadPage
from limewire.pages.playlist import PlaylistPage
from limewire.pages.converter import ConverterPage
from limewire.pages.player import PlayerPage
from limewire.pages.effects import EffectsPage
from limewire.pages.discovery import DiscoveryPage
from limewire.pages.samples import SamplesPage
from limewire.pages.editor import EditorPage
from limewire.pages.recorder import RecorderPage
from limewire.pages.spectrogram import SpectrogramPage
from limewire.pages.pitchtime import PitchTimePage
from limewire.pages.remixer import RemixerPage
from limewire.pages.batch_processor import BatchProcessorPage
from limewire.pages.scheduler import SchedulerPage
from limewire.pages.history import HistoryPage
from limewire.pages.settings import SettingsPage
from limewire.pages.cover_art import CoverArtPage
from limewire.pages.lyrics import LyricsPage
from limewire.pages.visualizer import VisualizerPage
from limewire.pages.library import LibraryPage
from limewire.pages.dj import DJPage

__all__ = [
    "SearchPage", "AnalyzePage", "StemsPage", "DownloadPage",
    "PlaylistPage", "ConverterPage", "PlayerPage", "EffectsPage",
    "DiscoveryPage", "SamplesPage", "EditorPage", "RecorderPage",
    "SpectrogramPage", "PitchTimePage", "RemixerPage",
    "BatchProcessorPage", "SchedulerPage", "HistoryPage",
    "SettingsPage", "CoverArtPage",
    "LyricsPage", "VisualizerPage", "LibraryPage", "DJPage",
]
