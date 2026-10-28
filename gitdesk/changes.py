"""Working tree / staging area panel with commit box."""
from __future__ import annotations

import os

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit,
                               QPushButton, QSplitter, QToolButton, QVBoxLayout, QWidget)

from . import icons, theme
from .diffview import DiffView
from .git import FileStatus, Status
from .i18n import T

STATUS_TEXT = {
    "M": ("M", T("已修改", "Modified")), "A": ("A", T("新增", "Added")),
    "D": ("D", T("已刪除", "Deleted")), "R": ("R", T("重新命名", "Renamed")),
    "C": ("C", T("複製", "Copied")), "T": ("T", T("類型變更", "Type changed")),
    "?": ("?", T("未追蹤", "Untracked")), "U": ("U", T("衝突", "Conflict")),
}
STATUS_COLOR = {"M": "#ca5010", "A": "#107c10", "D": "#c42b1c", "R": "#0078d4", "C": "#0078d4",
                "T": "#8764b8", "?": "#107c10", "U": "#c42b1c"}


class FileList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setAlternatingRowColors(False)

    def set_files(self, files, side):
        keep = {it.data(Qt.UserRole).path for it in self.selectedItems()}
        cur = self.currentItem().data(Qt.UserRole).path if self.currentItem() else None
        self.blockSignals(True)
        self.clear()
        for f in files:
            code = f.x if side == "staged" else f.y
            if f.kind == "?":
                code = "?"
            if f.kind == "u":
                code = "U"
            letter, desc = STATUS_TEXT.get(code, (code, code))
            name = os.path.basename(f.path) or f.path
            d = os.path.dirname(f.path)
            label = f"{letter}   {name}" + (f"    {d}" if d else "")
            if f.kind == "2" and f.orig:
                label += f"   ← {f.orig}"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, f)
            it.setToolTip(f"{desc}: {f.path}")
            it.setForeground(QBrush(QColor(STATUS_COLOR.get(code, theme.C["text"]))))
            self.addItem(it)
        if cur:
            for i in range(self.count()):
                if self.item(i).data(Qt.UserRole).path == cur:
                    self.setCurrentRow(i, QItemSelectionModel.NoUpdate)
                    break
        for i in range(self.count()):
            if self.item(i).data(Qt.UserRole).path in keep:
                self.item(i).setSelected(True)
        self.blockSignals(False)

    def selected_files(self):
        return [it.data(Qt.UserRole) for it in self.selectedItems()]


