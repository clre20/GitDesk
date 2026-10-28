"""Commit graph: lane layout, table model and painting delegate."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from . import theme
from .git import Commit
from .i18n import T

LANE_W = 14
ROW_H = 26


@dataclass
class Row:
    commit: Commit
    col: int
    top: List[tuple] = field(default_factory=list)      # (from_lane, to_lane, color_lane)
    bottom: List[tuple] = field(default_factory=list)
    width: int = 1
    refs: List[tuple] = field(default_factory=list)     # (kind, name)


def parse_refs(decor: str, head_branch: str):
    res = []
    for r in [x.strip() for x in decor.split(",") if x.strip()]:
        if r.startswith("HEAD -> "):
            res.append(("head", r[8:].replace("refs/heads/", "")))
        elif r == "HEAD":
            res.append(("detached", "HEAD"))
        elif r.startswith("tag: "):
            res.append(("tag", r[5:].replace("refs/tags/", "")))
        elif r.startswith("refs/heads/"):
            res.append(("branch", r[11:]))
        elif r.startswith("refs/remotes/"):
            n = r[13:]
            if not n.endswith("/HEAD"):
                res.append(("remote", n))
        elif r.startswith("refs/stash"):
            res.append(("stash", "stash"))
        else:
            res.append(("other", r))
    order = {"head": 0, "detached": 0, "branch": 1, "remote": 2, "tag": 3, "stash": 4, "other": 5}
    res.sort(key=lambda x: order.get(x[0], 9))
    return res


def layout(commits: List[Commit]) -> List[Row]:
    lanes: List = []          # sha expected in each lane
    rows = []

    def place(sha):
        try:
            j = lanes.index(None)
            lanes[j] = sha
        except ValueError:
            j = len(lanes)
            lanes.append(sha)
        return j

    for c in commits:
        expected = c.sha in lanes
        col = lanes.index(c.sha) if expected else place(c.sha)
        before = list(lanes)
        row = Row(commit=c, col=col)
        for i, s in enumerate(before):
            if s is None:
                continue
            if s == c.sha:
                if i == col and not expected:
                    continue            # branch tip: nothing above
                row.top.append((i, col, i))
            else:
                row.top.append((i, i, i))
        for i, s in enumerate(lanes):
            if s == c.sha and i != col:
                lanes[i] = None
        lanes[col] = c.parents[0] if c.parents else None
        for p in c.parents[1:]:
            if p not in lanes:
                place(p)
        after = list(lanes)
        for k, p in enumerate(c.parents):
            j = col if k == 0 else after.index(p)
            row.bottom.append((col, j, j))
        for i, s in enumerate(after):
            if s is None or i == col:
                continue
            if i < len(before) and before[i] == s and s != c.sha:
                row.bottom.append((i, i, i))
        while lanes and lanes[-1] is None:
            lanes.pop()
        row.width = max(len(before), len(after), col + 1)
        rows.append(row)
    return rows


def rel_time(ts: int) -> str:
    d = time.time() - ts
    if d < 60:
        return T("剛剛", "just now")
    if d < 3600:
        return T(f"{int(d // 60)} 分鐘前", f"{int(d // 60)} min ago")
    if d < 86400:
        return T(f"{int(d // 3600)} 小時前", f"{int(d // 3600)} h ago")
    if d < 86400 * 30:
        return T(f"{int(d // 86400)} 天前", f"{int(d // 86400)} days ago")
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class CommitModel(QAbstractTableModel):
    COLS = [("graph", ""), ("author", ""), ("date", ""), ("sha", "")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[Row] = []
        self.headers = [T("描述", "Description"), T("作者", "Author"), T("日期", "Date"), "SHA"]
        self.head_sha = ""
        self.highlight = set()

    def set_rows(self, rows: List[Row], head_sha: str):
        self.beginResetModel()
        self.rows = rows
        self.head_sha = head_sha
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[s]
        return None

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid():
            return None
        r = self.rows[idx.row()]
        c = r.commit
        col = idx.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return c.subject
            if col == 1:
                return c.author
            if col == 2:
                return rel_time(c.time)
            if col == 3:
                return c.sha[:8]
        if role == Qt.ToolTipRole:
            if col == 2:
                return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(c.time))
            if col == 1:
                return f"{c.author} <{c.email}>"
            if col == 0:
                return c.subject
        if role == Qt.UserRole:
            return r
        if role == Qt.FontRole and c.sha == self.head_sha:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ForegroundRole and col in (1, 2, 3):
            return QBrush(QColor(theme.C["muted"]))
        return None


class GraphDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        return QSize(s.width(), ROW_H)

    def paint(self, p: QPainter, option, index):
        r: Row = index.data(Qt.UserRole)
        self.initStyleOption(option, index)
        style = option.widget.style() if option.widget else None
        text = option.text
        option.text = ""
        if style:
            style.drawControl(QStyle.CE_ItemViewItem, option, p, option.widget)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        x0 = rect.left() + 6
        cy = rect.top() + rect.height() / 2
        top = rect.top()
        bot = rect.bottom() + 1
        lx = lambda i: x0 + i * LANE_W + LANE_W / 2

        def color(i):
            return QColor(theme.GRAPH_COLORS[i % len(theme.GRAPH_COLORS)])

        for (a, b, ci) in r.top:
            pen = QPen(color(ci), 2)
            p.setPen(pen)
            if a == b:
                p.drawLine(QPointF(lx(a), top), QPointF(lx(b), cy))
            else:
                path = QPainterPath(QPointF(lx(a), top))
                path.cubicTo(QPointF(lx(a), cy), QPointF(lx(b), top), QPointF(lx(b), cy))
                p.drawPath(path)
        for (a, b, ci) in r.bottom:
            pen = QPen(color(ci), 2)
            p.setPen(pen)
            if a == b:
                p.drawLine(QPointF(lx(a), cy), QPointF(lx(b), bot))
            else:
                path = QPainterPath(QPointF(lx(a), cy))
                path.cubicTo(QPointF(lx(a), bot), QPointF(lx(b), cy), QPointF(lx(b), bot))
                p.drawPath(path)
        # node
        nc = color(r.col)
        model = index.model()
        is_head = getattr(model, "head_sha", "") == r.commit.sha
        if len(r.commit.parents) > 1:
            p.setPen(QPen(nc, 2))
            p.setBrush(QColor(theme.C["base"]))
            p.drawEllipse(QPointF(lx(r.col), cy), 4, 4)
        else:
            p.setPen(QPen(QColor(theme.C["base"]), 1.5))
            p.setBrush(nc)
            p.drawEllipse(QPointF(lx(r.col), cy), 5 if is_head else 4.5, 5 if is_head else 4.5)
        if is_head:
            p.setPen(QPen(nc, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(lx(r.col), cy), 8, 8)

        # ref badges
        x = x0 + r.width * LANE_W + 6
        fm = QFontMetrics(option.font)
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() - 1))
        sfm = QFontMetrics(small)
        for kind, name in r.refs:
            bg, fg = self._ref_colors(kind)
            label = name
            if kind == "head":
                label = "✓ " + name
            w = sfm.horizontalAdvance(label) + 12
            if x + w > rect.right() - 60:
                break
            br = QRectF(x, cy - 9, w, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(br, 4, 4)
            p.setPen(fg)
            p.setFont(small)
            p.drawText(br, Qt.AlignCenter, label)
            x += w + 4
        p.setFont(option.font)
        p.setPen(option.palette.color(QPalette.Text))
        tr = QRectF(x + 2, rect.top(), rect.right() - x - 4, rect.height())
        p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(text, Qt.ElideRight, int(tr.width())))
        p.restore()

    @staticmethod
    def _ref_colors(kind):
        dark = theme.is_dark()
        m = {
            "head": ("#0067c0", "#ffffff"),
            "detached": ("#c42b1c", "#ffffff"),
            "branch": ("#cce4f7" if not dark else "#16405f", "#003e73" if not dark else "#cfe8ff"),
            "remote": ("#e5e5e5" if not dark else "#3a3a3a", "#333333" if not dark else "#dddddd"),
            "tag": ("#fff4ce" if not dark else "#4a3c10", "#5c4400" if not dark else "#ffe58a"),
            "stash": ("#efe0fb" if not dark else "#3d2a52", "#5c2d91" if not dark else "#dcc3ff"),
            "other": ("#e5e5e5", "#333333"),
        }
        bg, fg = m.get(kind, m["other"])
        return QColor(bg), QColor(fg)
