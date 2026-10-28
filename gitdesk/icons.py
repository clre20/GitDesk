"""Small line icons (24x24, stroke based), tinted to the current theme."""
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

P = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder-plus": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
    "clone": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "fetch": '<path d="M7 18a4 4 0 0 1-.6-7.95A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9"/><path d="M12 12v8M9 17l3 3 3-3"/>',
    "pull": '<path d="M12 4v13M6 11l6 6 6-6"/><path d="M5 21h14"/>',
    "push": '<path d="M12 20V7M6 13l6-6 6 6"/><path d="M5 3h14"/>',
    "branch": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/><path d="M6 7v10M18 9c0 5-6 4-12 8"/>',
    "merge": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="13" r="2"/><path d="M6 7v10M6 7c0 5 6 6 10 6"/>',
    "rebase": '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M6 16V9a3 3 0 0 1 3-3h7"/><path d="M13 3l3 3-3 3"/>',
    "commit": '<circle cx="12" cy="12" r="3.5"/><path d="M3 12h5.5M15.5 12H21"/>',
    "stash": '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9"/><path d="M10 13h4"/>',
    "pop": '<rect x="3" y="11" width="18" height="9" rx="2"/><path d="M12 15V3M8 7l4-4 4 4"/>',
    "terminal": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/>',
    "settings": '<path d="M19.15 10.08 L21.42 10.17 L21.42 13.83 L19.15 13.92 L18.41 15.70 L19.96 17.37 L17.37 19.96 L15.70 18.41 L13.92 19.15 L13.83 21.42 L10.17 21.42 L10.08 19.15 L8.30 18.41 L6.63 19.96 L4.04 17.37 L5.59 15.70 L4.85 13.92 L2.58 13.83 L2.58 10.17 L4.85 10.08 L5.59 8.30 L4.04 6.63 L6.63 4.04 L8.30 5.59 L10.08 4.85 L10.17 2.58 L13.83 2.58 L13.92 4.85 L15.70 5.59 L17.37 4.04 L19.96 6.63 L18.41 8.30Z"/><circle cx="12" cy="12" r="3"/>',
    "tag": '<path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9z"/><circle cx="8" cy="8" r="1.5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.5-4.5"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "refresh": '<path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>',
    "changes": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M12 12v6M9 15h6"/>',
    "cloud": '<path d="M7 18a4 4 0 0 1-.6-7.95A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9z"/>',
    "box": '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "tree": '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M5 8v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8M12 12v4"/>',
    "check": '<path d="M5 12l5 5L20 7"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "bug": '<rect x="8" y="6" width="8" height="14" rx="4"/><path d="M12 10v10M4 13h4M16 13h4M5 7l3 2M19 7l-3 2M5 19l3-2M19 19l-3-2M10 4l1 2M14 4l-1 2"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "file": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "link": '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
    "cherry": '<circle cx="7" cy="17" r="3"/><circle cx="17" cy="17" r="3"/><path d="M7 14c1-5 4-8 8-10M17 14c0-4-1-7-2-10"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "hook": '<path d="M7 3v9a5 5 0 0 0 10 0v-2"/><path d="M14 13l3-3 3 3"/>',
    "wrench": '<path d="M14.7 6.3a4 4 0 0 0 5 5L22 14l-8 8-2.3-2.3a4 4 0 0 0-5-5L4 12l8-8z"/>',
    "repo": '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v16H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5A2.5 2.5 0 0 0 6.5 23H20v-5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
}


def _svg(name, color):
    body = P.get(name, P["file"])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            f'{body}</svg>')


@lru_cache(maxsize=512)
def _icon(name, color):
    icon = QIcon()
    r = QSvgRenderer(QByteArray(_svg(name, color).encode()))
    for size in (16, 20, 24, 32, 48):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        icon.addPixmap(pm)
    return icon


def icon(name: str, color: str = None) -> QIcon:
    return _icon(name, color or theme.C["text"])


def accent(name: str) -> QIcon:
    return _icon(name, theme.C["accent"])


def app_icon() -> QIcon:
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
           '<rect x="2" y="2" width="60" height="60" rx="14" fill="#0067c0"/>'
           '<g fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round">'
           '<path d="M22 16v32M22 26c0 10 20 6 20 16"/></g>'
           '<g fill="#fff"><circle cx="22" cy="16" r="5"/><circle cx="22" cy="48" r="5"/>'
           '<circle cx="42" cy="42" r="5"/></g></svg>')
    icon_ = QIcon()
    r = QSvgRenderer(QByteArray(svg.encode()))
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, size, size))
        p.end()
        icon_.addPixmap(pm)
    return icon_


APP_ICON_SVG_SIZE = 256
