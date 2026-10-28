"""Secondary windows: interactive rebase, conflict editor, blame, file history,
reflog, compare, remotes, config, hooks, LFS, clean, maintenance, grep…"""
from __future__ import annotations

import os
import re
import shlex
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QTextCharFormat, QTextCursor, QTextFormat
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .diffview import DiffView
from .git import GitError, run_git
from .i18n import T


def _close_box(dlg, layout, extra=None):
    bb = QDialogButtonBox()
    for b in extra or []:
        bb.addButton(b, QDialogButtonBox.ActionRole)
    c = bb.addButton(T("關閉", "Close"), QDialogButtonBox.RejectRole)
    bb.rejected.connect(dlg.reject)
    layout.addWidget(bb)
    return bb


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setShowGrid(False)
    t.horizontalHeader().setHighlightSections(False)
    t.verticalHeader().setDefaultSectionSize(24)
    return t


# =========================================================================== diff window
class DiffWindow(QMainWindow):
    def __init__(self, rw, title, text):
        super().__init__(rw)
        self.setWindowTitle(title)
        self.resize(1000, 700)
        d = DiffView(self, show_options=False)
        d.set_diff(text, "readonly", title)
        self.setCentralWidget(d)


# =========================================================================== interactive rebase
class InteractiveRebaseDialog(QDialog):
    ACTIONS = [("pick", T("保留 pick", "pick")), ("reword", T("改訊息 reword", "reword")),
               ("edit", T("停下編輯 edit", "edit")), ("squash", T("壓縮 squash", "squash")),
               ("fixup", T("合併丟訊息 fixup", "fixup")), ("drop", T("刪除 drop", "drop"))]

    def __init__(self, rw, base):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("互動式變基", "Interactive rebase"))
        self.resize(900, 560)
        repo = rw.repo
        self.root = False
        base_sha = repo.git("rev-parse", "--verify", "-q", base + "^{commit}", check=False).strip()
        head = repo.git("rev-parse", "HEAD").strip()
        if base_sha == head:
            # rebase "from here" including this commit
            parent = repo.git("rev-parse", "--verify", "-q", base_sha + "~1", check=False).strip()
            if parent:
                base_sha = parent
            else:
                self.root = True
        rng = "HEAD" if self.root else f"{base_sha}..HEAD"
        out = repo.git("log", "--reverse", "--no-merges", "--format=%H%x1f%s%x1f%B%x1e", rng, check=False)
        self.commits = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if rec:
                sha, subj, body = (rec.split("\x1f") + ["", ""])[:3]
                self.commits.append((sha, subj, body.strip()))
        v = QVBoxLayout(self)
        h = QLabel(T("互動式變基", "Interactive rebase"))
        h.setProperty("h2", True)
        v.addWidget(h)
        info = QLabel(T("由上（最舊）到下（最新）依序重新套用。用按鈕調整順序；squash/fixup 會併入上一個提交。"
                        "可直接編輯訊息欄位來改寫訊息（reword）。",
                        "Commits are replayed top (oldest) to bottom (newest). Use the buttons to reorder; "
                        "squash/fixup fold into the commit above. Edit the message cell to reword."))
        info.setWordWrap(True)
        info.setProperty("muted", True)
        v.addWidget(info)
        self.table = _table([T("動作", "Action"), "SHA", T("訊息", "Message")])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 170)
        self.table.setColumnWidth(1, 90)
        for sha, subj, body in self.commits:
            self._add_row(sha, subj, body, "pick")
        v.addWidget(self.table, 1)
        btns = QHBoxLayout()
        for txt, fn in ((T("上移", "Move up"), lambda: self._move(-1)), (T("下移", "Move down"), lambda: self._move(1))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch(1)
        for act, label in self.ACTIONS:
            b = QPushButton(act)
            b.setProperty("flat", True)
            b.setToolTip(label)
            b.clicked.connect(lambda _=False, a=act: self._set_selected(a))
            btns.addWidget(b)
        v.addLayout(btns)
        if not self.commits:
            v.addWidget(QLabel(T("此範圍內沒有可變基的提交。", "No commits to rebase in this range.")))
        bb = QDialogButtonBox()
        ok = bb.addButton(T("開始變基", "Start rebase"), QDialogButtonBox.AcceptRole)
        ok.setProperty("accent", True)
        ok.setEnabled(bool(self.commits))
        bb.addButton(T("取消", "Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _add_row(self, sha, subj, body, action, row=None):
        r = self.table.rowCount() if row is None else row
        self.table.insertRow(r)
        cb = QComboBox()
        for a, label in self.ACTIONS:
            cb.addItem(label, a)
        cb.setCurrentIndex([a for a, _ in self.ACTIONS].index(action))
        self.table.setCellWidget(r, 0, cb)
        it = QTableWidgetItem(sha[:8])
        it.setData(Qt.UserRole, (sha, subj, body))
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 1, it)
        self.table.setItem(r, 2, QTableWidgetItem(subj))

    def _rows(self):
        res = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 1)
            if not it:
                continue
            cb = self.table.cellWidget(r, 0)
            sha, subj, body = it.data(Qt.UserRole)
            msg = self.table.item(r, 2).text() if self.table.item(r, 2) else subj
            res.append((cb.currentData() if cb else "pick", sha, subj, body, msg))
        return res

    def _rebuild(self, rows, select):
        self.table.setRowCount(0)
        for act, sha, subj, body, msg in rows:
            self._add_row(sha, subj, body, act)
            self.table.item(self.table.rowCount() - 1, 2).setText(msg)
        self.table.selectRow(select)

    def _move(self, d):
        r = self.table.currentRow()
        rows = self._rows()
        j = r + d
        if r < 0 or j < 0 or j >= len(rows):
            return
        rows[r], rows[j] = rows[j], rows[r]
        self._rebuild(rows, j)

    def _set_selected(self, act):
        for idx in self.table.selectionModel().selectedRows():
            cb = self.table.cellWidget(idx.row(), 0)
            if cb:
                cb.setCurrentIndex(cb.findData(act))

    def todo_text(self):
        lines = []
        rows = self._rows()
        for i, (act, sha, subj, body, msg) in enumerate(rows):
            if act in ("squash", "fixup") and i == 0:
                act = "pick"
            if msg.strip() != subj.strip() and act == "pick":
                act = "reword"
            if act == "reword":
                newmsg = msg.strip()
                rest = body.split("\n", 1)[1].strip() if "\n" in body else ""
                full = newmsg + ("\n\n" + rest if rest else "")
                p = self.rw.temp_file(full, f"reword-{sha[:10]}").replace("\\", "/")
                lines.append(f"pick {sha} {subj}")
                lines.append(f"exec git commit --amend --no-verify -F '{p}'")
            else:
                lines.append(f"{act} {sha} {subj}")
        return "\n".join(lines) + "\n"


# =========================================================================== conflict editor
class ConflictEditor(QDialog):
    """Built-in merge conflict editor: choose ours / theirs / both per conflict block."""

    def __init__(self, rw, path, parent=None):
        super().__init__(parent or rw)
        self.rw = rw
        self.path = path
        self.full = os.path.join(rw.repo.path, path)
        self.setWindowTitle(T(f"解決衝突 — {path}", f"Resolve conflicts — {path}"))
        self.resize(1100, 720)
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.lbl = QLabel()
        self.lbl.setProperty("h2", True)
        top.addWidget(self.lbl, 1)
        for txt, fn in ((T("◀ 上一個", "◀ Prev"), lambda: self._goto(-1)),
                        (T("下一個 ▶", "Next ▶"), lambda: self._goto(1)),
                        (T("採用我方 (ours)", "Take ours"), lambda: self._take("ours")),
                        (T("採用對方 (theirs)", "Take theirs"), lambda: self._take("theirs")),
                        (T("兩者 (我方在前)", "Both (ours first)"), lambda: self._take("both")),
                        (T("兩者 (對方在前)", "Both (theirs first)"), lambda: self._take("both_r"))):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            top.addWidget(b)
        v.addLayout(top)
        hint = QLabel(T("可直接編輯下方文字。<<<<<<< 我方（目前 HEAD）| ======= | >>>>>>> 對方（傳入）",
                        "You can edit the text directly. <<<<<<< ours (HEAD) | ======= | >>>>>>> theirs (incoming)"))
        hint.setProperty("muted", True)
        v.addWidget(hint)
        self.edit = QPlainTextEdit()
        self.edit.setFont(theme.mono_font())
        self.edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        try:
            with open(self.full, encoding="utf-8", errors="surrogateescape", newline="") as fh:
                self.edit.setPlainText(fh.read())
        except OSError as e:
            self.edit.setPlainText(str(e))
        self.edit.textChanged.connect(self._highlight)
        v.addWidget(self.edit, 1)
        bb = QDialogButtonBox()
        save = bb.addButton(T("儲存並標記已解決", "Save && mark resolved"), QDialogButtonBox.AcceptRole)
        save.setProperty("accent", True)
        only = bb.addButton(T("僅儲存", "Save only"), QDialogButtonBox.ActionRole)
        bb.addButton(T("取消", "Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(lambda: self._save(True))
        only.clicked.connect(lambda: self._save(False))
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self._highlight()
        QTimer.singleShot(0, lambda: self._goto(1, from_start=True))

    def _blocks(self):
        """Return list of (start_line, mid_line, base_line|None, end_line)."""
        lines = self.edit.toPlainText().split("\n")
        res, start, mid, base = [], None, None, None
        for i, l in enumerate(lines):
            if l.startswith("<<<<<<<"):
                start, mid, base = i, None, None
            elif l.startswith("|||||||") and start is not None:
                base = i
            elif l.startswith("=======") and start is not None:
                mid = i
            elif l.startswith(">>>>>>>") and start is not None and mid is not None:
                res.append((start, mid, base, i))
                start = None
        return res

    def _highlight(self):
        blocks = self._blocks()
        self.lbl.setText(T(f"剩餘 {len(blocks)} 個衝突", f"{len(blocks)} conflict(s) left"))
        sels = []
        doc = self.edit.document()
        dark = theme.is_dark()
        ours = QColor("#12304a" if dark else "#e1efff")
        theirs = QColor("#123a1f" if dark else "#e6ffec")
        marker = QColor("#3a3a3a" if dark else "#e8e8e8")
        for s, m, b, e in blocks:
            for ln in range(s, e + 1):
                blk = doc.findBlockByNumber(ln)
                sel = QTextEdit.ExtraSelection()
                sel.cursor = QTextCursor(blk)
                sel.format.setProperty(QTextFormat.FullWidthSelection, True)
                if ln in (s, m, e) or ln == b:
                    sel.format.setBackground(marker)
                elif ln < (b if b is not None else m):
                    sel.format.setBackground(ours)
                elif ln > m:
                    sel.format.setBackground(theirs)
                else:
                    sel.format.setBackground(marker)
                sels.append(sel)
        self.edit.setExtraSelections(sels)

    def _current_block(self):
        line = self.edit.textCursor().blockNumber()
        for b in self._blocks():
            if b[0] <= line <= b[3]:
                return b
        bl = self._blocks()
        return next((b for b in bl if b[0] >= line), bl[0] if bl else None)

    def _goto(self, d, from_start=False):
        bl = self._blocks()
        if not bl:
            return
        line = -1 if from_start else self.edit.textCursor().blockNumber()
        if d > 0:
            tgt = next((b for b in bl if b[0] > line), bl[0])
        else:
            tgt = next((b for b in reversed(bl) if b[0] < line), bl[-1])
        c = QTextCursor(self.edit.document().findBlockByNumber(tgt[0]))
        self.edit.setTextCursor(c)
        self.edit.centerCursor()

    def _take(self, which):
        b = self._current_block()
        if not b:
            return
        s, m, base, e = b
        lines = self.edit.toPlainText().split("\n")
        ours = lines[s + 1:(base if base is not None else m)]
        theirs = lines[m + 1:e]
        rep = {"ours": ours, "theirs": theirs, "both": ours + theirs, "both_r": theirs + ours}[which]
        lines[s:e + 1] = rep
        self.edit.setPlainText("\n".join(lines))
        c = QTextCursor(self.edit.document().findBlockByNumber(min(s, len(lines) - 1)))
        self.edit.setTextCursor(c)
        self._goto(1)

    def _save(self, resolve):
        text = self.edit.toPlainText()
        if resolve and self._blocks():
            if not self.rw.confirm(T("仍有衝突", "Conflicts remain"),
                                   T("檔案中仍有衝突標記，仍要標記為已解決嗎？",
                                     "Conflict markers remain. Mark as resolved anyway?")):
                return
        with open(self.full, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            fh.write(text)
        if resolve:
            self.rw.git_sync(["add", "--", self.path])
        self.accept()


# =========================================================================== blame
class BlameWindow(QMainWindow):
    def __init__(self, rw, path, rev=None):
        super().__init__(rw)
        self.rw = rw
        self.path = path
        self.setWindowTitle(f"Blame — {path}" + (f" @ {rev[:8]}" if rev else ""))
        self.resize(1200, 760)
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.rev = QLineEdit(rev or "")
        self.rev.setPlaceholderText(T("版本（空白=工作區）", "Revision (empty = working tree)"))
        self.chk_ws = QCheckBox(T("忽略空白 (-w)", "Ignore whitespace (-w)"))
        self.chk_move = QCheckBox(T("偵測移動/複製 (-C)", "Detect moves/copies (-C)"))
        b = QPushButton(T("重新整理", "Refresh"))
        b.clicked.connect(self.load)
        bar.addWidget(QLabel(path))
        bar.addStretch(1)
        bar.addWidget(self.rev)
        bar.addWidget(self.chk_ws)
        bar.addWidget(self.chk_move)
        bar.addWidget(b)
        v.addLayout(bar)
        self.table = _table([T("提交", "Commit"), T("作者", "Author"), T("日期", "Date"), "#", T("內容", "Line")])
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setFont(theme.mono_font())
        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 95)
        self.table.setColumnWidth(3, 50)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.table)
        self.setCentralWidget(w)
        self.load()

    def load(self):
        args = ["blame", "--porcelain"]
        if self.chk_ws.isChecked():
            args.append("-w")
        if self.chk_move.isChecked():
            args += ["-C", "-M"]
        if self.rev.text().strip():
            args.append(self.rev.text().strip())
        args += ["--", self.path]
        try:
            out = self.rw.repo.git(*args)
        except GitError as e:
            self.rw.error("blame", str(e))
            return
        info = {}
        rows = []
        cur = None
        for line in out.split("\n"):
            if not line:
                continue
            if line.startswith("\t"):
                if cur:
                    rows.append((cur[0], cur[1], line[1:]))
                continue
            p = line.split(" ")
            if len(p[0]) == 40 and len(p) >= 3 and all(c in "0123456789abcdef" for c in p[0]):
                cur = (p[0], int(p[2]))
                info.setdefault(p[0], {})
            elif cur:
                k, _, val = line.partition(" ")
                info[cur[0]][k] = val
        self.table.setRowCount(len(rows))
        palette = [QColor(theme.C["base"]), QColor(theme.C["alt"])]
        prev, band = None, 0
        for r, (sha, ln, text) in enumerate(rows):
            meta = info.get(sha, {})
            show = sha != prev
            if show:
                band ^= 1
            prev = sha
            t = int(meta.get("author-time", 0) or 0)
            vals = [sha[:8] if show else "", meta.get("author", "") if show else "",
                    time.strftime("%Y-%m-%d", time.localtime(t)) if show and t else "", str(ln), text]
            for c, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setBackground(QBrush(palette[band]))
                if c == 0:
                    it.setData(Qt.UserRole, sha)
                    it.setToolTip(f"{sha}\n{meta.get('author', '')} <{meta.get('author-mail', '')}>\n{meta.get('summary', '')}")
                self.table.setItem(r, c, it)

    def _menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r < 0:
            return
        sha = None
        for k in range(r, -1, -1):
            it = self.table.item(k, 0)
            if it and it.text():
                sha = it.data(Qt.UserRole)
                break
        if not sha:
            return
        m = QMenu(self)
        m.addAction(T("在歷史中顯示", "Show in history"),
                    lambda: (self.rw.show_view("history"), self.rw.history.jump_to(sha)))
        m.addAction(T("追溯此提交之前 (blame 父版本)", "Blame prior revision"),
                    lambda: BlameWindow(self.rw, self.path, sha + "^").show())
        m.addAction(T("複製 SHA", "Copy SHA"), lambda: self.rw.copy_text(sha))
        m.exec(self.table.viewport().mapToGlobal(pos))


# =========================================================================== file history
class FileHistoryWindow(QMainWindow):
    def __init__(self, rw, path):
        super().__init__(rw)
        self.rw = rw
        self.path = path
        self.setWindowTitle(T(f"檔案歷史 — {path}", f"File history — {path}"))
        self.resize(1200, 760)
        split = QSplitter(Qt.Horizontal)
        self.list = _table(["SHA", T("作者", "Author"), T("日期", "Date"), T("訊息", "Message")])
        self.list.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.list.setColumnWidth(0, 80)
        self.list.setColumnWidth(1, 120)
        self.list.setColumnWidth(2, 95)
        self.list.itemSelectionChanged.connect(self._sel)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.diff = DiffView(self)
        self.diff.optionsChanged.connect(self._sel)
        split.addWidget(self.list)
        split.addWidget(self.diff)
        split.setSizes([480, 720])
        self.setCentralWidget(split)
        out = rw.repo.git("log", "--follow", "--name-only", "--format=%x1e%H%x1f%an%x1f%at%x1f%s", "--", path, check=False)
        self.entries = []
        for rec in out.split("\x1e"):
            rec = rec.strip()
            if not rec:
                continue
            head, _, files = rec.partition("\n")
            p = head.split("\x1f")
            if len(p) < 4:
                continue
            fname = files.strip().splitlines()[-1] if files.strip() else path
            self.entries.append((p[0], p[1], int(p[2] or 0), p[3], fname))
        self.list.setRowCount(len(self.entries))
        for r, (sha, a, t, s, _f) in enumerate(self.entries):
            for c, val in enumerate([sha[:8], a, time.strftime("%Y-%m-%d", time.localtime(t)), s]):
                self.list.setItem(r, c, QTableWidgetItem(val))
        if self.entries:
            self.list.selectRow(0)

    def _sel(self, *_):
        r = self.list.currentRow()
        if r < 0 or r >= len(self.entries):
            return
        sha, _a, _t, _s, fname = self.entries[r]
        txt = self.rw.repo.git("show", "--no-color", "--format=", "-M", *self.diff.diff_opts(), sha, "--", fname, check=False)
        self.diff.set_diff(txt, "readonly", f"{sha[:8]}  {fname}")

    def _menu(self, pos):
        r = self.list.rowAt(pos.y())
        if r < 0:
            return
        sha, _a, _t, _s, fname = self.entries[r]
        from . import actions
        m = QMenu(self)
        m.addAction(T("在歷史中顯示", "Show in history"), lambda: (self.rw.show_view("history"), self.rw.history.jump_to(sha)))
        m.addAction("Blame", lambda: BlameWindow(self.rw, fname, sha).show())
        m.addAction(T("還原檔案到此版本", "Restore file to this revision"), lambda: actions.restore_file_from(self.rw, fname, sha))
        m.addAction(T("另存此版本…", "Save this revision…"), lambda: actions.save_revision(self.rw, fname, sha))
        m.exec(self.list.viewport().mapToGlobal(pos))


# =========================================================================== reflog
class ReflogWindow(QMainWindow):
    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("參照記錄 (reflog)", "Reflog"))
        self.resize(1000, 640)
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.ref = QComboBox()
        self.ref.setEditable(True)
        self.ref.addItems(["HEAD"] + [b.name for b in rw.repo.branches()] + ["refs/stash"])
        self.ref.currentTextChanged.connect(self.load)
        info = QLabel(T("可用來找回遺失的提交或還原錯誤的 reset / rebase。",
                        "Use it to recover lost commits or undo a bad reset / rebase."))
        info.setProperty("muted", True)
        bar.addWidget(self.ref)
        bar.addWidget(info, 1)
        exp = QPushButton(T("清理過期記錄 (expire)", "Expire old entries"))
        exp.clicked.connect(lambda: rw.run(["reflog", "expire", "--expire=90.days.ago", "--all"], "reflog expire"))
        bar.addWidget(exp)
        v.addLayout(bar)
        self.table = _table([T("參照", "Ref"), "SHA", T("時間", "When"), T("動作", "Action")])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        v.addWidget(self.table)
        self.setCentralWidget(w)
        self.load()

    def load(self, *_):
        out = self.rw.repo.git("reflog", "show", "--format=%gd%x1f%H%x1f%cr%x1f%gs", self.ref.currentText() or "HEAD", check=False)
        rows = [l.split("\x1f") for l in out.splitlines() if l.count("\x1f") >= 3]
        self.table.setRowCount(len(rows))
        for r, p in enumerate(rows):
            for c, val in enumerate([p[0], p[1][:10], p[2], p[3]]):
                it = QTableWidgetItem(val)
                if c == 1:
                    it.setData(Qt.UserRole, p[1])
                self.table.setItem(r, c, it)

    def _menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r < 0:
            return
        sha = self.table.item(r, 1).data(Qt.UserRole)
        from . import actions
        m = QMenu(self)
        m.addAction(T("在此建立分支…", "Create branch here…"), lambda: actions.new_branch(self.rw, sha))
        m.addAction(T("將目前分支重設到此…", "Reset current branch here…"), lambda: actions.reset(self.rw, sha))
        m.addAction(T("簽出（分離 HEAD）", "Checkout (detached)"), lambda: actions.checkout_commit(self.rw, sha))
        m.addAction(T("揀選…", "Cherry-pick…"), lambda: actions.cherry_pick(self.rw, [sha]))
        m.addAction(T("在歷史中顯示", "Show in history"), lambda: (self.rw.show_view("history"), self.rw.history.jump_to(sha)))
        m.addAction(T("複製 SHA", "Copy SHA"), lambda: self.rw.copy_text(sha))
        m.exec(self.table.viewport().mapToGlobal(pos))


# =========================================================================== compare
class CompareWindow(QMainWindow):
    def __init__(self, rw, a, b):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("比較分支 / 提交", "Compare branches / commits"))
        self.resize(1200, 760)
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        refs = rw.repo.all_refs_for_completion()
        self.a = QComboBox(); self.a.setEditable(True); self.a.addItems(["HEAD"] + refs); self.a.setCurrentText(a)
        self.b = QComboBox(); self.b.setEditable(True); self.b.addItems(["HEAD"] + refs); self.b.setCurrentText(b)
        self.mode = QComboBox()
        self.mode.addItem(T("三點 (從共同祖先起 B 的變更) A...B", "A...B (changes on B since merge base)"), "...")
        self.mode.addItem(T("兩點 (直接比較) A..B", "A..B (direct)"), "..")
        go = QPushButton(T("比較", "Compare"))
        go.setProperty("accent", True)
        go.clicked.connect(self.load)
        swap = QPushButton("⇄")
        swap.clicked.connect(self._swap)
        for wd in (QLabel("A"), self.a, swap, QLabel("B"), self.b, self.mode, go):
            bar.addWidget(wd)
        v.addLayout(bar)
        self.summary = QLabel()
        self.summary.setProperty("muted", True)
        v.addWidget(self.summary)
        split = QSplitter(Qt.Horizontal)
        left = QSplitter(Qt.Vertical)
        self.commits = QListWidget()
        self.files = QListWidget()
        self.files.currentItemChanged.connect(self._file)
        left.addWidget(self.commits)
        left.addWidget(self.files)
        self.diff = DiffView(self)
        self.diff.optionsChanged.connect(lambda: self._file(self.files.currentItem(), None))
        split.addWidget(left)
        split.addWidget(self.diff)
        split.setSizes([420, 780])
        v.addWidget(split, 1)
        self.setCentralWidget(w)
        if b:
            self.load()

    def _swap(self):
        a, b = self.a.currentText(), self.b.currentText()
        self.a.setCurrentText(b)
        self.b.setCurrentText(a)
        self.load()

    def load(self):
        a, b, mode = self.a.currentText().strip(), self.b.currentText().strip(), self.mode.currentData()
        if not a or not b:
            return
        repo = self.rw.repo
        cnt = repo.git("rev-list", "--left-right", "--count", f"{a}...{b}", check=False).split()
        if len(cnt) == 2:
            self.summary.setText(T(f"A 獨有 {cnt[0]} 個提交，B 獨有 {cnt[1]} 個提交",
                                   f"{cnt[0]} commit(s) only in A, {cnt[1]} only in B"))
        self.commits.clear()
        out = repo.git("log", "--left-right", "--format=%m %h %s", f"{a}...{b}", check=False)
        for l in out.splitlines()[:2000]:
            side = "A" if l.startswith("<") else "B"
            self.commits.addItem(f"[{side}] {l[2:]}")
        self.files.clear()
        self._rng = f"{a}{mode}{b}"
        it = QListWidgetItem(T("全部檔案", "All files"))
        it.setData(Qt.UserRole, None)
        self.files.addItem(it)
        for l in repo.git("diff", "--name-status", self._rng, check=False).splitlines():
            st, _, p = l.partition("\t")
            it = QListWidgetItem(f"{st[:1]}   {p}")
            it.setData(Qt.UserRole, p.split("\t")[-1])
            self.files.addItem(it)
        self.files.setCurrentRow(0)

    def _file(self, it, _p):
        if not it:
            return
        p = it.data(Qt.UserRole)
        args = ["diff", "--no-color", "-M", *self.diff.diff_opts(), self._rng]
        if p:
            args += ["--", p]
        self.diff.set_diff(self.rw.repo.git(*args, check=False), "readonly", p or self._rng)


