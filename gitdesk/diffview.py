"""Unified diff viewer with hunk- and line-level stage / unstage / discard."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QPainter, QSyntaxHighlighter, QTextBlockFormat,
                           QTextCharFormat, QTextCursor, QTextFormat, QTextOption)
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QMenu, QPlainTextEdit,
                               QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget)

from . import theme
from .i18n import T
from .theme import C

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")
MAX_LINES = 30000


@dataclass
class Hunk:
    header: str
    old_start: int
    new_start: int
    lines: List[str] = field(default_factory=list)


@dataclass
class FileDiff:
    header: List[str] = field(default_factory=list)
    hunks: List[Hunk] = field(default_factory=list)
    path: str = ""
    binary: bool = False


def parse_diff(text: str) -> List[FileDiff]:
    files: List[FileDiff] = []
    cur: Optional[FileDiff] = None
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git ") or line.startswith("diff --cc ") or line.startswith("diff --combined "):
            cur = FileDiff(header=[line])
            m = re.match(r'diff --git "?a/(.*?)"? "?b/(.*?)"?$', line)
            cur.path = m.group(2) if m else line.split(" ")[-1]
            files.append(cur)
            i += 1
            continue
        if cur is None:
            if line.startswith("--- ") or line.startswith("@@"):
                cur = FileDiff()
                files.append(cur)
            else:
                i += 1
                continue
        m = HUNK_RE.match(line)
        if m:
            old_n = int(m.group(2)) if m.group(2) is not None else 1
            new_n = int(m.group(4)) if m.group(4) is not None else 1
            h = Hunk(header=line, old_start=int(m.group(1)), new_start=int(m.group(3)))
            i += 1
            while i < len(lines) and (old_n > 0 or new_n > 0 or
                                      (i < len(lines) and lines[i].startswith("\\"))):
                l = lines[i]
                tag = l[:1]
                if tag == "+":
                    new_n -= 1
                elif tag == "-":
                    old_n -= 1
                elif tag == " " or l == "":
                    if l == "" and i == len(lines) - 1:
                        break
                    old_n -= 1
                    new_n -= 1
                    if l == "":
                        l = " "
                elif tag == "\\":
                    pass
                else:
                    break
                h.lines.append(l)
                i += 1
            # trailing "\ No newline" after counts are exhausted
            while i < len(lines) and lines[i].startswith("\\"):
                h.lines.append(lines[i])
                i += 1
            cur.hunks.append(h)
            continue
        if line == "":
            i += 1
            continue
        if line.startswith("Binary files") or line.startswith("GIT binary patch"):
            cur.binary = True
        if line.startswith("+++ "):
            p = line[4:]
            if p.startswith("b/"):
                cur.path = p[2:]
        cur.header.append(line)
        i += 1
    return files


def build_patch(fd: FileDiff, selection: Dict[int, Optional[set]], reverse: bool) -> str:
    """Build a patch containing only the selected hunks / lines.

    reverse=True means the patch will be applied with -R; then the "new" side is
    the base, so unselected '+' lines turn into context and unselected '-' lines
    are dropped (and the other way round for forward application)."""
    out = [l for l in fd.header if not l.startswith("Binary")]
    for hi, h in enumerate(fd.hunks):
        if hi not in selection:
            continue
        sel = selection[hi]
        body = []
        changed = False
        for li, l in enumerate(h.lines):
            tag = l[:1]
            if sel is None or li in sel:
                body.append(l)
                if tag in "+-":
                    changed = True
            elif tag == " ":
                body.append(l)
            elif tag == "+":
                if reverse:
                    body.append(" " + l[1:])
            elif tag == "-":
                if not reverse:
                    body.append(" " + l[1:])
            elif tag == "\\":
                if body and body[-1][:1] in " +-":
                    body.append(l)
        if changed:
            out.append(h.header)
            out.extend(body)
    return "\n".join(out) + "\n"


class _Gutter(QWidget):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def sizeHint(self):
        return QSize(self.view.gutter_width(), 0)

    def paintEvent(self, e):
        self.view.paint_gutter(self, e)


class _DiffHighlighter(QSyntaxHighlighter):
    """Colors each line by its kind (added / removed / hunk / meta)."""

    def __init__(self, view):
        super().__init__(view.document())
        self.view = view
        self.formats = {}

    def refresh_formats(self):
        def f(color, bold=False):
            x = QTextCharFormat()
            x.setForeground(QColor(C[color]))
            if bold:
                x.setFontWeight(QFont.Bold)
            return x
        self.formats = {"add": f("add_fg"), "del": f("del_fg"), "hunk": f("hunk_fg"),
                        "meta": f("muted"), "file": f("text", True)}

    def highlightBlock(self, text):
        n = self.currentBlock().blockNumber()
        kinds = self.view.kinds
        if n < len(kinds):
            fmt = self.formats.get(kinds[n])
            if fmt is not None:
                self.setFormat(0, len(text), fmt)


class DiffText(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setWordWrapMode(QTextOption.NoWrap)
        self.setFont(theme.mono_font())
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.numbers: List[tuple] = []
        self.kinds: List[str] = []
        self.gutter = _Gutter(self)
        self.highlighter = _DiffHighlighter(self)
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._update_gutter)
        self._update_margins()

    def gutter_width(self):
        return self.fontMetrics().horizontalAdvance("9") * 11 + 10

    def _update_margins(self, *_):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    BG = {"add": "add_bg", "del": "del_bg", "hunk": "hunk_bg", "file": "panel"}

    def paintEvent(self, e):
        # Full-width line backgrounds are painted here (only for visible lines),
        # which is far faster than storing a block format on every line.
        if self.kinds:
            p = QPainter(self.viewport())
            block = self.firstVisibleBlock()
            n = block.blockNumber()
            off = self.contentOffset()
            w = self.viewport().width()
            bottom_limit = e.rect().bottom()
            colors = {k: QColor(C[v]) for k, v in self.BG.items()}
            while block.isValid():
                geo = self.blockBoundingGeometry(block).translated(off)
                if geo.top() > bottom_limit:
                    break
                if n < len(self.kinds):
                    col = colors.get(self.kinds[n])
                    if col is not None:
                        p.fillRect(QRect(0, int(geo.top()), w, int(geo.height()) + 1), col)
                block = block.next()
                n += 1
            p.end()
        super().paintEvent(e)

    def paint_gutter(self, w, e):
        p = QPainter(w)
        p.fillRect(e.rect(), QColor(C["panel"]))
        p.setPen(QColor(C["muted"]))
        p.setFont(self.font())
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        cw = self.fontMetrics().horizontalAdvance("9") * 5
        h = self.fontMetrics().height()
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top() and n < len(self.numbers):
                o, nn = self.numbers[n]
                if o:
                    p.drawText(0, top, cw, h, Qt.AlignRight, str(o))
                if nn:
                    p.drawText(cw + 4, top, cw, h, Qt.AlignRight, str(nn))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            n += 1
        p.setPen(QColor(C["border"]))
        p.drawLine(w.width() - 1, e.rect().top(), w.width() - 1, e.rect().bottom())


class DiffView(QWidget):
    """mode: 'unstaged' | 'staged' | 'readonly'"""
    patchRequested = Signal(str, list, str)   # patch, git-apply args, description
    optionsChanged = Signal()

    def __init__(self, parent=None, show_options=True):
        super().__init__(parent)
        self.mode = "readonly"
        self.files: List[FileDiff] = []
        self.map: List[Optional[tuple]] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 0, 4, 0)
        self.title = QLabel("")
        self.title.setProperty("h2", True)
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bar.addWidget(self.title, 1)
        self.btn_hunk = QPushButton()
        self.btn_lines = QPushButton()
        self.btn_discard_hunk = QPushButton(T("捨棄區塊", "Discard hunk"))
        self.btn_discard_lines = QPushButton(T("捨棄選取行", "Discard lines"))
        for b in (self.btn_hunk, self.btn_lines, self.btn_discard_hunk, self.btn_discard_lines):
            b.setProperty("flat", True)
            bar.addWidget(b)
        self.btn_hunk.clicked.connect(lambda: self._act("hunk"))
        self.btn_lines.clicked.connect(lambda: self._act("lines"))
        self.btn_discard_hunk.clicked.connect(lambda: self._act("hunk", discard=True))
        self.btn_discard_lines.clicked.connect(lambda: self._act("lines", discard=True))
        self.chk_ws = QCheckBox(T("忽略空白", "Ignore whitespace"))
        self.spin_ctx = QSpinBox()
        self.spin_ctx.setRange(0, 99)
        self.spin_ctx.setValue(3)
        self.spin_ctx.setPrefix(T("上下文 ", "Context "))
        self.spin_ctx.setMinimumWidth(110)
        self.chk_ws.toggled.connect(lambda *_: self.optionsChanged.emit())
        self.spin_ctx.valueChanged.connect(lambda *_: self.optionsChanged.emit())
        if show_options:
            bar.addWidget(self.chk_ws)
            bar.addWidget(self.spin_ctx)
        lay.addLayout(bar)

        self.text = DiffText(self)
        self.text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.text.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.text, 1)
        self._update_buttons()

    # ------------------------------------------------------------------ options
    def diff_opts(self) -> List[str]:
        o = [f"-U{self.spin_ctx.value()}"]
        if self.chk_ws.isChecked():
            o.append("-w")
        return o

    # ------------------------------------------------------------------ content
    def clear(self):
        self.files = []
        self.map = []
        self.text.numbers = []
        self.text.kinds = []
        self.text.clear()
        self.title.setText("")
        self._update_buttons()

    def set_message(self, msg: str):
        self.clear()
        self.text.setPlainText(msg)

    def set_diff(self, text: str, mode: str = "readonly", title: str = ""):
        # keep scroll position when content is refreshed for the same file
        same = title == self.title.text()
        vpos = self.text.verticalScrollBar().value() if same else 0
        hpos = self.text.horizontalScrollBar().value() if same else 0
        self.mode = mode
        self.title.setText(title)
        self.files = parse_diff(text)
        lines, kinds, numbers, mp = [], [], [], []

        def add(txt, kind, m, nums):
            lines.append(txt)
            kinds.append(kind)
            mp.append(m)
            numbers.append(nums)

        multi = len(self.files) > 1
        truncated = False
        if not self.files and text.strip():
            for l in text.splitlines()[:MAX_LINES]:
                add(l, "norm", None, (None, None))
        for fi, fd in enumerate(self.files):
            if len(lines) > MAX_LINES:
                truncated = True
                break
            if multi:
                add("▸ " + fd.path, "file", None, (None, None))
            for hl in fd.header:
                if hl.startswith(("diff --git", "index ", "--- ", "+++ ")):
                    continue
                add(hl, "meta", None, (None, None))
            if fd.binary:
                add(T("（二進位檔案）", "(binary file)"), "meta", None, (None, None))
            for hi, h in enumerate(fd.hunks):
                add(h.header, "hunk", (fi, hi, None), (None, None))
                o, n = h.old_start, h.new_start
                for li, l in enumerate(h.lines):
                    tag = l[:1]
                    if tag == "+":
                        add(l, "add", (fi, hi, li), (None, n)); n += 1
                    elif tag == "-":
                        add(l, "del", (fi, hi, li), (o, None)); o += 1
                    elif tag == "\\":
                        add(l, "meta", (fi, hi, li), (None, None))
                    else:
                        add(l, "norm", (fi, hi, li), (o, n)); o += 1; n += 1
                if len(lines) > MAX_LINES:
                    truncated = True
                    break
        if truncated:
            add(T("… 差異過大，已截斷顯示", "… diff too large, truncated"), "meta", None, (None, None))
        if not lines:
            add(T("沒有差異", "No differences"), "meta", None, (None, None))
        self.map = mp
        t = self.text
        t.kinds = kinds
        t.numbers = numbers
        if not t.highlighter.formats:
            t.highlighter.refresh_formats()
        t.setPlainText("\n".join(lines))
        t.gutter.update()
        t.verticalScrollBar().setValue(vpos)
        t.horizontalScrollBar().setValue(hpos)
        self._update_buttons()

    # ------------------------------------------------------------------ actions
    def _update_buttons(self):
        can = self.mode in ("unstaged", "staged") and len(self.files) == 1 and bool(self.files[0].hunks) \
            and not self.files[0].binary
        if self.mode == "staged":
            self.btn_hunk.setText(T("取消暫存區塊", "Unstage hunk"))
            self.btn_lines.setText(T("取消暫存選取行", "Unstage lines"))
        else:
            self.btn_hunk.setText(T("暫存區塊", "Stage hunk"))
            self.btn_lines.setText(T("暫存選取行", "Stage lines"))
        self.btn_hunk.setVisible(can)
        self.btn_lines.setVisible(can)
        self.btn_discard_hunk.setVisible(can and self.mode == "unstaged")
        self.btn_discard_lines.setVisible(can and self.mode == "unstaged")

    def _selected_blocks(self):
        c = self.text.textCursor()
        a = self.text.document().findBlock(c.selectionStart()).blockNumber()
        b = self.text.document().findBlock(c.selectionEnd()).blockNumber()
        return a, b

    def _selection(self, kind):
        a, b = self._selected_blocks()
        sel: Dict[int, Optional[set]] = {}
        if kind == "hunk":
            for bn in range(a, b + 1):
                if bn < len(self.map) and self.map[bn]:
                    sel[self.map[bn][1]] = None
        else:
            for bn in range(a, b + 1):
                if bn < len(self.map) and self.map[bn]:
                    _f, hi, li = self.map[bn]
                    if li is None:
                        sel[hi] = None
                    elif sel.get(hi, set()) is not None:
                        sel.setdefault(hi, set()).add(li)
        return sel

    def _act(self, kind, discard=False):
        if not self.files:
            return
        sel = self._selection(kind)
        if not sel:
            return
        fd = self.files[0]
        if self.mode == "unstaged" and not discard:
            patch = build_patch(fd, sel, reverse=False)
            self.patchRequested.emit(patch, ["--cached"], "stage")
        elif self.mode == "unstaged" and discard:
            patch = build_patch(fd, sel, reverse=True)
            self.patchRequested.emit(patch, ["-R"], "discard")
        elif self.mode == "staged":
            patch = build_patch(fd, sel, reverse=True)
            self.patchRequested.emit(patch, ["--cached", "-R"], "unstage")

    def _menu(self, pos):
        m = QMenu(self)
        if self.btn_hunk.isVisible():
            m.addAction(self.btn_hunk.text(), lambda: self._act("hunk"))
            m.addAction(self.btn_lines.text(), lambda: self._act("lines"))
            if self.mode == "unstaged":
                m.addSeparator()
                m.addAction(self.btn_discard_hunk.text(), lambda: self._act("hunk", True))
                m.addAction(self.btn_discard_lines.text(), lambda: self._act("lines", True))
            m.addSeparator()
        m.addAction(T("複製", "Copy"), self.text.copy)
        m.addAction(T("全選", "Select all"), self.text.selectAll)
        m.exec(self.text.mapToGlobal(pos))
