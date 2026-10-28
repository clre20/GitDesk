"""One open repository: sidebar + changes/history, live-synced with disk."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSplitter,
                               QStackedWidget, QVBoxLayout, QWidget, QDialog, QPlainTextEdit,
                               QDialogButtonBox)

from . import actions, icons, theme
from .changes import ChangesPanel
from .git import GitError, LOG, Repo
from .history import HistoryPanel
from .i18n import T
from .sidebar import Sidebar
from .watcher import RepoWatcher
from .worker import LRU, Worker


class Banner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 6, 8, 6)
        self.icon = QLabel()
        self.icon.setPixmap(icons.icon("alert", theme.C["warn_fg"]).pixmap(18, 18))
        self.label = QLabel()
        self.label.setWordWrap(True)
        h.addWidget(self.icon)
        h.addWidget(self.label, 1)
        self.btns = []
        self.box = QHBoxLayout()
        h.addLayout(self.box)

    def set(self, text, buttons):
        sig = (text, tuple(b[0] for b in buttons))
        if sig == getattr(self, "_sig", None) and self.isVisible():
            return
        self._sig = sig
        self.label.setText(text)
        for b in self.btns:
            b.deleteLater()
        self.btns = []
        for txt, fn, accent in buttons:
            b = QPushButton(txt)
            if accent:
                b.setProperty("accent", True)
            b.clicked.connect(fn)
            self.box.addWidget(b)
            self.btns.append(b)
        self.show()


class RepoWidget(QWidget):
    titleChanged = Signal()
    busyChanged = Signal(bool, str)

    def __init__(self, path: str, main=None, parent=None):
        super().__init__(parent)
        self.repo = Repo(path)
        self.main = main
        self._tasks = []
        self._queue = []
        self._busy = False
        self._last_status_raw = None
        self._tmp = tempfile.mkdtemp(prefix="gitdesk-")

        v = QVBoxLayout(self)
        v.setContentsMargins(8, 4, 8, 4)
        v.setSpacing(6)
        self.banner = Banner()
        self.banner.hide()
        v.addWidget(self.banner)

        split = QSplitter(Qt.Horizontal)
        v.addWidget(split, 1)
        self.sidebar = Sidebar()
        self.sidebar.setMinimumWidth(200)
        split.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        self.changes = ChangesPanel(self)
        self.history = HistoryPanel(self)
        self.stack.addWidget(self.changes)
        self.stack.addWidget(self.history)
        split.addWidget(self.stack)
        split.setSizes([260, 1100])
        split.setStretchFactor(1, 1)

        self.sidebar.navigate.connect(self.show_view)
        self.sidebar.activated.connect(self._side_activate)
        self.sidebar.selected.connect(self._side_select)
        self.sidebar.contextRequested.connect(self._side_menu)

        self.worker = Worker(self)      # interactive reads (diffs, commit details)
        self.bg = Worker(self)          # refresh / status / history loading
        self.diff_cache = LRU(400)
        self._refresh_pending = set()
        self._refresh_inflight = False
        self.status_duration = 0.05
        self._first = True

        self.watcher = RepoWatcher(self.repo, self, worker=self.bg)
        self.watcher.changed.connect(self.refresh)

        # first load is synchronous so the window opens fully populated
        self._apply_refresh(self._load({"refs", "index", "state", "worktree", "config"}))
        st = self.changes.status
        has_changes = st and (st.unstaged or st.staged or st.conflicts)
        self.show_view("changes" if has_changes or not st.oid or st.oid == "(initial)" else "history")

    # ------------------------------------------------------------------ views
    def show_view(self, which):
        self.stack.setCurrentWidget(self.changes if which == "changes" else self.history)
        self.sidebar.select_nav(which)

    def title(self):
        return self.repo.name

    def current_branch(self):
        st = self.changes.status
        if st and st.head and st.head != "(detached)":
            return st.head
        return ""

    # ------------------------------------------------------------------ refresh
    def refresh(self, kinds=None):
        """Request a refresh; the git reads run on a background thread."""
        self._refresh_pending |= set(kinds or {"refs", "index", "state", "worktree"})
        if not self._refresh_inflight:
            self._start_refresh()

    def _start_refresh(self):
        kinds, self._refresh_pending = self._refresh_pending, set()
        if not kinds:
            return
        self._refresh_inflight = True
        self.bg.submit(lambda: self._load(kinds), self._apply_refresh, key="refresh")

    def _load(self, kinds):
        """Runs on the worker thread: collect everything the UI needs."""
        import time
        repo = self.repo
        if not os.path.isdir(repo.git_dir):
            return None
        t0 = time.monotonic()
        st = repo.status()
        self.status_duration = time.monotonic() - t0
        refs = None
        if kinds & {"refs", "state", "config"}:
            refs = (repo.branches(), repo.remote_branches(), repo.remotes(), repo.tags(),
                    repo.stashes(), repo.submodules(), repo.worktrees())
        return kinds, st, refs

    def _apply_refresh(self, res):
        self._refresh_inflight = False
        if res:
            kinds, st, refs = res
            kinds = set(kinds)
            if st.raw != self._last_status_raw:
                self._last_status_raw = st.raw
                self.changes.set_status(st)
                self.sidebar.set_changes_count(len(st.unstaged) + len(st.staged) + len(st.conflicts))
                kinds.add("status")
            elif kinds & {"worktree", "index"}:
                self.changes.status_touched()
            if refs is not None:
                self.sidebar.populate(*refs, self.repo.path)
                self.history.mark_dirty()
            if kinds & {"refs", "state", "status"} or self._first:
                self._update_banner(st)
                self.titleChanged.emit()
            if not self._first and ("config" in kinds or "state" in kinds):
                self.watcher.rescan()
            self._first = False
            if self.main:
                self.main.update_status_bar(self)
        if self._refresh_pending:
            self._start_refresh()

    def refresh_all(self):
        self._last_status_raw = None
        self.history._sig = None
        self.refresh({"refs", "index", "state", "worktree", "config"})

    def _update_banner(self, st):
        op = self.repo.operation_state()
        nconf = len(st.conflicts)
        cf = T(f"（{nconf} 個衝突檔案）", f" ({nconf} conflicted file(s))") if nconf else ""
        if op == "merge":
            self.banner.set(T("合併進行中", "Merge in progress") + cf, [
                (T("中止合併", "Abort merge"), lambda: self.run(["merge", "--abort"], "merge --abort"), False),
                (T("繼續 (提交)", "Continue (commit)"), lambda: self.run(["merge", "--continue"], "merge --continue"), True)])
        elif op == "rebase":
            prog = self.repo.rebase_progress()
            p = f" {prog[0]}/{prog[1]}" if prog else ""
            self.banner.set(T("變基進行中", "Rebase in progress") + p + cf, [
                (T("中止", "Abort"), lambda: self.run(["rebase", "--abort"], "rebase --abort"), False),
                (T("略過此提交", "Skip"), lambda: self.run(["rebase", "--skip"], "rebase --skip"), False),
                (T("繼續", "Continue"), lambda: self.run(["rebase", "--continue"], "rebase --continue"), True)])
        elif op == "am":
            self.banner.set(T("套用修補檔 (am) 進行中", "Applying patches (am)") + cf, [
                (T("中止", "Abort"), lambda: self.run(["am", "--abort"], "am --abort"), False),
                (T("略過", "Skip"), lambda: self.run(["am", "--skip"], "am --skip"), False),
                (T("繼續", "Continue"), lambda: self.run(["am", "--continue"], "am --continue"), True)])
        elif op == "cherry-pick":
            self.banner.set(T("揀選進行中", "Cherry-pick in progress") + cf, [
                (T("中止", "Abort"), lambda: self.run(["cherry-pick", "--abort"], "cherry-pick --abort"), False),
                (T("略過", "Skip"), lambda: self.run(["cherry-pick", "--skip"], "cherry-pick --skip"), False),
                (T("繼續", "Continue"), lambda: self.run(["cherry-pick", "--continue"], "cherry-pick --continue"), True)])
        elif op == "revert":
            self.banner.set(T("還原進行中", "Revert in progress") + cf, [
                (T("中止", "Abort"), lambda: self.run(["revert", "--abort"], "revert --abort"), False),
                (T("略過", "Skip"), lambda: self.run(["revert", "--skip"], "revert --skip"), False),
                (T("繼續", "Continue"), lambda: self.run(["revert", "--continue"], "revert --continue"), True)])
        elif op == "bisect":
            self.banner.set(T("二分搜尋 (bisect) 進行中 — 測試目前簽出的提交後標記結果",
                              "Bisecting — test the checked-out commit, then mark it"), [
                (T("結束 (reset)", "End (reset)"), lambda: self.run(["bisect", "reset"], "bisect reset"), False),
                (T("檢視記錄", "Log"), lambda: self.run(["bisect", "log"], "bisect log", show_output=True), False),
                (T("略過", "Skip"), lambda: actions.bisect(self, "skip"), False),
                (T("壞 (bad)", "Bad"), lambda: actions.bisect(self, "bad"), False),
                (T("好 (good)", "Good"), lambda: actions.bisect(self, "good"), True)])
        elif st.head == "(detached)":
            self.banner.set(T("目前處於分離 HEAD 狀態（不在任何分支上）", "You are in detached HEAD state (not on a branch)"), [
                (T("在此建立分支…", "Create branch here…"), lambda: actions.new_branch(self, "HEAD"), True)])
        else:
            self.banner.hide()

    # ------------------------------------------------------------------ git execution
    def run(self, args, title="", on_done=None, env=None, show_output=False, refresh=True,
            program=None, quiet=False):
        """Run a git command asynchronously (queued), then refresh."""
        self._queue.append((list(args), title, on_done, env, show_output, refresh, program, quiet))
        if not self._busy:
            self._next()

    def _next(self):
        if not self._queue:
            self._busy = False
            self.busyChanged.emit(False, "")
            return
        args, title, on_done, env, show_output, refresh, program, quiet = self._queue.pop(0)
        self._busy = True
        self.busyChanged.emit(True, title or ("git " + " ".join(args[:2])))
        from .git import GitTask
        task = GitTask(args, self.repo.path, env=env, parent=self, program=program)
        self._tasks.append(task)

        def done(code, out, err, task=task):
            if task in self._tasks:
                self._tasks.remove(task)
            text = (out + ("\n" if out and err else "") + err).strip()
            if code != 0 and not quiet:
                self._report_failure(args, text)
            elif show_output:
                self.show_text(title or "git", text or T("（沒有輸出）", "(no output)"))
            if on_done:
                try:
                    on_done(code, out, err)
                except Exception as ex:  # keep the queue alive
                    LOG.entry.emit("err", repr(ex))
            if refresh:
                self.refresh_all()
            task.deleteLater()
            QTimer.singleShot(0, self._next)
        task.done.connect(done)
        task.start()

    def _report_failure(self, args, text):
        if self.repo.operation_state() in ("merge", "rebase", "cherry-pick", "revert", "am") and \
                ("CONFLICT" in text or "conflict" in text.lower()):
            self.show_view("changes")
            self.error(T("發生衝突", "Conflicts"), text[-3000:])
            return
        self.error("git " + " ".join(args[:3]), text or T("命令失敗", "Command failed"))

    def git_sync(self, args, refresh=True, log=True):
        """Quick synchronous git call with error reporting."""
        try:
            out = self.repo.git(*args, log=log)
        except GitError as e:
            self.error("git " + " ".join(args[:3]), str(e))
            out = None
        if refresh:
            self.refresh({"index", "refs"} if args and args[0] in ("branch", "tag", "remote", "stash", "notes", "update-ref") else {"index"})
        return out

    def is_busy(self):
        return self._busy

    # ------------------------------------------------------------------ ui helpers
    def temp_file(self, content, name="tmp"):
        p = os.path.join(self._tmp, name)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return p

    def confirm(self, title, text, danger=False):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
        yes = box.addButton(T("確定", "OK"), QMessageBox.AcceptRole)
        box.addButton(T("取消", "Cancel"), QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def error(self, title, text):
        from .errors import show_git_error
        show_git_error(self, title, text)

    def show_text(self, title, text):
        d = QDialog(self)
        d.setWindowTitle(title)
        d.resize(760, 480)
        v = QVBoxLayout(d)
        e = QPlainTextEdit(text)
        e.setReadOnly(True)
        e.setFont(theme.mono_font())
        v.addWidget(e)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(d.reject)
        bb.button(QDialogButtonBox.Close).setText(T("關閉", "Close"))
        v.addWidget(bb)
        d.exec()

    def copy_text(self, t):
        QGuiApplication.clipboard().setText(t)

    def open_path(self, p):
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def open_file_history(self, path):
        from .tools import FileHistoryWindow
        FileHistoryWindow(self, path).show()

    def open_blame(self, path, rev=None):
        from .tools import BlameWindow
        BlameWindow(self, path, rev).show()

    # ------------------------------------------------------------------ sidebar
    def _side_select(self, kind, name, data):
        if kind in ("branch", "remote_branch", "tag"):
            self.show_view("history")
            self.history.jump_to(name if kind != "tag" else "refs/tags/" + name)
        elif kind == "stash":
            self.show_view("history")
            self.history._cur_sha = None
            self.history._show_commit(data.sha)

    def _side_activate(self, kind, name, data):
        if kind == "branch":
            actions.checkout(self, name)
        elif kind == "remote_branch":
            actions.checkout_remote(self, name)
        elif kind == "tag":
            actions.checkout_commit(self, "refs/tags/" + name)
        elif kind == "stash":
            actions.stash_apply(self, name, pop=False)
        elif kind == "submodule":
            if self.main:
                self.main.open_repo(os.path.join(self.repo.path, name))
        elif kind == "worktree":
            if self.main:
                self.main.open_repo(name)
        elif kind == "remote":
            actions.fetch(self, name)

    def _side_menu(self, kind, name, data, pos):
        menu = actions.sidebar_menu(self, kind, name, data)
        if menu:
            menu.exec(pos)

    # ------------------------------------------------------------------ cleanup
    def close_repo(self):
        self.watcher.stop()
        self.worker.stop()
        self.bg.stop()
        for t in self._tasks:
            t.kill()
