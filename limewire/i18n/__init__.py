"""Internationalization — translations and language management."""
from limewire.i18n.strings import _LANG_STRINGS

_CURRENT_LANG = "en"

def _t(key):
    """Get translated string for current language. Falls back to English."""
    return _LANG_STRINGS.get(_CURRENT_LANG, _LANG_STRINGS["en"]).get(key,
           _LANG_STRINGS["en"].get(key, key))

def set_language(lang):
    global _CURRENT_LANG
    if lang in _LANG_STRINGS: _CURRENT_LANG = lang

SUPPORTED_LANGUAGES = list(_LANG_STRINGS.keys())
