"""Windows 11–like look (Fluent-ish) on both Windows and Linux, light & dark."""
from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

LIGHT = {
    "bg": "#f3f3f3", "panel": "#fbfbfb", "base": "#ffffff", "alt": "#f7f7f7",
    "text": "#1b1b1b", "muted": "#616161", "border": "#e0e0e0", "hover": "#eaeaea",
    "accent": "#0067c0", "accent_text": "#ffffff", "sel": "#cce4f7",
    "add_bg": "#e6ffec", "add_fg": "#116329", "del_bg": "#ffebe9", "del_fg": "#a40e26",
    "hunk_bg": "#ddf4ff", "hunk_fg": "#0550ae", "warn_bg": "#fff4ce", "warn_fg": "#5c4400",
    "err_bg": "#fde7e9", "ok": "#0f7b0f",
}
DARK = {
    "bg": "#202020", "panel": "#272727", "base": "#1c1c1c", "alt": "#242424",
    "text": "#ffffff", "muted": "#a0a0a0", "border": "#3a3a3a", "hover": "#2f2f2f",
    "accent": "#4cc2ff", "accent_text": "#000000", "sel": "#0e3a5a",
    "add_bg": "#12301b", "add_fg": "#7ee787", "del_bg": "#3b1219", "del_fg": "#ffa198",
    "hunk_bg": "#0c2d4a", "hunk_fg": "#79c0ff", "warn_bg": "#433519", "warn_fg": "#fce100",
    "err_bg": "#442726", "ok": "#6ccb5f",
}
GRAPH_COLORS = ["#0078d4", "#e3008c", "#107c10", "#ff8c00", "#8764b8", "#00b7c3",
                "#d13438", "#498205", "#ca5010", "#4f6bed", "#b146c2", "#038387"]

C = dict(LIGHT)


def is_dark() -> bool:
    mode = QSettings().value("ui/theme", "system")
    if mode == "dark":
        return True
    if mode == "light":
        return False
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def ui_font() -> QFont:
    fams = set(QFontDatabase.families())
    for f in ("Segoe UI Variable Text", "Segoe UI", "Microsoft JhengHei UI", "Noto Sans CJK TC",
              "Noto Sans TC", "Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans"):
        if f in fams:
            font = QFont(f, 10 if os.name != "nt" else 9)
            font.setFamilies([f, "Microsoft JhengHei UI", "Noto Sans CJK TC", "Noto Sans CJK SC"])
            return font
    return QApplication.font()


def mono_font(size=None) -> QFont:
    fams = set(QFontDatabase.families())
    size = size or int(QSettings().value("ui/diff_font_size", 10))
    for f in ("Cascadia Mono", "Cascadia Code", "Consolas", "JetBrains Mono", "DejaVu Sans Mono",
              "Noto Sans Mono", "Liberation Mono", "Monospace"):
        if f in fams:
            font = QFont(f, size)
            font.setFamilies([f, "Noto Sans Mono CJK TC", "Microsoft JhengHei", "Noto Sans CJK TC"])
            font.setStyleHint(QFont.Monospace)
            return font
    font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    font.setPointSize(size)
    return font


def apply_theme(app: QApplication):
    C.clear()
    C.update(DARK if is_dark() else LIGHT)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(ui_font())
    pal = QPalette()
    col = lambda k: QColor(C[k])
    pal.setColor(QPalette.Window, col("bg"))
    pal.setColor(QPalette.WindowText, col("text"))
    pal.setColor(QPalette.Base, col("base"))
    pal.setColor(QPalette.AlternateBase, col("alt"))
    pal.setColor(QPalette.Text, col("text"))
    pal.setColor(QPalette.Button, col("panel"))
    pal.setColor(QPalette.ButtonText, col("text"))
    pal.setColor(QPalette.Highlight, col("sel"))
    pal.setColor(QPalette.HighlightedText, col("text"))
    pal.setColor(QPalette.ToolTipBase, col("panel"))
    pal.setColor(QPalette.ToolTipText, col("text"))
    pal.setColor(QPalette.PlaceholderText, col("muted"))
    pal.setColor(QPalette.Link, col("accent"))
    pal.setColor(QPalette.Disabled, QPalette.Text, col("muted"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, col("muted"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, col("muted"))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet())


def _check_svg() -> str:
    """Write a checkmark image for checkbox indicators and return its path."""
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "gitdesk-theme")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"check-{C['accent_text'].strip('#')}.svg")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7" '
                    f'fill="none" stroke="{C["accent_text"]}" stroke-width="2" stroke-linecap="round" '
                    'stroke-linejoin="round"/></svg>')
    return p.replace("\\", "/")


def _svg_file(name: str, body: str, color: str) -> str:
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "gitdesk-theme")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"{name}-{color.strip('#')}.svg")
    if not os.path.exists(p):
        with open(p, "w") as f:
            f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path d="{body}" fill="none" '
                    f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    return p.replace("\\", "/")


