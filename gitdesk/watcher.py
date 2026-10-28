"""Watches a repository for changes made by anyone (terminal, AI agent, IDE...)
and tells the UI what to refresh.

Two mechanisms run together so nothing is missed:
  * QFileSystemWatcher on the .git metadata and the (non-ignored) working tree
    folders, for instant reaction;
  * a light poll of .git metadata fingerprints (and `git status` for very large
    trees that exceed the watch limit), as a safety net.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from .git import Repo

GIT_FILES_REFS = ["HEAD", "packed-refs", "FETCH_HEAD", "ORIG_HEAD", os.path.join("logs", "HEAD"),
                  os.path.join("logs", "refs", "stash"), os.path.join("refs", "stash")]
GIT_FILES_STATE = ["MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "rebase-merge",
                   "rebase-apply", "sequencer", "AUTO_MERGE", "MERGE_MSG"]
MAX_WATCHED_DIRS = 4000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
             ".pytest_cache", ".gradle", ".idea", "target", "dist", "build", ".next", ".cache"}


def _stat(p):
    try:
        s = os.stat(p)
        return (s.st_mtime_ns, s.st_size)
    except OSError:
        return None


class RepoWatcher(QObject):
    changed = Signal(set)   # {"refs", "index", "state", "worktree", "config"}

    def __init__(self, repo: Repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self._pending = set()
        self._paused = 0
        self.fs = QFileSystemWatcher(self)
        self.fs.directoryChanged.connect(self._on_dir)
        self.fs.fileChanged.connect(self._on_file)
        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self._flush)
        self._poll = QTimer(self, interval=1500)
        self._poll.timeout.connect(self._poll_tick)
        self._status_poll_ticks = 0
        self._wt_complete = True
        self._fp = self._fingerprint()
        self._setup_watches()
        self._poll.start()

    # ------------------------------------------------------------------ setup
    def _git_dirs(self):
        return {self.repo.git_dir, self.repo.common_dir}

    def _setup_watches(self):
        if self.fs.directories():
            self.fs.removePaths(self.fs.directories())
        if self.fs.files():
            self.fs.removePaths(self.fs.files())
        paths = []
        for g in self._git_dirs():
            paths.append(g)
            for sub in ("refs", "logs", os.path.join("logs", "refs")):
                for root, dirs, _files in os.walk(os.path.join(g, sub)):
                    paths.append(root)
            idx = os.path.join(g, "index")
            if os.path.exists(idx):
                paths.append(idx)
        # working tree directories (skip ignored / heavy folders)
        ignored = self._ignored_dirs()
        count = 0
        self._wt_complete = True
        for root, dirs, _files in os.walk(self.repo.path):
            rel = os.path.relpath(root, self.repo.path)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and
                       os.path.normpath(os.path.join(rel, d)) not in ignored]
            paths.append(root)
            count += 1
            if count >= MAX_WATCHED_DIRS:
                self._wt_complete = False
                break
        paths = [p for p in dict.fromkeys(paths) if os.path.exists(p)]
        if paths:
            self.fs.addPaths(paths)

    def _ignored_dirs(self):
        try:
            out = self.repo.git("ls-files", "--others", "--ignored", "--exclude-standard",
                                "--directory", "-z", check=False)
            return {os.path.normpath(p.rstrip("/")) for p in out.split("\0") if p.endswith("/")}
        except Exception:
            return set()

    # ------------------------------------------------------------------ fingerprints
    def _fingerprint(self):
        fp = {"refs": [], "index": None, "state": [], "config": None}
        for g in sorted(self._git_dirs()):
            for f in GIT_FILES_REFS:
                fp["refs"].append(_stat(os.path.join(g, f)))
            for f in GIT_FILES_STATE:
                fp["state"].append(_stat(os.path.join(g, f)))
            refs_root = os.path.join(g, "refs")
            for root, _dirs, files in os.walk(refs_root):
                for fn in files:
                    p = os.path.join(root, fn)
                    fp["refs"].append((os.path.relpath(p, refs_root), _stat(p)))
        fp["index"] = _stat(os.path.join(self.repo.git_dir, "index"))
        fp["config"] = _stat(os.path.join(self.repo.common_dir, "config"))
        fp["state"].append(_stat(os.path.join(self.repo.path, ".gitmodules")))
        return fp

    def _compare_fp(self):
        new = self._fingerprint()
        kinds = {k for k in new if new[k] != self._fp.get(k)}
        self._fp = new
        return kinds

    # ------------------------------------------------------------------ events
    def _on_dir(self, path):
        path = os.path.normpath(path)
        in_git = any(path == g or path.startswith(g + os.sep) for g in self._git_dirs())
        if in_git:
            self._pending |= self._compare_fp() or {"refs"}
            # new ref folders (e.g. refs/heads/feature/) need watching
            for root, _d, _f in os.walk(path):
                if root not in self.fs.directories():
                    self.fs.addPath(root)
        else:
            self._pending.add("worktree")
            try:
                for e in os.scandir(path):
                    if e.is_dir() and e.name not in SKIP_DIRS and e.path not in self.fs.directories():
                        self.fs.addPath(e.path)
            except OSError:
                pass
        self._debounce.start()

    def _on_file(self, path):
        # index is rewritten atomically -> re-add it
        if os.path.exists(path) and path not in self.fs.files():
            self.fs.addPath(path)
        self._pending |= self._compare_fp() or {"index"}
        self._debounce.start()

    def _poll_tick(self):
        if self._paused:
            return
        kinds = self._compare_fp()
        self._status_poll_ticks += 1
        if not self._wt_complete and self._status_poll_ticks % 3 == 0:
            kinds.add("worktree")
        # re-arm index watch if it disappeared during atomic replace
        idx = os.path.join(self.repo.git_dir, "index")
        if os.path.exists(idx) and idx not in self.fs.files():
            self.fs.addPath(idx)
        if kinds:
            self._pending |= kinds
            self._debounce.start()

    def _flush(self):
        if self._paused:
            return
        # wait while another git process holds the index lock
        if os.path.exists(os.path.join(self.repo.git_dir, "index.lock")):
            self._debounce.start(400)
            return
        kinds, self._pending = self._pending, set()
        if kinds:
            self.changed.emit(kinds)

    # ------------------------------------------------------------------ control
    def pause(self):
        self._paused += 1

    def resume(self):
        self._paused = max(0, self._paused - 1)
        if not self._paused:
            self._pending |= self._compare_fp()
            self._debounce.start()

    def rescan(self):
        self._setup_watches()

    def stop(self):
        self._poll.stop()
        self._debounce.stop()
        if self.fs.directories():
            self.fs.removePaths(self.fs.directories())
        if self.fs.files():
            self.fs.removePaths(self.fs.files())
