"""Main window: menus, toolbar, repository tabs, console and status bar."""
from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QComboBox, QDockWidget, QLabel, QMainWindow,
                               QMessageBox, QSpinBox, QTabWidget, QToolButton, QWidget, QMenu,
                               QToolBar)

from . import APP_NAME, __version__, actions, icons, theme
from .console import Console
from .forms import Form
from .git import git_executable, run_git
from .i18n import T, current_language, set_language
from .repowidget import RepoWidget
from .startup import CloneDialog, StartupDialog, add_recent, ensure_repo, recent_folders


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1440, 900)
        self._repo_actions = []

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setObjectName("repoTabs")
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        plus = QToolButton()
        plus.setIcon(icons.icon("plus"))
        plus.setToolTip(T("開啟另一個工作資料夾", "Open another working folder"))
        plus.clicked.connect(self.open_folder)
        self.tabs.setCornerWidget(plus, Qt.TopRightCorner)
        self.setCentralWidget(self.tabs)

        self.console = Console(self)
        self.dock = QDockWidget(T("指令記錄與終端機", "Command log / console"), self)
        self.dock.setObjectName("console")
        self.dock.setWidget(self.console)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
        self.resizeDocks([self.dock], [140], Qt.Vertical)

        self._build_toolbar()
        self._build_menus()
        self._build_status()
        st = QSettings().value("ui/geometry")
        if st:
            self.restoreGeometry(st)
        ws = QSettings().value("ui/state")
        if ws:
            self.restoreState(ws)
        QApplication.instance().applicationStateChanged.connect(self._app_state)
        self._update_actions()
        if not ws:
            QTimer.singleShot(0, lambda: self.resizeDocks([self.dock], [140], Qt.Vertical))

    # ------------------------------------------------------------------ build
    def _act(self, text, fn, icon=None, shortcut=None, repo=True, tip=None):
        a = QAction(text, self)
        if icon:
            a.setIcon(icons.icon(icon))
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if tip:
            a.setToolTip(tip)
        a.triggered.connect(lambda *_: self._call(fn, repo))
        if repo:
            self._repo_actions.append(a)
        return a

    def _call(self, fn, repo):
        if repo:
            rw = self.current_repo()
            if rw is None:
                return
            fn(rw)
        else:
            fn()

    def _build_toolbar(self):
        tb = QToolBar(T("工具列", "Toolbar"))
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(tb)
        tb.addAction(self._act(T("開啟", "Open"), self.open_folder, "folder", repo=False,
                               tip=T("開啟工作資料夾（不是儲存庫會自動 git init）", "Open working folder (git init if needed)")))
        tb.addSeparator()
        tb.addAction(self._act(T("提取", "Fetch"), actions.fetch, "fetch", "Ctrl+Shift+F", tip="git fetch --all --prune"))
        pull = self._act(T("拉取", "Pull"), actions.pull_quick, "pull", "Ctrl+Shift+L", tip="git pull")
        push = self._act(T("推送", "Push"), actions.push_quick, "push", "Ctrl+Shift+P", tip="git push")
        self._dropdown(tb, pull, [(T("拉取選項…", "Pull options…"), actions.pull_dialog),
                                  (T("提取選項…", "Fetch options…"), actions.fetch_dialog)])
        self._dropdown(tb, push, [(T("推送選項…", "Push options…"), actions.push_dialog),
                                  (T("推送所有標籤…", "Push all tags…"), actions.push_tag)])
        tb.addSeparator()
        tb.addAction(self._act(T("分支", "Branch"), actions.new_branch, "branch", "Ctrl+B", tip=T("建立分支", "New branch")))
        tb.addAction(self._act(T("合併", "Merge"), actions.merge, "merge", "Ctrl+M"))
        tb.addAction(self._act(T("變基", "Rebase"), actions.rebase, "rebase", "Ctrl+R"))
        tb.addSeparator()
        stash = self._act(T("暫存", "Stash"), actions.stash_save, "stash", "Ctrl+Shift+S", tip="git stash push")
        tb.addAction(stash)
        tb.addAction(self._act(T("取出", "Pop"), lambda rw: actions.stash_apply(rw, "stash@{0}", True), "pop",
                               tip="git stash pop"))
        tb.addAction(self._act(T("復原提交", "Undo"), actions.undo_last_commit, "undo", "Ctrl+Shift+Z",
                               tip=T("復原上次提交（reset --soft HEAD~1）", "Undo last commit (reset --soft HEAD~1)")))
        tb.addSeparator()
        tb.addAction(self._act(T("終端機", "Terminal"), lambda rw: self.console.open_terminal(), "terminal",
                               tip=T("在此資料夾開啟系統終端機", "Open system terminal here")))
        tb.addAction(self._act(T("重新整理", "Refresh"), lambda rw: rw.refresh_all(), "refresh", "F5"))
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(self._act(T("設定", "Settings"), self.settings, "settings", "Ctrl+,", repo=False))

    def _dropdown(self, tb, action, items):
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        m = QMenu(btn)
        for text, fn in items:
            a = self._act(text, fn)
            m.addAction(a)
        btn.setMenu(m)
        tb.addWidget(btn)

    def _build_menus(self):
        mb = self.menuBar()
        A = self._act
        # File
        m = mb.addMenu(T("檔案(&F)", "&File"))
        m.addAction(A(T("開啟工作資料夾…", "Open working folder…"), self.open_folder, "folder", "Ctrl+O", repo=False))
        m.addAction(A(T("複製遠端儲存庫 (clone)…", "Clone repository…"), self.clone, "clone", "Ctrl+Shift+O", repo=False))
        m.addAction(A(T("初始化新儲存庫 (init)…", "Initialize new repository…"), self.init_repo, "folder-plus", repo=False))
        self.recent_menu = m.addMenu(T("最近使用", "Recent"))
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        m.addAction(A(T("在檔案總管中開啟", "Show in file manager"), lambda rw: rw.open_path(rw.repo.path)))
        m.addAction(A(T("關閉儲存庫分頁", "Close repository tab"), lambda rw: self.close_tab(self.tabs.currentIndex()), shortcut="Ctrl+W"))
        m.addSeparator()
        m.addAction(A(T("設定…", "Settings…"), self.settings, "settings", repo=False))
        m.addAction(A(T("結束", "Quit"), self.close, shortcut="Ctrl+Q", repo=False))

        # View
        m = mb.addMenu(T("檢視(&V)", "&View"))
        m.addAction(A(T("工作區變更", "Local changes"), lambda rw: rw.show_view("changes"), "changes", "Ctrl+1"))
        m.addAction(A(T("歷史記錄", "History"), lambda rw: rw.show_view("history"), "history", "Ctrl+2"))
        ta = self.dock.toggleViewAction()
        ta.setText(T("指令記錄與終端機", "Command log / console"))
        ta.setShortcut(QKeySequence("Ctrl+`"))
        m.addAction(ta)
        m.addAction(A(T("重新整理", "Refresh"), lambda rw: rw.refresh_all(), "refresh"))

        # Repository
        m = mb.addMenu(T("儲存庫(&R)", "&Repository"))
        m.addAction(A(T("提取 (fetch)…", "Fetch…"), actions.fetch_dialog, "fetch"))
        m.addAction(A(T("拉取 (pull)…", "Pull…"), actions.pull_dialog, "pull"))
        m.addAction(A(T("推送 (push)…", "Push…"), actions.push_dialog, "push"))
        m.addSeparator()
        sub = m.addMenu(icons.icon("globe"), T("遠端", "Remotes"))
        sub.addAction(A(T("管理遠端…", "Manage remotes…"), lambda rw: self._tools().RemotesDialog(rw).exec()))
        sub.addAction(A(T("新增遠端…", "Add remote…"), actions.add_remote))
        sub = m.addMenu(icons.icon("box"), T("子模組", "Submodules"))
        sub.addAction(A(T("新增子模組…", "Add submodule…"), actions.add_submodule))
        sub.addAction(A(T("更新子模組…", "Update submodules…"), actions.update_submodules))
        sub.addAction(A("submodule sync --recursive", lambda rw: rw.run(["submodule", "sync", "--recursive"], "submodule sync")))
        sub.addAction(A("submodule foreach…", actions._submodule_foreach))
        sub = m.addMenu(icons.icon("tree"), T("工作樹", "Worktrees"))
        sub.addAction(A(T("新增工作樹…", "Add worktree…"), actions.add_worktree))
        sub.addAction(A("worktree prune", lambda rw: rw.run(["worktree", "prune", "-v"], "worktree prune", show_output=True)))
        m.addSeparator()
        m.addAction(A(T("清理未追蹤檔案 (clean)…", "Clean untracked files…"), lambda rw: self._tools().CleanDialog(rw).exec(), "trash"))
        m.addAction(A(T("稀疏簽出 (sparse-checkout)…", "Sparse checkout…"), actions.sparse_checkout))
        m.addAction(A("Git LFS…", lambda rw: self._tools().LfsDialog(rw).exec(), "box"))
        m.addAction(A(T("編輯 .gitignore…", "Edit .gitignore…"), actions.edit_gitignore))
        m.addAction(A(T("編輯 .gitattributes…", "Edit .gitattributes…"), actions.edit_gitattributes))
        m.addAction(A(T("Hooks 管理…", "Hooks…"), lambda rw: self._tools().HooksDialog(rw).exec(), "hook"))
        m.addAction(A(T("儲存庫設定 (config)…", "Repository config…"), lambda rw: self._tools().ConfigDialog(rw, "local").exec(), "settings"))
        m.addAction(A(T("維護 (gc / fsck / repack)…", "Maintenance (gc / fsck / repack)…"), lambda rw: self._tools().MaintenanceDialog(rw).exec(), "wrench"))
        m.addSeparator()
        m.addAction(A(T("匯出封存檔 (archive)…", "Export archive…"), lambda rw: actions.archive(rw)))
        m.addAction(A("git bundle…", actions.bundle))

        # Branch
        m = mb.addMenu(T("分支(&B)", "&Branch"))
        m.addAction(A(T("建立分支…", "New branch…"), actions.new_branch, "branch"))
        m.addAction(A(T("簽出分支…", "Checkout branch…"), self._checkout_pick))
        m.addAction(A(T("重新命名目前分支…", "Rename current branch…"), lambda rw: actions.rename_branch(rw, rw.repo.current_branch())))
        m.addAction(A(T("設定上游…", "Set upstream…"), lambda rw: actions.set_upstream(rw, rw.repo.current_branch())))
        m.addSeparator()
        m.addAction(A(T("合併 (merge)…", "Merge…"), actions.merge, "merge"))
        m.addAction(A(T("變基 (rebase)…", "Rebase…"), actions.rebase, "rebase"))
        m.addAction(A(T("互動式變基…", "Interactive rebase…"), self._irebase_pick))
        m.addAction(A(T("比較分支…", "Compare branches…"), lambda rw: actions.compare_branches(rw)))
        m.addSeparator()
        m.addAction(A(T("建立標籤…", "New tag…"), actions.new_tag, "tag"))
        m.addAction(A(T("推送所有標籤…", "Push all tags…"), actions.push_tag))

        # Commit
        m = mb.addMenu(T("提交(&C)", "&Commit"))
        m.addAction(A(T("全部暫存", "Stage all"), lambda rw: rw.changes.stage_all(), "plus", "Ctrl+Shift+A"))
        m.addAction(A(T("全部取消暫存", "Unstage all"), lambda rw: rw.changes.unstage_all(), "minus", "Ctrl+Shift+U"))
        m.addAction(A(T("捨棄所有變更…", "Discard all changes…"), lambda rw: rw.changes.discard_all(), "trash"))
        m.addSeparator()
        m.addAction(A(T("提交", "Commit"), lambda rw: (rw.show_view("changes"), rw.changes.summary.setFocus()), "commit", "Ctrl+Shift+C"))
        m.addAction(A(T("修訂上次提交…", "Amend last commit…"), lambda rw: (rw.show_view("changes"), rw.changes.chk_amend.setChecked(True))))
        m.addAction(A(T("復原上次提交", "Undo last commit"), actions.undo_last_commit, "undo"))
        m.addAction(A(T("重設 (reset)…", "Reset…"), lambda rw: actions.reset(rw, "HEAD")))
        m.addAction(A(T("揀選 (cherry-pick)…", "Cherry-pick…"), self._cherry_pick))
        m.addAction(A(T("還原 (revert)…", "Revert…"), self._revert))
        m.addSeparator()
        m.addAction(A(T("套用修補檔 (am / apply)…", "Apply patch (am / apply)…"), actions.apply_patch_file))
        m.addAction(A(T("由變更產生修補檔…", "Create patch from changes…"), actions.create_patch_from_changes))

        # Stash
        m = mb.addMenu(T("Stash(&S)", "&Stash"))
        m.addAction(A(T("暫存變更…", "Stash changes…"), actions.stash_save, "stash"))
        m.addAction(A(T("取出最新 (pop)", "Pop latest"), lambda rw: actions.stash_apply(rw, "stash@{0}", True), "pop"))
        m.addAction(A(T("套用最新 (apply)", "Apply latest"), lambda rw: actions.stash_apply(rw, "stash@{0}", False)))
        m.addAction(A(T("清除全部…", "Clear all…"), actions.stash_clear, "trash"))

        # Tools
        m = mb.addMenu(T("工具(&T)", "&Tools"))
        m.addAction(A(T("參照記錄 (reflog)…", "Reflog…"), lambda rw: self._tools().ReflogWindow(rw).show(), "history"))
        m.addAction(A(T("在檔案中搜尋 (grep)…", "Search in files (grep)…"), lambda rw: self._tools().GrepWindow(rw).show(), "search", "Ctrl+Shift+G"))
        m.addAction(A(T("檔案歷史…", "File history…"), self._file_history_pick))
        m.addAction(A(T("逐行追溯 (blame)…", "Blame…"), self._blame_pick))
        sub = m.addMenu(icons.icon("bug"), T("二分搜尋 (bisect)", "Bisect"))
        sub.addAction(A(T("開始（目前為壞）", "Start (current is bad)"), lambda rw: actions.bisect(rw, "bad")))
        sub.addAction(A(T("標記目前為好", "Mark current good"), lambda rw: actions.bisect(rw, "good")))
        sub.addAction(A(T("標記目前為壞", "Mark current bad"), lambda rw: actions.bisect(rw, "bad")))
        sub.addAction(A(T("略過目前", "Skip current"), lambda rw: actions.bisect(rw, "skip")))
        sub.addAction(A(T("自動執行測試 (bisect run)…", "Run test script (bisect run)…"), actions.bisect_run))
        sub.addAction(A(T("檢視記錄", "Show log"), lambda rw: rw.run(["bisect", "log"], "bisect log", show_output=True, refresh=False)))
        sub.addAction(A(T("結束 (reset)", "End (reset)"), lambda rw: rw.run(["bisect", "reset"], "bisect reset")))
        m.addSeparator()
        m.addAction(A(T("貢獻者統計 (shortlog)", "Contributors (shortlog)"), actions.shortlog))
        m.addAction(A(T("描述目前版本 (describe)", "Describe (describe)"), actions.describe))
        m.addAction(A(T("物件統計 (count-objects)", "Object stats"), actions.count_objects))
        m.addSeparator()
        m.addAction(A(T("全域 Git 設定…", "Global git config…"), lambda: self._tools().ConfigDialog(None, "global").exec(), "settings", repo=False))
        m.addAction(A(T("開啟系統終端機", "Open system terminal"), lambda rw: self.console.open_terminal(), "terminal"))

        # Help
        m = mb.addMenu(T("說明(&H)", "&Help"))
        m.addAction(A(T("關於", "About"), self.about, "info", repo=False))

    def _build_status(self):
        sb = self.statusBar()
        self.lbl_branch = QLabel()
        self.lbl_sync = QLabel()
        self.lbl_busy = QLabel()
        self.lbl_watch = QLabel("● " + T("自動同步中", "Live sync"))
        self.lbl_watch.setToolTip(T("偵測到其他程式（終端機、AI 代理、IDE）對儲存庫的變更時會自動更新畫面",
                                    "The UI updates automatically when other tools (terminal, AI agents, IDEs) change the repository"))
        self.lbl_watch.setStyleSheet(f"color:{theme.C['ok']}")
        sb.addWidget(self.lbl_branch)
        sb.addWidget(self.lbl_sync)
        sb.addWidget(self.lbl_busy, 1)
        sb.addPermanentWidget(self.lbl_watch)

    def _tools(self):
        from . import tools
        return tools

    # ------------------------------------------------------------------ repos
    def current_repo(self) -> RepoWidget:
        w = self.tabs.currentWidget()
        return w if isinstance(w, RepoWidget) else None

    def open_repo(self, path):
        path = os.path.normpath(path)
        top = ensure_repo(self, path)
        if not top:
            return
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, RepoWidget) and os.path.normcase(w.repo.path) == os.path.normcase(top):
                self.tabs.setCurrentIndex(i)
                return w
        try:
            rw = RepoWidget(top, main=self)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e))
            return
        add_recent(top)
        rw.titleChanged.connect(lambda rw=rw: self._update_tab(rw))
        rw.busyChanged.connect(self._busy)
        i = self.tabs.addTab(rw, icons.icon("repo"), rw.title())
        self.tabs.setTabToolTip(i, top)
        from PySide6.QtWidgets import QTabBar
        close = QToolButton()
        close.setObjectName("tabClose")
        close.setIcon(icons.icon("x", theme.C["muted"]))
        close.setIconSize(QSize(12, 12))
        close.setAutoRaise(True)
        close.setToolTip(T("關閉", "Close"))
        close.clicked.connect(lambda _=False, rw=rw: self.close_tab(self.tabs.indexOf(rw)))
        self.tabs.tabBar().setTabButton(i, QTabBar.RightSide, close)
        self.tabs.setCurrentIndex(i)
        self._update_tab(rw)
        self._update_actions()
        return rw

    def _update_tab(self, rw):
        i = self.tabs.indexOf(rw)
        if i >= 0:
            b = rw.repo.current_branch() or T("分離", "detached")
            self.tabs.setTabText(i, f"{rw.title()}  ·  {b}")
        if rw is self.current_repo():
            self.update_status_bar(rw)
            self.setWindowTitle(f"{rw.repo.path} — {APP_NAME}")

    def close_tab(self, i):
        w = self.tabs.widget(i)
        if isinstance(w, RepoWidget):
            w.close_repo()
        self.tabs.removeTab(i)
        if w:
            w.deleteLater()
        self._update_actions()
        if self.tabs.count() == 0:
            # always keep a working folder: ask again
            QTimer.singleShot(0, self._ask_folder_again)

    def _ask_folder_again(self):
        d = StartupDialog(self, first_run=False)
        if d.exec() and d.path:
            self.open_repo(d.path)
        elif self.tabs.count() == 0:
            self.close()

    def _tab_changed(self, i):
        rw = self.current_repo()
        if rw:
            rw.refresh()
            self._update_tab(rw)
        self._update_actions()

    def _update_actions(self):
        has = self.current_repo() is not None
        for a in self._repo_actions:
            a.setEnabled(has)

    def update_status_bar(self, rw):
        if rw is not self.current_repo():
            return
        st = rw.changes.status
        if not st:
            return
        head = st.head if st.head != "(detached)" else T("分離 HEAD", "detached HEAD") + f" {st.oid[:8]}"
        self.lbl_branch.setText("  ⎇ " + head)
        if st.upstream:
            self.lbl_sync.setText(f"   ↑{st.ahead} ↓{st.behind}  {st.upstream}")
        else:
            self.lbl_sync.setText("   " + T("（無上游）", "(no upstream)"))

    def _busy(self, busy, title):
        self.lbl_busy.setText(("   ⏳ " + title) if busy else "")

    # ------------------------------------------------------------------ commands
    def open_folder(self):
        from PySide6.QtWidgets import QFileDialog
        start = recent_folders()[0] if recent_folders() else os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, T("選擇工作資料夾", "Choose working folder"), os.path.dirname(start))
        if d:
            self.open_repo(d)

    def clone(self):
        d = CloneDialog(self)
        if d.exec() and d.result_path:
            self.open_repo(d.result_path)

    def init_repo(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, T("選擇要初始化的資料夾", "Folder to initialize"))
        if not d:
            return
        from .git import Repo
        if Repo.is_repo(d):
            QMessageBox.information(self, "git init", T("此資料夾已在 Git 儲存庫中，將直接開啟。", "This folder is already in a repository; opening it."))
        self.open_repo(d)

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        for p in recent_folders():
            self.recent_menu.addAction(p, lambda p=p: self.open_repo(p))

    def _pick_ref(self, rw, title, refs, current=""):
        f = Form(self, title)
        f.combo("ref", "", refs, current=current, editable=True)
        v = f.ask()
        return v["ref"] if v else None

    def _checkout_pick(self, rw):
        refs = [b.name for b in rw.repo.branches()] + [b.name for b in rw.repo.remote_branches()]
        r = self._pick_ref(rw, T("簽出分支", "Checkout branch"), refs)
        if r:
            if r in [b.name for b in rw.repo.branches()]:
                actions.checkout(rw, r)
            else:
                actions.checkout_remote(rw, r)

    def _irebase_pick(self, rw):
        r = self._pick_ref(rw, T("互動式變基：選擇基底（不含）", "Interactive rebase: choose base (exclusive)"),
                           ["HEAD~5", "HEAD~10"] + rw.repo.all_refs_for_completion(), "HEAD~5")
        if r:
            actions.interactive_rebase(rw, r)

    def _cherry_pick(self, rw):
        sel = rw.history.selected_commits() if rw.stack.currentWidget() is rw.history else []
        if sel:
            actions.cherry_pick(rw, [c.sha for c in reversed(sel)])
            return
        r = self._pick_ref(rw, T("揀選提交（SHA 或 ref）", "Cherry-pick commit (SHA or ref)"), rw.repo.all_refs_for_completion())
        if r:
            actions.cherry_pick(rw, [r])

    def _revert(self, rw):
        sel = rw.history.selected_commits() if rw.stack.currentWidget() is rw.history else []
        if sel:
            actions.revert(rw, [c.sha for c in sel])
            return
        r = self._pick_ref(rw, T("還原提交（SHA 或 ref）", "Revert commit (SHA or ref)"), ["HEAD"])
        if r:
            actions.revert(rw, [r])

    def _tracked_file(self, rw, title):
        files = rw.repo.git("ls-files", check=False).splitlines()
        return self._pick_ref(rw, title, files)

    def _file_history_pick(self, rw):
        p = self._tracked_file(rw, T("檔案歷史：選擇檔案", "File history: choose file"))
        if p:
            rw.open_file_history(p)

    def _blame_pick(self, rw):
        p = self._tracked_file(rw, T("Blame：選擇檔案", "Blame: choose file"))
        if p:
            rw.open_blame(p)

    # ------------------------------------------------------------------ settings / about
    def settings(self):
        s = QSettings()
        f = Form(self, T("設定", "Settings"))
        f.combo("lang", T("語言 Language", "Language 語言"), [("zh_TW", "繁體中文"), ("en", "English")], current=current_language())
        f.combo("theme", T("主題", "Theme"), [("system", T("跟隨系統", "Follow system")), ("light", T("淺色", "Light")),
                                              ("dark", T("深色", "Dark"))], current=s.value("ui/theme", "system"))
        f.spin("font", T("差異字型大小", "Diff font size"), int(s.value("ui/diff_font_size", 10)), 7, 24)
        f.path("git", T("git 執行檔", "git executable"), s.value("git/path", "") or git_executable(), directory=False)
        f.combo("pull", T("預設拉取方式", "Default pull mode"), [("merge", "merge"), ("rebase", "rebase"), ("ff-only", "ff-only")],
                current=s.value("git/pull_mode", "merge"))
        f.text("branch", T("git init 預設分支", "Default branch for git init"), s.value("git/default_branch", "main"))
        name = run_git(["config", "--global", "--get", "user.name"], check=False).strip()
        email = run_git(["config", "--global", "--get", "user.email"], check=False).strip()
        f.text("name", T("全域 user.name", "Global user.name"), name)
        f.text("email", T("全域 user.email", "Global user.email"), email)
        try:
            ver = run_git(["--version"], check=False).strip()
        except Exception:
            ver = "?"
        f.label(ver)
        v = f.ask()
        if not v:
            return
        restart = v["lang"] != current_language() or v["theme"] != s.value("ui/theme", "system") or \
            v["font"] != int(s.value("ui/diff_font_size", 10))
        set_language(v["lang"])
        s.setValue("ui/theme", v["theme"])
        s.setValue("ui/diff_font_size", v["font"])
        s.setValue("git/path", v["git"] if v["git"] and v["git"] != "git" else "")
        s.setValue("git/pull_mode", v["pull"])
        s.setValue("git/default_branch", v["branch"] or "main")
        try:
            if v["name"] and v["name"] != name:
                run_git(["config", "--global", "user.name", v["name"]], log=True)
            if v["email"] and v["email"] != email:
                run_git(["config", "--global", "user.email", v["email"]], log=True)
        except Exception as e:
            QMessageBox.warning(self, "config", str(e))
        if restart:
            QMessageBox.information(self, APP_NAME, T("部分設定（語言、主題、字型）將在重新啟動後套用。",
                                                      "Some settings (language, theme, font) apply after restart."))

    def about(self):
        try:
            ver = run_git(["--version"], check=False).strip()
        except Exception:
            ver = "git ?"
        QMessageBox.about(self, APP_NAME, f"<h3>{APP_NAME} {__version__}</h3>"
                          + T("<p>跨平台（Windows / Linux）圖形化 Git 用戶端。</p>",
                              "<p>Cross-platform (Windows / Linux) graphical Git client.</p>")
                          + f"<p>{ver}</p>")

    # ------------------------------------------------------------------ events
    def _app_state(self, state):
        if state == Qt.ApplicationActive:
            rw = self.current_repo()
            if rw:
                QTimer.singleShot(50, lambda: rw.refresh({"refs", "index", "state", "worktree"}))

    def closeEvent(self, e):
        s = QSettings()
        s.setValue("ui/geometry", self.saveGeometry())
        s.setValue("ui/state", self.saveState())
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, RepoWidget):
                w.close_repo()
        super().closeEvent(e)