def stylesheet() -> str:
    c = C
    chk = _check_svg()
    up = _svg_file("chev-up", "M4.5 10l3.5-3.5 3.5 3.5", c["muted"])
    down = _svg_file("chev-down", "M4.5 6l3.5 3.5 3.5-3.5", c["muted"])
    return f"""
    QSpinBox {{ padding-right: 20px; }}
    QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 18px;
        border: none; background: transparent; }}
    QSpinBox::up-button {{ subcontrol-position: top right; margin-top: 2px; }}
    QSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 2px; }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {c['hover']}; border-radius: 3px; }}
    QSpinBox::up-arrow {{ image: url("{up}"); width: 12px; height: 12px; }}
    QSpinBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}
    QComboBox::down-arrow {{ image: url("{down}"); width: 12px; height: 12px; }}
    QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {c['muted']};
        border-radius: 4px; background: {c['base']}; }}
    QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']};
        image: url("{chk}"); }}
    QCheckBox::indicator:disabled {{ background: {c['bg']}; border-color: {c['border']}; }}
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
                padding: 4px 6px; border-radius: 4px; }}
    QToolBar {{ background: {c['bg']}; border: none; padding: 4px 6px; spacing: 2px; }}
    QToolBar::separator {{ background: {c['border']}; width: 1px; margin: 6px 6px; }}
    QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 4px 8px;
                   color: {c['text']}; background: transparent; }}
    QToolButton:hover {{ background: {c['hover']}; }}
    QToolButton:pressed {{ background: {c['border']}; }}
    QToolButton:checked {{ background: {c['sel']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}
    QPushButton {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
                   border-bottom-color: {c['border']}; border-radius: 6px; padding: 5px 14px;
                   min-height: 20px; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:pressed {{ background: {c['border']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton[accent="true"] {{ background: {c['accent']}; color: {c['accent_text']};
                                   border: 1px solid {c['accent']}; font-weight: 600; }}
    QPushButton[accent="true"]:hover {{ background: {c['accent']}; border-color: {c['text']}; }}
    QPushButton[accent="true"]:disabled {{ background: {c['border']}; border-color: {c['border']};
                                            color: {c['muted']}; }}
    QPushButton[flat="true"] {{ border: none; background: transparent; padding: 3px 8px; }}
    QPushButton[flat="true"]:hover {{ background: {c['hover']}; }}
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox, QTextBrowser {{
        background: {c['base']}; color: {c['text']}; border: 1px solid {c['border']};
        border-radius: 6px; padding: 4px 6px; selection-background-color: {c['sel']};
        selection-color: {c['text']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid {c['border']}; border-bottom: 2px solid {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {c['panel']}; border: 1px solid {c['border']};
        selection-background-color: {c['sel']}; outline: none; }}
    QTreeView, QListView, QTableView, QTreeWidget, QListWidget, QTableWidget {{
        background: {c['base']}; color: {c['text']}; border: 1px solid {c['border']};
        border-radius: 6px; outline: none; alternate-background-color: {c['alt']}; }}
    QTreeView::item, QListView::item, QTableView::item {{ padding: 2px 4px; border: none; }}
    QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background: {c['hover']}; }}
    QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
        background: {c['sel']}; color: {c['text']}; }}
    QHeaderView::section {{ background: {c['panel']}; color: {c['muted']}; border: none;
        border-bottom: 1px solid {c['border']}; border-right: 1px solid {c['border']};
        padding: 4px 6px; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 6px 14px;
        border: none; border-bottom: 2px solid transparent; margin-right: 2px; }}
    QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}
    QTabBar::tab:hover {{ color: {c['text']}; background: {c['hover']}; border-radius: 4px; }}
    QTabBar#repoTabs::tab {{ background: {c['bg']}; border: 1px solid transparent;
        border-top-left-radius: 8px; border-top-right-radius: 8px; padding: 6px 12px; }}
    QTabBar#repoTabs::tab:selected {{ background: {c['panel']}; border: 1px solid {c['border']};
        border-bottom: none; color: {c['text']}; }}
    QToolButton#tabClose {{ padding: 1px; border-radius: 4px; }}
    QSplitter::handle {{ background: {c['bg']}; }}
    QSplitter::handle:horizontal {{ width: 5px; }}
    QSplitter::handle:vertical {{ height: 5px; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::handle:horizontal:hover {{ background: {c['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QMenuBar {{ background: {c['bg']}; color: {c['text']}; }}
    QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
    QMenuBar::item:selected {{ background: {c['hover']}; }}
    QMenu {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']};
             border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 28px 6px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['hover']}; }}
    QMenu::item:disabled {{ color: {c['muted']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
    QStatusBar {{ background: {c['bg']}; color: {c['muted']}; }}
    QDockWidget {{ color: {c['text']}; }}
    QDockWidget::title {{ background: {c['bg']}; padding: 4px 8px; }}
    QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 10px; padding-top: 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {c['muted']}; }}
    QCheckBox, QRadioButton, QLabel {{ color: {c['text']}; }}
    QLabel[muted="true"] {{ color: {c['muted']}; }}
    QLabel[h1="true"] {{ font-size: 20pt; font-weight: 600; }}
    QLabel[h2="true"] {{ font-size: 12pt; font-weight: 600; }}
    QFrame#banner {{ background: {c['warn_bg']}; border: 1px solid {c['border']}; border-radius: 8px; }}
    QFrame#banner QLabel {{ color: {c['warn_fg']}; font-weight: 600; }}
    QFrame#card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 8px; }}
    QFrame#sectionHeader {{ background: transparent; }}
    """