# =========================================================================== remotes
class RemotesDialog(QDialog):
    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("管理遠端", "Manage remotes"))
        self.resize(820, 420)
        v = QVBoxLayout(self)
        self.table = _table([T("名稱", "Name"), T("提取 URL", "Fetch URL"), T("推送 URL", "Push URL")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        v.addWidget(self.table)
        from . import actions
        btns = []
        for txt, fn in ((T("新增…", "Add…"), lambda: actions.add_remote(rw)),
                        (T("編輯…", "Edit…"), lambda: self._sel() and actions.edit_remote(rw, self._sel())),
                        (T("移除…", "Remove…"), lambda: self._sel() and actions.remove_remote(rw, self._sel())),
                        (T("提取", "Fetch"), lambda: self._sel() and actions.fetch(rw, self._sel())),
                        ("prune", lambda: self._sel() and rw.run(["remote", "prune", self._sel()], "remote prune"))):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, f=fn: (f(), QTimer.singleShot(800, self.load)))
            btns.append(b)
        _close_box(self, v, btns)
        self.load()

    def _sel(self):
        r = self.table.currentRow()
        return self.table.item(r, 0).text() if r >= 0 else None

    def load(self):
        rems = self.rw.repo.remotes()
        self.table.setRowCount(len(rems))
        for r, x in enumerate(rems):
            for c, k in enumerate(("name", "fetch", "push")):
                self.table.setItem(r, c, QTableWidgetItem(x[k]))


# =========================================================================== config
class ConfigDialog(QDialog):
    def __init__(self, rw=None, scope="local"):
        super().__init__(rw)
        self.rw = rw
        self.cwd = rw.repo.path if rw else None
        self.setWindowTitle(T("Git 設定 (git config)", "Git configuration"))
        self.resize(860, 560)
        v = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.scope = QComboBox()
        if rw:
            self.scope.addItem(T("此儲存庫 (--local)", "This repository (--local)"), "local")
            self.scope.addItem(T("此工作樹 (--worktree)", "This worktree (--worktree)"), "worktree")
        self.scope.addItem(T("使用者 (--global)", "User (--global)"), "global")
        self.scope.addItem(T("系統 (--system，唯讀)", "System (--system, read-only)"), "system")
        self.scope.addItem(T("全部有效值 (--list --show-origin)", "Effective (--show-origin)"), "all")
        i = self.scope.findData(scope)
        self.scope.setCurrentIndex(max(0, i))
        self.scope.currentIndexChanged.connect(self.load)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(T("篩選…", "Filter…"))
        self.filter.textChanged.connect(self._filter)
        bar.addWidget(self.scope)
        bar.addWidget(self.filter, 1)
        v.addLayout(bar)
        quick = QHBoxLayout()
        self.name = QLineEdit()
        self.email = QLineEdit()
        self.name.setPlaceholderText("user.name")
        self.email.setPlaceholderText("user.email")
        save_id = QPushButton(T("儲存身分", "Save identity"))
        save_id.clicked.connect(self._save_identity)
        quick.addWidget(QLabel(T("身分：", "Identity:")))
        quick.addWidget(self.name)
        quick.addWidget(self.email)
        quick.addWidget(save_id)
        v.addLayout(quick)
        self.table = _table([T("鍵", "Key"), T("值", "Value"), T("來源", "Origin")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 260)
        self.table.doubleClicked.connect(lambda *_: self._edit())
        v.addWidget(self.table, 1)
        btns = []
        for txt, fn in ((T("新增…", "Add…"), self._add), (T("編輯…", "Edit…"), self._edit),
                        (T("刪除", "Unset"), self._unset), (T("用編輯器開啟檔案", "Open file in editor"), self._open)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            btns.append(b)
        _close_box(self, v, btns)
        self.load()

    def _git(self, *args, check=True):
        return run_git(list(args), cwd=self.cwd, check=check, log=True)

    def _sc(self):
        s = self.scope.currentData()
        return [] if s == "all" else ["--" + s]

    def load(self):
        s = self.scope.currentData()
        try:
            out = self._git("config", *self._sc(), "--list", "--show-origin", "-z", check=False)
        except Exception:
            out = ""
        rows = []
        for rec in out.split("\0"):
            pass
        parts = out.split("\0")
        i = 0
        while i + 1 < len(parts):
            origin, kv = parts[i], parts[i + 1]
            i += 2
            k, _, val = kv.partition("\n")
            rows.append((k, val, origin))
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(val))
        self._filter(self.filter.text())
        scope = [] if s in ("all", "system") else self._sc()
        self.name.setText(self._git("config", *scope, "--get", "user.name", check=False).strip())
        self.email.setText(self._git("config", *scope, "--get", "user.email", check=False).strip())

    def _filter(self, t):
        t = t.lower()
        for r in range(self.table.rowCount()):
            k = self.table.item(r, 0).text().lower()
            val = self.table.item(r, 1).text().lower()
            self.table.setRowHidden(r, bool(t) and t not in k and t not in val)

    def _writable(self):
        if self.scope.currentData() in ("system", "all"):
            QMessageBox.information(self, "config", T("請先選擇 local / global 範圍。", "Choose local or global scope first."))
            return False
        return True

    def _save_identity(self):
        if not self._writable():
            return
        for k, val in (("user.name", self.name.text().strip()), ("user.email", self.email.text().strip())):
            if val:
                self._git("config", *self._sc(), k, val)
        self.load()

    def _add(self):
        if not self._writable():
            return
        from .forms import Form
        f = Form(self, T("新增設定", "Add setting"))
        f.text("key", T("鍵", "Key"), placeholder="core.autocrlf")
        f.text("val", T("值", "Value"))
        f.check("add", T("新增多值項目 (--add)", "Add as extra value (--add)"), False)
        v = f.ask()
        if v and v["key"]:
            try:
                self._git("config", *self._sc(), *(["--add"] if v["add"] else []), v["key"], v["val"])
            except GitError as e:
                QMessageBox.warning(self, "config", str(e))
            self.load()

    def _edit(self):
        r = self.table.currentRow()
        if r < 0 or not self._writable():
            return
        k = self.table.item(r, 0).text()
        val, ok = QInputDialog.getText(self, k, T("值：", "Value:"), text=self.table.item(r, 1).text())
        if ok:
            try:
                self._git("config", *self._sc(), "--replace-all", k, val)
            except GitError as e:
                QMessageBox.warning(self, "config", str(e))
            self.load()

    def _unset(self):
        r = self.table.currentRow()
        if r < 0 or not self._writable():
            return
        k = self.table.item(r, 0).text()
        try:
            self._git("config", *self._sc(), "--unset-all", k)
        except GitError as e:
            QMessageBox.warning(self, "config", str(e))
        self.load()

    def _open(self):
        s = self.scope.currentData()
        if s == "all":
            return
        path = None
        if s == "global":
            path = os.path.expanduser("~/.gitconfig")
        elif s in ("local", "worktree") and self.rw:
            path = os.path.join(self.rw.repo.common_dir, "config" if s == "local" else "config.worktree")
        if path:
            TextFileEditor(self.rw, path, os.path.basename(path), parent=self).exec()
            self.load()


# =========================================================================== hooks
class HooksDialog(QDialog):
    HOOKS = ["pre-commit", "prepare-commit-msg", "commit-msg", "post-commit", "pre-rebase", "post-rewrite",
             "post-checkout", "post-merge", "pre-push", "pre-merge-commit", "pre-applypatch", "applypatch-msg",
             "post-applypatch", "pre-auto-gc", "reference-transaction", "push-to-checkout", "sendemail-validate",
             "fsmonitor-watchman", "p4-pre-submit", "post-index-change"]

    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        hp = rw.repo.config_get("core.hooksPath")
        self.dir = os.path.join(rw.repo.path, hp) if hp and not os.path.isabs(hp) else (hp or os.path.join(rw.repo.common_dir, "hooks"))
        self.setWindowTitle(T("Git Hooks 管理", "Git hooks"))
        self.resize(980, 600)
        v = QVBoxLayout(self)
        lbl = QLabel(T(f"Hooks 資料夾：{self.dir}", f"Hooks folder: {self.dir}"))
        lbl.setProperty("muted", True)
        v.addWidget(lbl)
        split = QSplitter(Qt.Horizontal)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._load)
        self.edit = QPlainTextEdit()
        self.edit.setFont(theme.mono_font())
        split.addWidget(self.list)
        split.addWidget(self.edit)
        split.setSizes([260, 700])
        v.addWidget(split, 1)
        btns = []
        self.btn_toggle = QPushButton(T("啟用 / 停用", "Enable / disable"))
        self.btn_toggle.clicked.connect(self._toggle)
        save = QPushButton(T("儲存", "Save"))
        save.setProperty("accent", True)
        save.clicked.connect(self._save)
        delete = QPushButton(T("刪除", "Delete"))
        delete.clicked.connect(self._delete)
        hp_btn = QPushButton(T("設定 core.hooksPath…", "Set core.hooksPath…"))
        hp_btn.clicked.connect(self._hooks_path)
        _close_box(self, v, [self.btn_toggle, delete, hp_btn, save])
        self.refresh()

    def refresh(self):
        cur = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.clear()
        for h in self.HOOKS:
            p = os.path.join(self.dir, h)
            on = os.path.exists(p)
            sample = os.path.exists(p + ".sample")
            state = T("● 啟用", "● enabled") if on else (T("○ 範例", "○ sample") if sample else T("— 無", "— none"))
            it = QListWidgetItem(f"{h}    {state}")
            it.setData(Qt.UserRole, h)
            if on:
                it.setForeground(QBrush(QColor(theme.C["ok"])))
            self.list.addItem(it)
            if h == cur:
                self.list.setCurrentItem(it)

    def _cur(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _load(self, *_):
        h = self._cur()
        if not h:
            return
        p = os.path.join(self.dir, h)
        for cand in (p, p + ".disabled", p + ".sample"):
            if os.path.exists(cand):
                with open(cand, encoding="utf-8", errors="replace") as fh:
                    self.edit.setPlainText(fh.read())
                return
        self.edit.setPlainText("#!/bin/sh\n# " + h + "\n\nexit 0\n")

    def _save(self):
        h = self._cur()
        if not h:
            return
        os.makedirs(self.dir, exist_ok=True)
        p = os.path.join(self.dir, h)
        if os.path.exists(p + ".disabled") and not os.path.exists(p):
            p = p + ".disabled"
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.edit.toPlainText())
        try:
            os.chmod(p, 0o755)
        except OSError:
            pass
        self.refresh()

    def _toggle(self):
        h = self._cur()
        if not h:
            return
        p = os.path.join(self.dir, h)
        if os.path.exists(p):
            os.replace(p, p + ".disabled")
        elif os.path.exists(p + ".disabled"):
            os.replace(p + ".disabled", p)
        else:
            self._save()
            if os.path.exists(p + ".disabled"):
                os.replace(p + ".disabled", p)
        self.refresh()

    def _delete(self):
        h = self._cur()
        if not h:
            return
        for cand in (os.path.join(self.dir, h), os.path.join(self.dir, h + ".disabled")):
            if os.path.exists(cand):
                os.remove(cand)
        self.refresh()
        self._load()

    def _hooks_path(self):
        cur = self.rw.repo.config_get("core.hooksPath")
        val, ok = QInputDialog.getText(self, "core.hooksPath", T("路徑（空白=預設）：", "Path (empty = default):"), text=cur)
        if ok:
            if val.strip():
                self.rw.git_sync(["config", "core.hooksPath", val.strip()])
            else:
                self.rw.git_sync(["config", "--unset", "core.hooksPath"])
            self.accept()


# =========================================================================== LFS
class LfsDialog(QDialog):
    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle("Git LFS")
        self.resize(860, 560)
        v = QVBoxLayout(self)
        if not rw.repo.lfs_available():
            l = QLabel(T("找不到 git-lfs。請先安裝 Git LFS（https://git-lfs.com），Git for Windows 已內建。",
                         "git-lfs was not found. Install Git LFS (https://git-lfs.com); Git for Windows bundles it."))
            l.setWordWrap(True)
            v.addWidget(l)
            _close_box(self, v)
            return
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel(T("追蹤的檔案樣式 (.gitattributes)", "Tracked patterns (.gitattributes)")))
        self.patterns = QListWidget()
        lv.addWidget(self.patterns, 1)
        row = QHBoxLayout()
        add = QPushButton(T("追蹤樣式…", "Track pattern…"))
        add.clicked.connect(self._track)
        rm = QPushButton(T("取消追蹤", "Untrack"))
        rm.clicked.connect(self._untrack)
        row.addWidget(add)
        row.addWidget(rm)
        lv.addLayout(row)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel(T("LFS 檔案", "LFS files")))
        self.files = QListWidget()
        rv.addWidget(self.files, 1)
        split.addWidget(left)
        split.addWidget(right)
        v.addWidget(split, 1)
        btns = []
        for txt, args in ((T("安裝 (install)", "Install"), ["lfs", "install"]),
                          (T("拉取 (pull)", "Pull"), ["lfs", "pull"]),
                          (T("提取 (fetch --all)", "Fetch --all"), ["lfs", "fetch", "--all"]),
                          (T("推送 (push --all)", "Push --all"), None),
                          (T("清理 (prune)", "Prune"), ["lfs", "prune"]),
                          (T("狀態", "Status"), ["lfs", "status"]),
                          (T("鎖定清單", "Locks"), ["lfs", "locks"]),
                          ("migrate…", "migrate")):
            b = QPushButton(txt)
            if args == "migrate":
                b.clicked.connect(self._migrate)
            elif args is None:
                b.clicked.connect(self._push_all)
            else:
                b.clicked.connect(lambda _=False, a=args: rw.run(a, "git " + " ".join(a), show_output=True,
                                                                 on_done=lambda *x: self.load()))
            btns.append(b)
        bl = QHBoxLayout()
        for b in btns:
            bl.addWidget(b)
        v.addLayout(bl)
        _close_box(self, v)
        self.load()

    def load(self):
        self.patterns.clear()
        out = self.rw.repo.git("lfs", "track", check=False)
        for l in out.splitlines():
            l = l.strip()
            if l and not l.startswith("Listing") and "(" in l:
                self.patterns.addItem(l.split(" (")[0])
        self.files.clear()
        for l in self.rw.repo.git("lfs", "ls-files", "-l", check=False).splitlines():
            self.files.addItem(l)

    def _track(self):
        p, ok = QInputDialog.getText(self, "git lfs track", T("樣式：", "Pattern:"), text="*.psd")
        if ok and p.strip():
            self.rw.run(["lfs", "track", p.strip()], "lfs track", on_done=lambda *x: self.load())

    def _untrack(self):
        it = self.patterns.currentItem()
        if it:
            self.rw.run(["lfs", "untrack", it.text()], "lfs untrack", on_done=lambda *x: self.load())

    def _push_all(self):
        rems = [r["name"] for r in self.rw.repo.remotes()]
        if rems:
            self.rw.run(["lfs", "push", "--all", rems[0]], "lfs push", show_output=True)

    def _migrate(self):
        from .forms import Form
        f = Form(self, "git lfs migrate", T("改寫歷史，將符合的檔案轉為 LFS。⚠ 會改寫提交。",
                                           "Rewrite history to move matching files into LFS. ⚠ Rewrites commits."))
        f.radio("mode", T("模式", "Mode"), [("info", "info"), ("import", "import"), ("export", "export")])
        f.text("include", "--include", "*.psd")
        f.check("everything", "--everything", False)
        v = f.ask()
        if v:
            args = ["lfs", "migrate", v["mode"], f"--include={v['include']}"]
            if v["everything"]:
                args.append("--everything")
            self.rw.run(args, "lfs migrate", show_output=True)