class Section(QWidget):
    def __init__(self, title, buttons, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        h = QHBoxLayout()
        h.setContentsMargins(2, 0, 2, 0)
        self.label = QLabel(title)
        self.label.setProperty("h2", True)
        self._title = title
        h.addWidget(self.label)
        h.addStretch(1)
        self.buttons = {}
        for key, text, ic in buttons:
            b = QPushButton(icons.icon(ic), text)
            b.setProperty("flat", True)
            h.addWidget(b)
            self.buttons[key] = b
        v.addLayout(h)
        self.list = FileList()
        v.addWidget(self.list, 1)

    def set_count(self, n):
        self.label.setText(f"{self._title}  ({n})")


class ChangesPanel(QWidget):
    def __init__(self, rw, parent=None):
        super().__init__(parent)
        self.rw = rw
        self.status: Status = None
        self._current = None   # (side, FileStatus)
        self._shown_key = None
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        outer.addWidget(split)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)
        vs = QSplitter(Qt.Vertical)
        self.sec_conf = Section(T("衝突 Conflicts", "Conflicts"), [
            ("resolve", T("全部標記已解決", "Mark all resolved"), "check")])
        self.sec_un = Section(T("未暫存", "Unstaged"), [
            ("discard", T("全部捨棄", "Discard all"), "trash"),
            ("stage", T("全部暫存", "Stage all"), "plus")])
        self.sec_st = Section(T("已暫存", "Staged"), [
            ("unstage", T("全部取消暫存", "Unstage all"), "minus")])
        vs.addWidget(self.sec_conf)
        vs.addWidget(self.sec_un)
        vs.addWidget(self.sec_st)
        vs.setSizes([80, 300, 200])
        lv.addWidget(vs, 1)

        # commit box
        box = QFrame()
        box.setObjectName("card")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.setSpacing(6)
        self.summary = QLineEdit()
        self.summary.setPlaceholderText(T("提交摘要（必填）", "Commit summary (required)"))
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText(T("詳細描述（選填）", "Description (optional)"))
        self.body.setFixedHeight(70)
        self.counter = QLabel("")
        self.counter.setProperty("muted", True)
        self.summary.textChanged.connect(self._update_commit_enabled)
        bl.addWidget(self.summary)
        bl.addWidget(self.body)
        opts = QHBoxLayout()
        self.chk_amend = QCheckBox(T("修訂上次提交", "Amend"))
        self.chk_signoff = QCheckBox(T("簽署", "Sign-off"))
        self.chk_gpg = QCheckBox(T("GPG 簽章", "GPG sign"))
        self.chk_noverify = QCheckBox(T("略過 hooks", "No verify"))
        self.chk_empty = QCheckBox(T("允許空提交", "Allow empty"))
        self.chk_amend.toggled.connect(self._amend_toggled)
        for c in (self.chk_amend, self.chk_signoff, self.chk_gpg, self.chk_noverify, self.chk_empty):
            opts.addWidget(c)
        opts.addStretch(1)
        bl.addLayout(opts)
        btns = QHBoxLayout()
        btns.addWidget(self.counter, 1)
        self.btn_commit_push = QPushButton(T("提交並推送", "Commit && Push"))
        self.btn_commit = QPushButton(icons.icon("commit", "#ffffff"), T("提交", "Commit"))
        self.btn_commit.setProperty("accent", True)
        btns.addWidget(self.btn_commit_push)
        btns.addWidget(self.btn_commit)
        bl.addLayout(btns)
        self.btn_commit.clicked.connect(lambda: self.commit(push=False))
        self.btn_commit_push.clicked.connect(lambda: self.commit(push=True))
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self.commit(False))
        lv.addWidget(box)
        split.addWidget(left)

        self.diff = DiffView(self)
        self.diff.patchRequested.connect(self._apply_patch)
        self.diff.optionsChanged.connect(lambda: (self._prefetch(), self.show_current_diff()))
        split.addWidget(self.diff)
        split.setSizes([420, 800])
        split.setStretchFactor(1, 1)

        # wiring
        for sec, side in ((self.sec_un, "unstaged"), (self.sec_st, "staged"), (self.sec_conf, "conflict")):
            sec.list.itemSelectionChanged.connect(lambda s=side: self._sel_changed(s))
            sec.list.itemDoubleClicked.connect(lambda it, s=side: self._dbl(s, it))
            sec.list.customContextMenuRequested.connect(lambda pos, s=side, l=sec.list: self._menu(s, l, pos))
        self.sec_un.buttons["stage"].clicked.connect(self.stage_all)
        self.sec_un.buttons["discard"].clicked.connect(self.discard_all)
        self.sec_st.buttons["unstage"].clicked.connect(self.unstage_all)
        self.sec_conf.buttons["resolve"].clicked.connect(
            lambda: self.rw.git_sync(["add", "--"] + [f.path for f in self.status.conflicts]))
        QShortcut(QKeySequence("Space"), self.sec_un.list, activated=lambda: self.stage(self.sec_un.list.selected_files()))
        QShortcut(QKeySequence("Space"), self.sec_st.list, activated=lambda: self.unstage(self.sec_st.list.selected_files()))
        QShortcut(QKeySequence.Delete, self.sec_un.list, activated=lambda: self.discard(self.sec_un.list.selected_files()))
        self._update_commit_enabled()

    # ------------------------------------------------------------------ update
    def set_status(self, st: Status):
        self.status = st
        self.sec_conf.setVisible(bool(st.conflicts))
        self.sec_conf.list.set_files(st.conflicts, "conflict")
        self.sec_conf.set_count(len(st.conflicts))
        self.sec_un.list.set_files(st.unstaged, "unstaged")
        self.sec_un.set_count(len(st.unstaged))
        self.sec_st.list.set_files(st.staged, "staged")
        self.sec_st.set_count(len(st.staged))
        # keep showing the same file if it still exists, otherwise clear the diff
        if self._current:
            side, f = self._current
            pool = {"unstaged": st.unstaged, "staged": st.staged, "conflict": st.conflicts}[side]
            match = next((x for x in pool if x.path == f.path), None)
            if match:
                self._current = (side, match)
                self.show_current_diff()
            else:
                self._current = None
                self._shown_key = None
                self.diff.set_message(T("選擇一個檔案以檢視差異", "Select a file to see its diff"))
        elif not (st.unstaged or st.staged or st.conflicts):
            self.diff.set_message(T("工作區是乾淨的，沒有變更。", "Working tree clean — nothing to commit."))
        self._update_commit_enabled()
        self._prefetch()

    def _update_commit_enabled(self):
        ok = bool(self.summary.text().strip())
        has = bool(self.status and self.status.staged) or self.chk_amend.isChecked() or self.chk_empty.isChecked()
        self.btn_commit.setEnabled(ok and has)
        self.btn_commit_push.setEnabled(ok and has)
        n = len(self.status.staged) if self.status else 0
        self.counter.setText(T(f"{n} 個檔案已暫存", f"{n} file(s) staged"))

    def _amend_toggled(self, on):
        if on and not self.summary.text().strip() and self._has_head():
            msg = self.rw.repo.git("log", "-1", "--format=%B").rstrip()
            s, _, b = msg.partition("\n")
            self.summary.setText(s)
            self.body.setPlainText(b.strip())
        self._update_commit_enabled()

    def _has_head(self):
        st = self.status
        return bool(st and st.oid and st.oid != "(initial)")

    # ------------------------------------------------------------------ selection
    def _sel_changed(self, side):
        lst = {"unstaged": self.sec_un.list, "staged": self.sec_st.list, "conflict": self.sec_conf.list}[side]
        files = lst.selected_files()
        if not files:
            return
        for other in (self.sec_un.list, self.sec_st.list, self.sec_conf.list):
            if other is not lst:
                other.blockSignals(True)
                other.clearSelection()
                other.blockSignals(False)
        cur = lst.currentItem()
        f = cur.data(Qt.UserRole) if cur and cur.isSelected() else files[0]
        self._current = (side, f)
        self.show_current_diff()

    # ------------------------------------------------------------------ diffs (async + cached)
    def _stamp(self, side, f):
        """Cheap fingerprint of what a diff depends on (file + index timestamps)."""
        def st(p):
            try:
                x = os.stat(p)
                return (x.st_mtime_ns, x.st_size)
            except OSError:
                return None
        idx = st(os.path.join(self.rw.repo.git_dir, "index"))
        if side == "staged":
            return (idx,)
        return (idx, st(os.path.join(self.rw.repo.path, f.path)))

    def _key(self, side, f, opts):
        return ("wt", side, f.path, f.x, f.y, f.kind, f.submodule, tuple(opts), self._stamp(side, f))

    def _compute(self, side, f, opts):
        """Runs on the worker thread."""
        repo = self.rw.repo
        if f.submodule:
            txt = repo.git("diff", "--submodule=log", *(["--cached"] if side == "staged" else []),
                           "--", f.path, check=False)
            return ("diff", txt, "readonly", f.path)
        if side == "staged":
            return ("diff", repo.diff_staged(f.path, opts), "staged", f.path)
        if side == "conflict":
            return ("diff", repo.git("diff", "--no-color", *opts, "--", f.path, check=False),
                    "readonly", f.path + T("（衝突）", " (conflict)"))
        if f.kind == "?" and os.path.isdir(os.path.join(repo.path, f.path)):
            return ("msg", f.path)
        return ("diff", repo.diff_worktree(f.path, untracked=f.kind == "?", opts=opts), "unstaged", f.path)

    def _display(self, res):
        if res[0] == "msg":
            self.diff.set_message(res[1])
        else:
            self.diff.set_diff(res[1], res[2], res[3])

    def show_current_diff(self, force=False):
        if not self._current:
            return
        side, f = self._current
        opts = self.diff.diff_opts()
        key = self._key(side, f, opts)
        if key == self._shown_key and not force:
            return                                  # nothing changed: keep scroll/selection
        cache = self.rw.diff_cache
        hit = cache.get(key)
        if hit is not None:
            self._shown_key = key
            self._display(hit)
            return
        self.diff.title.setText(f.path + "  …")

        def done(res, key=key, want=(side, f.path)):
            cache.put(key, res)
            if self._current and (self._current[0], self._current[1].path) == want:
                self._shown_key = key
                self._display(res)
        self.rw.worker.submit(lambda: self._compute(side, f, opts), done, key="diff")

    def status_touched(self):
        """Status text unchanged but files may have been edited again: re-check the shown diff."""
        self.show_current_diff()

    def _prefetch(self):
        """Pre-compute diffs of listed files in the background so clicks are instant."""
        if not self.status:
            return
        opts = self.diff.diff_opts()
        cache = self.rw.diff_cache
        jobs = [("conflict", f) for f in self.status.conflicts[:20]] + \
               [("unstaged", f) for f in self.status.unstaged[:60]] + \
               [("staged", f) for f in self.status.staged[:60]]
        for side, f in jobs:
            key = self._key(side, f, opts)
            if key in cache:
                continue
            self.rw.worker.submit(lambda side=side, f=f: self._compute(side, f, opts),
                                  lambda res, key=key: cache.put(key, res),
                                  key=("pre",) + key, low=True)

    def _dbl(self, side, it):
        f = it.data(Qt.UserRole)
        if side == "unstaged":
            self.stage([f])
        elif side == "staged":
            self.unstage([f])
        else:
            from .tools import ConflictEditor
            ConflictEditor(self.rw, f.path, self).exec()

    # ------------------------------------------------------------------ operations
    def stage(self, files):
        if files:
            self.rw.git_sync(["add", "-A", "--"] + [f.path for f in files])

    def unstage(self, files):
        if not files:
            return
        paths = [f.path for f in files]
        if self._has_head():
            self.rw.git_sync(["restore", "--staged", "--"] + paths)
        else:
            self.rw.git_sync(["rm", "--cached", "-r", "-q", "--"] + paths)

    def discard(self, files):
        if not files:
            return
        names = "\n".join(f.path for f in files[:15]) + ("\n…" if len(files) > 15 else "")
        if not self.rw.confirm(T("捨棄變更", "Discard changes"),
                               T("確定要永久捨棄這些檔案的變更嗎？此動作無法復原。\n\n",
                                 "Permanently discard changes in these files? This cannot be undone.\n\n") + names,
                               danger=True):
            return
        untracked = [f.path for f in files if f.kind == "?"]
        tracked = [f.path for f in files if f.kind != "?"]
        if tracked:
            self.rw.git_sync(["restore", "--"] + tracked)
        if untracked:
            self.rw.git_sync(["clean", "-f", "-d", "--"] + untracked)

    def stage_all(self):
        self.rw.git_sync(["add", "-A"])

    def unstage_all(self):
        if self._has_head():
            self.rw.git_sync(["reset", "-q"])
        else:
            self.rw.git_sync(["rm", "--cached", "-r", "-q", "."])

    def discard_all(self):
        if not self.rw.confirm(T("全部捨棄", "Discard all"),
                               T("要捨棄所有未暫存的變更嗎？（未追蹤檔案也會刪除）此動作無法復原。",
                                 "Discard ALL unstaged changes? (untracked files will be deleted too) This cannot be undone."),
                               danger=True):
            return
        if self.status and any(f.kind != "?" for f in self.status.unstaged):
            self.rw.git_sync(["restore", "."])
        if self.status and any(f.kind == "?" for f in self.status.unstaged):
            self.rw.git_sync(["clean", "-f", "-d"])

    def _apply_patch(self, patch, args, what):
        if what == "discard" and not self.rw.confirm(
                T("捨棄", "Discard"), T("確定要捨棄選取的變更嗎？", "Discard the selected changes?"), danger=True):
            return
        try:
            self.rw.repo.apply_patch(patch, args)
        except Exception as e:
            self.rw.error(T("套用失敗", "Patch failed"), str(e))
        self.rw.refresh({"index"})

    # ------------------------------------------------------------------ commit
    def commit(self, push=False):
        if not self.btn_commit.isEnabled():
            return
        msg = self.summary.text().strip()
        body = self.body.toPlainText().strip()
        if body:
            msg += "\n\n" + body
        args = ["commit", "-F", self.rw.temp_file(msg, "COMMIT_MSG")]
        if self.chk_amend.isChecked():
            args.append("--amend")
        if self.chk_signoff.isChecked():
            args.append("--signoff")
        if self.chk_gpg.isChecked():
            args.append("-S")
        if self.chk_noverify.isChecked():
            args.append("--no-verify")
        if self.chk_empty.isChecked():
            args.append("--allow-empty")

        def done(code, out, err):
            if code == 0:
                self.summary.clear()
                self.body.clear()
                self.chk_amend.setChecked(False)
                self.chk_empty.setChecked(False)
                if push:
                    from . import actions
                    actions.push_quick(self.rw)
        self.rw.run(args, T("提交中…", "Committing…"), done)

    # ------------------------------------------------------------------ context menu
    def _menu(self, side, lst, pos):
        files = lst.selected_files()
        if not files:
            return
        m = QMenu(self)
        rw = self.rw
        if side == "unstaged":
            m.addAction(icons.icon("plus"), T("暫存", "Stage"), lambda: self.stage(files))
            m.addAction(icons.icon("trash"), T("捨棄變更…", "Discard changes…"), lambda: self.discard(files))
            m.addSeparator()
            if any(f.kind == "?" for f in files):
                ig = m.addMenu(T("加入 .gitignore", "Add to .gitignore"))
                f0 = files[0].path
                ext = os.path.splitext(f0)[1]
                ig.addAction(f0, lambda: self._ignore([f.path for f in files]))
                if ext:
                    ig.addAction(f"*{ext}", lambda: self._ignore([f"*{ext}"]))
                d = os.path.dirname(f0)
                if d:
                    ig.addAction(d + "/", lambda: self._ignore([d + "/"]))
                m.addAction(T("意圖加入 (add -N)", "Intent to add (add -N)"),
                            lambda: rw.git_sync(["add", "-N", "--"] + [f.path for f in files]))
        elif side == "staged":
            m.addAction(icons.icon("minus"), T("取消暫存", "Unstage"), lambda: self.unstage(files))
        else:
            from .tools import ConflictEditor
            m.addAction(T("在合併編輯器中解決…", "Resolve in merge editor…"),
                        lambda: ConflictEditor(rw, files[0].path, self).exec())
            m.addAction(T("使用我方版本 (ours)", "Use ours"),
                        lambda: self._take("--ours", files))
            m.addAction(T("使用對方版本 (theirs)", "Use theirs"),
                        lambda: self._take("--theirs", files))
            m.addAction(T("標記為已解決 (git add)", "Mark resolved (git add)"),
                        lambda: rw.git_sync(["add", "--"] + [f.path for f in files]))
            m.addAction(T("以 git rm 標記刪除", "Resolve as deleted (git rm)"),
                        lambda: rw.git_sync(["rm", "--"] + [f.path for f in files]))
            m.addAction(T("外部合併工具 (mergetool)", "External merge tool"),
                        lambda: rw.run(["mergetool", "--no-prompt", "--"] + [f.path for f in files],
                                       "mergetool"))
        m.addSeparator()
        f0 = files[0]
        if f0.kind != "?":
            m.addAction(icons.icon("history"), T("檔案歷史", "File history"),
                        lambda: rw.open_file_history(f0.path))
            m.addAction(T("逐行追溯 (blame)", "Blame"), lambda: rw.open_blame(f0.path))
            m.addAction(T("停止追蹤 (rm --cached)", "Untrack (rm --cached)"),
                        lambda: rw.git_sync(["rm", "--cached", "-r", "--"] + [f.path for f in files]))
            sub = m.addMenu(T("索引旗標", "Index flags"))
            sub.addAction("assume-unchanged", lambda: rw.git_sync(["update-index", "--assume-unchanged", "--"] + [f.path for f in files]))
            sub.addAction("no-assume-unchanged", lambda: rw.git_sync(["update-index", "--no-assume-unchanged", "--"] + [f.path for f in files]))
            sub.addAction("skip-worktree", lambda: rw.git_sync(["update-index", "--skip-worktree", "--"] + [f.path for f in files]))
            sub.addAction("no-skip-worktree", lambda: rw.git_sync(["update-index", "--no-skip-worktree", "--"] + [f.path for f in files]))
            sub.addAction("chmod +x", lambda: rw.git_sync(["update-index", "--chmod=+x", "--"] + [f.path for f in files]))
            sub.addAction("chmod -x", lambda: rw.git_sync(["update-index", "--chmod=-x", "--"] + [f.path for f in files]))
        m.addAction(T("重新命名/移動 (git mv)…", "Rename / move (git mv)…"), lambda: self._mv(f0))
        m.addAction(T("開啟檔案", "Open file"), lambda: rw.open_path(os.path.join(rw.repo.path, f0.path)))
        m.addAction(T("在資料夾中顯示", "Show in folder"),
                    lambda: rw.open_path(os.path.dirname(os.path.join(rw.repo.path, f0.path))))
        m.addAction(T("複製路徑", "Copy path"), lambda: rw.copy_text("\n".join(f.path for f in files)))
        m.exec(lst.viewport().mapToGlobal(pos))

    def _take(self, which, files):
        paths = [f.path for f in files]
        self.rw.git_sync(["checkout", which, "--"] + paths)
        self.rw.git_sync(["add", "--"] + paths)

    def _ignore(self, patterns):
        p = os.path.join(self.rw.repo.path, ".gitignore")
        existing = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        with open(p, "a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            for pat in patterns:
                fh.write(pat + "\n")
        self.rw.refresh({"worktree"})

    def _mv(self, f):
        from PySide6.QtWidgets import QInputDialog
        new, ok = QInputDialog.getText(self, "git mv", T("新路徑：", "New path:"), text=f.path)
        if ok and new.strip() and new.strip() != f.path:
            self.rw.git_sync(["mv", "--", f.path, new.strip()])
