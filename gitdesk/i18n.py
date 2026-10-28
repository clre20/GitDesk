"""Bilingual (Traditional Chinese / English) text helper.

Usage:  T("提交", "Commit")
The language is read once at startup from settings (default: English)
and can be switched in Settings (takes effect after restart).
"""
from PySide6.QtCore import QSettings

_lang = None


def current_language() -> str:
    global _lang
    if _lang is None:
        s = QSettings()
        v = s.value("ui/language", "")
        if v not in ("zh_TW", "en"):
            v = "en"   # English by default; switch on the start screen or in Settings
        _lang = v
    return _lang


def set_language(lang: str):
    QSettings().setValue("ui/language", lang)


def T(zh: str, en: str) -> str:
    return zh if current_language() == "zh_TW" else en