# =========================================================================== clean
class CleanDialog(QDialog):
    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("清理未追蹤檔案 (git clean)", "Clean untracked files"))
        self.resize(760, 520)
        v = QVBoxLayout(self)
        opts = QHBoxLayout()
        self.d = QCheckBox(T("包含資料夾 (-d)", "Directories (-d)"))
        self.d.setChecked(True)
        self.x = QCheckBox(T("也刪除被忽略的檔案 (-x)", "Also ignored files (-x)"))
        self.X = QCheckBox(T("只刪除被忽略的檔案 (-X)", "Only ignored files (-X)"))
        for c in (self.d, self.x, self.X):
            c.toggled.connect(self.load)
            opts.addWidget(c)
        opts.addStretch(1)
        v.addLayout(opts)
        self.list = QListWidget()
        v.addWidget(self.list, 1)
        sel_all = QPushButton(T("全選", "Select all"))
        sel_all.clicked.connect(lambda: [self.list.item(i).setCheckState(Qt.Checked) for i in range(self.list.count())])
        sel_none = QPushButton(T("全不選", "Select none"))
        sel_none.clicked.connect(lambda: [self.list.item(i).setCheckState(Qt.Unchecked) for i in range(self.list.count())])
        go = QPushButton(T("刪除選取項目", "Delete selected"))
        go.setStyleSheet("QPushButton{background:#c42b1c;border-color:#c42b1c;color:white;}")
        go.clicked.connect(self._go)
        _close_box(self, v, [sel_all, sel_none, go])
        self.load()

    def _flags(self):
        f = ["-d"] if self.d.isChecked() else []
        if self.X.isChecked():
            f.append("-X")
        elif self.x.isChecked():
            f.append("-x")
        return f

    def load(self, *_):
        out = self.rw.repo.git("clean", "-n", *self._flags(), check=False)
        self.list.clear()
        for l in out.splitlines():
            p = l.replace("Would remove ", "", 1)
            it = QListWidgetItem(p)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)

    def _go(self):
        paths = [self.list.item(i).text() for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.Checked]
        if not paths:
            return
        if not self.rw.confirm(T("清理", "Clean"), T(f"永久刪除 {len(paths)} 個項目？", f"Permanently delete {len(paths)} item(s)?"), danger=True):
            return
        self.rw.git_sync(["clean", "-f", *self._flags(), "--"] + paths)
        self.load()


# =========================================================================== maintenance
class MaintenanceDialog(QDialog):
    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("儲存庫維護", "Repository maintenance"))
        self.resize(760, 520)
        v = QVBoxLayout(self)
        grid = QHBoxLayout()
        col1, col2 = QVBoxLayout(), QVBoxLayout()
        items = [
            (T("垃圾回收 (gc)", "Garbage collect (gc)"), ["gc"]),
            (T("深度垃圾回收 (gc --aggressive)", "Aggressive gc"), ["gc", "--aggressive", "--prune=now"]),
            (T("清除無法到達的物件 (prune)", "Prune unreachable objects"), ["prune", "-v"]),
            (T("檢查完整性 (fsck)", "Check integrity (fsck)"), ["fsck", "--full"]),
            (T("重新打包 (repack -ad)", "Repack (repack -ad)"), ["repack", "-a", "-d"]),
            (T("寫入 commit-graph", "Write commit-graph"), ["commit-graph", "write", "--reachable"]),
            (T("執行 maintenance", "Run maintenance"), ["maintenance", "run"]),
            (T("啟用背景 maintenance", "Enable scheduled maintenance"), ["maintenance", "start"]),
            (T("停用背景 maintenance", "Disable scheduled maintenance"), ["maintenance", "unregister"]),
            (T("物件統計 (count-objects)", "Object stats"), ["count-objects", "-vH"]),
            (T("清除過期 reflog", "Expire reflog"), ["reflog", "expire", "--expire=now", "--all"]),
            (T("重新整理索引 (update-index --refresh)", "Refresh index"), ["update-index", "--refresh"]),
            (T("重新正規化換行 (add --renormalize)", "Renormalize line endings"), ["add", "--renormalize", "."]),
            (T("驗證 pack", "Verify packs"), ["verify-pack", "-v"]),
        ]
        for i, (txt, args) in enumerate(items):
            b = QPushButton(txt)
            if args[0] == "verify-pack":
                b.clicked.connect(self._verify_packs)
            else:
                b.clicked.connect(lambda _=False, a=args: rw.run(a, "git " + " ".join(a), on_done=self._out, quiet=True))
            (col1 if i % 2 == 0 else col2).addWidget(b)
        grid.addLayout(col1)
        grid.addLayout(col2)
        v.addLayout(grid)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(theme.mono_font())
        v.addWidget(self.output, 1)
        _close_box(self, v)

    def _out(self, code, out, err):
        self.output.appendPlainText(((out or "") + (err or "")).strip() or T("完成", "Done"))
        self.output.appendPlainText("—" * 40)

    def _verify_packs(self):
        packdir = os.path.join(self.rw.repo.common_dir, "objects", "pack")
        idx = [os.path.join(packdir, f) for f in os.listdir(packdir) if f.endswith(".idx")] if os.path.isdir(packdir) else []
        if idx:
            self.rw.run(["verify-pack", "-s"] + idx, "verify-pack", on_done=self._out, quiet=True, refresh=False)
        else:
            self.output.appendPlainText(T("沒有 pack 檔。", "No pack files."))


# =========================================================================== grep
class GrepWindow(QMainWindow):
    def __init__(self, rw):
        super().__init__(rw)
        self.rw = rw
        self.setWindowTitle(T("在檔案中搜尋 (git grep)", "Search in files (git grep)"))
        self.resize(1000, 640)
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText(T("搜尋文字或正規表示式…", "Text or regex…"))
        self.q.returnPressed.connect(self.search)
        self.rev = QLineEdit()
        self.rev.setPlaceholderText(T("版本（空白=工作區）", "Revision (empty = working tree)"))
        self.rev.setMaximumWidth(180)
        self.ci = QCheckBox(T("忽略大小寫", "Ignore case"))
        self.re = QCheckBox(T("正規表示式", "Regex"))
        self.word = QCheckBox(T("全字", "Whole word"))
        self.untracked = QCheckBox(T("含未追蹤", "Untracked"))
        go = QPushButton(T("搜尋", "Search"))
        go.setProperty("accent", True)
        go.clicked.connect(self.search)
        for wd in (self.q, self.rev, self.ci, self.re, self.word, self.untracked, go):
            bar.addWidget(wd, 1 if wd is self.q else 0)
        v.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([T("檔案 / 行", "File / line"), T("內容", "Text")])
        self.tree.setColumnWidth(0, 340)
        self.tree.itemDoubleClicked.connect(self._open)
        v.addWidget(self.tree)
        self.status = QLabel()
        self.status.setProperty("muted", True)
        v.addWidget(self.status)
        self.setCentralWidget(w)

    def search(self):
        q = self.q.text()
        if not q:
            return
        args = ["grep", "-n", "-I", "--null"]
        if self.ci.isChecked(): args.append("-i")
        if self.word.isChecked(): args.append("-w")
        args.append("-E" if self.re.isChecked() else "-F")
        if self.untracked.isChecked() and not self.rev.text().strip(): args.append("--untracked")
        args += ["-e", q]
        if self.rev.text().strip():
            args.append(self.rev.text().strip())
        out = self.rw.repo.git(*args, check=False)
        self.tree.clear()
        nodes, n = {}, 0
        for line in out.splitlines():
            parts = line.split("\0")
            if len(parts) < 3:
                continue
            fname, ln, text = parts[0], parts[1], "\0".join(parts[2:])
            if fname not in nodes:
                nodes[fname] = QTreeWidgetItem([fname, ""])
                self.tree.addTopLevelItem(nodes[fname])
            it = QTreeWidgetItem([ln, text.strip()])
            it.setData(0, Qt.UserRole, (fname, ln))
            nodes[fname].addChild(it)
            n += 1
            if n > 20000:
                break
        self.tree.expandAll() if len(nodes) < 50 else None
        self.status.setText(T(f"{n} 筆結果，{len(nodes)} 個檔案", f"{n} match(es) in {len(nodes)} file(s)"))

    def _open(self, it, _c):
        d = it.data(0, Qt.UserRole)
        if d:
            fname = d[0].split(":", 1)[-1] if self.rev.text().strip() else d[0]
            self.rw.open_path(os.path.join(self.rw.repo.path, fname))


# =========================================================================== text editor
class TextFileEditor(QDialog):
    def __init__(self, rw, path, title, parent=None):
        super().__init__(parent or rw)
        self.rw = rw
        self.path = path
        self.setWindowTitle(title)
        self.resize(760, 560)
        v = QVBoxLayout(self)
        lbl = QLabel(path)
        lbl.setProperty("muted", True)
        v.addWidget(lbl)
        self.edit = QPlainTextEdit()
        self.edit.setFont(theme.mono_font())
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.edit.setPlainText(fh.read())
        v.addWidget(self.edit, 1)
        bb = QDialogButtonBox()
        s = bb.addButton(T("儲存", "Save"), QDialogButtonBox.AcceptRole)
        s.setProperty("accent", True)
        bb.addButton(T("取消", "Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.edit.toPlainText())
        self.accept()
