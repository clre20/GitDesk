"""Startup: choose the working folder for this session (git init if needed), clone."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget, QDialogButtonBox)

from . import APP_NAME, __version__, icons, theme
from .forms import Form
from .git import GitTask, Repo, git_available, run_git
from .i18n import T, current_language, set_language

MAX_RECENT = 15


def recent_folders():
    v = QSettings().value("recent/folders", [])
    if isinstance(v, str):
        v = [v]
    return [p for p in (v or []) if p]


def add_recent(path):
    path = os.path.normpath(path)
    lst = [p for p in recent_folders() if os.path.normcase(p) != os.path.normcase(path)]
    lst.insert(0, path)
    QSettings().setValue("recent/folders", lst[:MAX_RECENT])


def remove_recent(path):
    QSettings().setValue("recent/folders", [p for p in recent_folders() if p != path])


GITIGNORE_DEFAULT = """# OS
.DS_Store
Thumbs.db
desktop.ini

# Editors
.vscode/
.idea/
*.swp

# Build / dependencies
node_modules/
__pycache__/
*.pyc
dist/
build/
.venv/
"""


def ensure_repo(parent, path, ask=True):
    """Return the repository top-level for `path`, running `git init` if needed."""
    if not os.path.isdir(path):
        QMessageBox.warning(parent, APP_NAME, T("資料夾不存在：", "Folder does not exist: ") + path)
        return None
    if Repo.is_repo(path):
        return Repo(path).path
    s = QSettings()
    branch = s.value("git/default_branch", "main")
    make_ignore = s.value("git/init_gitignore", "false") == "true"
    if ask:
        f = Form(parent, T("建立 Git 儲存庫", "Create Git repository"),
                 T(f"「{path}」還不是 Git 儲存庫，將在此執行 git init。",
                   f"'{path}' is not a Git repository yet. git init will be run here."),
                 ok_text=T("建立並開始", "Create && start"))
        f.text("branch", T("初始分支", "Initial branch"), branch)
        f.check("ignore", T("建立預設 .gitignore", "Create a default .gitignore"), make_ignore)
        f.check("commit", T("建立初始提交", "Make an initial commit"), False)
        v = f.ask()
        if not v:
            return None
        branch, make_ignore = v["branch"] or "main", v["ignore"]
        s.setValue("git/default_branch", branch)
        s.setValue("git/init_gitignore", "true" if make_ignore else "false")
        initial_commit = v["commit"]
    else:
        initial_commit = False
    try:
        Repo.init(path, branch)
        if make_ignore and not os.path.exists(os.path.join(path, ".gitignore")):
            with open(os.path.join(path, ".gitignore"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(GITIGNORE_DEFAULT)
        if initial_commit:
            run_git(["add", "-A"], cwd=path, log=True)
            run_git(["commit", "--allow-empty", "-m", "Initial commit"], cwd=path, log=True)
    except Exception as e:
        from .errors import show_git_error
        show_git_error(parent, "git init", str(e))
        return None
    return Repo(path).path


class CloneDialog(QDialog):
    """Clone with live progress; returns the cloned path in self.result_path."""

    def __init__(self, parent=None, url=""):
        super().__init__(parent)
        self.setWindowTitle(T("複製遠端儲存庫 (clone)", "Clone repository"))
        self.setMinimumWidth(640)
        self.result_path = None
        self.task = None
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        h = QLabel(T("複製遠端儲存庫", "Clone repository"))
        h.setProperty("h2", True)
        v.addWidget(h)
        from PySide6.QtWidgets import QFormLayout
        fl = QFormLayout()
        fl.setLabelAlignment(Qt.AlignRight)
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("https://github.com/user/repo.git   /   git@github.com:user/repo.git")
        self.parent_dir = QLineEdit(QSettings().value("clone/parent", os.path.expanduser("~")))
        pick = QPushButton(T("瀏覽…", "Browse…"))
        pick.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self.parent_dir, 1)
        row.addWidget(pick)
        roww = QWidget()
        roww.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit()
        self.url.textChanged.connect(self._auto_name)
        self.branch = QLineEdit()
        self.branch.setPlaceholderText(T("（預設分支）", "(default branch)"))
        self.depth = QLineEdit()
        self.depth.setPlaceholderText(T("（完整歷史）", "(full history)"))
        self.recurse = QCheckBox(T("包含子模組 (--recurse-submodules)", "Recurse submodules"))
        self.recurse.setChecked(True)
        self.single = QCheckBox(T("只複製單一分支 (--single-branch)", "Single branch"))
        self.partial = QCheckBox(T("部分複製，延遲下載檔案 (--filter=blob:none)", "Partial clone (--filter=blob:none)"))
        self.sparse = QCheckBox(T("稀疏簽出 (--sparse)", "Sparse checkout (--sparse)"))
        self.nocheckout = QCheckBox(T("不簽出檔案 (--no-checkout)", "No checkout"))
        fl.addRow("URL", self.url)
        fl.addRow(T("存放位置", "Parent folder"), roww)
        fl.addRow(T("資料夾名稱", "Folder name"), self.name)
        fl.addRow(T("分支", "Branch"), self.branch)
        fl.addRow(T("深度", "Depth"), self.depth)
        for c in (self.recurse, self.single, self.partial, self.sparse, self.nocheckout):
            fl.addRow("", c)
        v.addLayout(fl)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(theme.mono_font(9))
        self.log.setFixedHeight(130)
        self.log.hide()
        v.addWidget(self.log)
        bb = QDialogButtonBox()
        self.ok = bb.addButton(T("複製", "Clone"), QDialogButtonBox.AcceptRole)
        self.ok.setProperty("accent", True)
        self.cancel = bb.addButton(T("取消", "Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._start)
        bb.rejected.connect(self._cancel)
        v.addWidget(bb)

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, T("存放位置", "Parent folder"), self.parent_dir.text())
        if d:
            self.parent_dir.setText(os.path.normpath(d))

    def _auto_name(self, u):
        m = re.search(r"([^/\\:]+?)(\.git)?/?$", u.strip())
        if m:
            self.name.setText(m.group(1))

    def _start(self):
        url = self.url.text().strip()
        parent = self.parent_dir.text().strip()
        name = self.name.text().strip()
        if not url or not parent or not name:
            QMessageBox.warning(self, "clone", T("請填寫 URL、位置與資料夾名稱", "URL, location and folder name are required"))
            return
        dest = os.path.join(parent, name)
        if os.path.exists(dest) and os.listdir(dest):
            QMessageBox.warning(self, "clone", T("目標資料夾已存在且不是空的：", "Destination exists and is not empty: ") + dest)
            return
        QSettings().setValue("clone/parent", parent)
        args = ["clone", "--progress"]
        if self.branch.text().strip():
            args += ["-b", self.branch.text().strip()]
        if self.depth.text().strip().isdigit():
            args += ["--depth", self.depth.text().strip()]
        if self.recurse.isChecked(): args.append("--recurse-submodules")
        if self.single.isChecked(): args.append("--single-branch")
        if self.partial.isChecked(): args.append("--filter=blob:none")
        if self.sparse.isChecked(): args.append("--sparse")
        if self.nocheckout.isChecked(): args.append("--no-checkout")
        args += [url, dest]
        self.log.show()
        self.log.clear()
        self.ok.setEnabled(False)
        self.task = GitTask(args, parent, parent=self)
        self.task.output.connect(self._out)
        self.task.done.connect(lambda code, o, e: self._done(code, dest, e))
        self.task.start()

    def _out(self, t):
        # git progress uses \r; show the latest line
        for part in re.split(r"[\r\n]+", t):
            if part.strip():
                self.log.appendPlainText(part.strip())

    def _done(self, code, dest, err):
        self.task = None
        if code == 0:
            self.result_path = dest
            self.accept()
        else:
            self.ok.setEnabled(True)
            from .errors import show_git_error
            show_git_error(self, T("複製失敗", "Clone failed"), err.strip()[-3000:])

    def _cancel(self):
        if self.task:
            self.task.kill()
        self.reject()


class LanguageDialog(QDialog):
    """First launch only: pick the interface language before anything else."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(420)
        self.lang = None
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(56, 56))
        logo.setAlignment(Qt.AlignCenter)
        v.addWidget(logo)
        h = QLabel("請選擇介面語言\nChoose your language")
        h.setAlignment(Qt.AlignCenter)
        h.setProperty("h2", True)
        v.addWidget(h)
        for code, text in (("zh_TW", "繁體中文"), ("en", "English")):
            b = QPushButton(text)
            b.setMinimumHeight(44)
            b.clicked.connect(lambda _=False, c=code: self._pick(c))
            v.addWidget(b)
        note = QLabel("之後可在「設定」中更改 · You can change this later in Settings")
        note.setProperty("muted", True)
        note.setAlignment(Qt.AlignCenter)
        note.setWordWrap(True)
        v.addWidget(note)

    def _pick(self, code):
        from . import i18n
        set_language(code)
        i18n._lang = code
        self.lang = code
        self.accept()


class StartupDialog(QDialog):
    """Shown at launch: the user must pick the working folder for this session."""
    _warned = False

    def __init__(self, parent=None, first_run=True):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(720, 560)
        self.path = None
        self.first_run = first_run
        self.relaunch = False
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 20)
        v.setSpacing(14)

        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(56, 56))
        top.addWidget(logo)
        tv = QVBoxLayout()
        h = QLabel(T("選擇這次的工作資料夾", "Choose your working folder"))
        h.setProperty("h1", True)
        sub = QLabel(T("已是 Git 儲存庫就直接繼續；不是的話會自動建立（git init）。",
                       "If it's already a Git repository you continue right away; otherwise one is created (git init)."))
        sub.setProperty("muted", True)
        sub.setWordWrap(True)
        tv.addWidget(h)
        tv.addWidget(sub)
        top.addLayout(tv, 1)
        lang = QComboBox()
        lang.addItem("繁體中文", "zh_TW")
        lang.addItem("English", "en")
        lang.setCurrentIndex(0 if current_language() == "zh_TW" else 1)
        lang.currentIndexChanged.connect(lambda: self._lang(lang.currentData()))
        top.addWidget(lang, 0, Qt.AlignTop)
        v.addLayout(top)

        btns = QHBoxLayout()
        self.btn_open = QPushButton(icons.icon("folder", "#ffffff"), T("  選擇資料夾…", "  Choose folder…"))
        self.btn_open.setProperty("accent", True)
        self.btn_open.setMinimumHeight(40)
        self.btn_open.clicked.connect(self._browse)
        self.btn_clone = QPushButton(icons.icon("clone"), T("  從網址複製 (clone)…", "  Clone from URL…"))
        self.btn_clone.setMinimumHeight(40)
        self.btn_clone.clicked.connect(self._clone)
        btns.addWidget(self.btn_open, 1)
        btns.addWidget(self.btn_clone, 1)
        v.addLayout(btns)

        rl = QLabel(T("最近使用", "Recent"))
        rl.setProperty("h2", True)
        v.addWidget(rl)
        self.recent = QListWidget()
        self.recent.itemActivated.connect(lambda it: self._choose(it.data(Qt.UserRole)))
        self.recent.itemDoubleClicked.connect(lambda it: self._choose(it.data(Qt.UserRole)))
        self.recent.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recent.customContextMenuRequested.connect(self._recent_menu)
        v.addWidget(self.recent, 1)
        self._fill_recent()

        bottom = QHBoxLayout()
        ver = QLabel(f"{APP_NAME} {__version__}")
        ver.setProperty("muted", True)
        bottom.addWidget(ver)
        bottom.addStretch(1)
        self.btn_go = QPushButton(T("開啟所選", "Open selected"))
        self.btn_go.clicked.connect(lambda: self.recent.currentItem() and self._choose(self.recent.currentItem().data(Qt.UserRole)))
        quit_btn = QPushButton(T("結束", "Quit") if first_run else T("取消", "Cancel"))
        quit_btn.clicked.connect(self.reject)
        bottom.addWidget(self.btn_go)
        bottom.addWidget(quit_btn)
        v.addLayout(bottom)

        if not git_available() and not StartupDialog._warned:
            StartupDialog._warned = True
            QMessageBox.critical(self, APP_NAME, T(
                "找不到 git。\n\nWindows：請安裝 Git for Windows（https://git-scm.com/download/win）。\n"
                "Linux：請用套件管理員安裝，例如 sudo apt install git。\n\n安裝後也可以在「設定」中指定 git 路徑。",
                "git was not found.\n\nWindows: install Git for Windows (https://git-scm.com/download/win).\n"
                "Linux: install it with your package manager, e.g. sudo apt install git.\n\n"
                "You can also set the git path in Settings."))

    def _lang(self, lang):
        set_language(lang)
        if self.first_run:
            # nothing else is on screen yet: switch immediately by rebuilding this dialog
            from . import i18n
            i18n._lang = lang
            self.relaunch = True
            self.done(2)
        else:
            QMessageBox.information(self, APP_NAME, "語言將在重新啟動後套用。\nLanguage will apply after restart.")

    def _fill_recent(self):
        self.recent.clear()
        for p in recent_folders():
            exists = os.path.isdir(p)
            is_git = exists and os.path.exists(os.path.join(p, ".git"))
            tag = "Git" if is_git else (T("資料夾", "Folder") if exists else T("不存在", "missing"))
            it = QListWidgetItem(icons.icon("repo" if is_git else "folder",
                                            theme.C["accent"] if is_git else theme.C["muted"]),
                                 f"{os.path.basename(p) or p}    —    {p}    [{tag}]")
            it.setData(Qt.UserRole, p)
            if not exists:
                it.setForeground(Qt.gray)
            self.recent.addItem(it)
        if self.recent.count():
            self.recent.setCurrentRow(0)
        else:
            it = QListWidgetItem(T("（尚無記錄）", "(nothing yet)"))
            it.setFlags(Qt.NoItemFlags)
            self.recent.addItem(it)

    def _recent_menu(self, pos):
        it = self.recent.itemAt(pos)
        if not it or not it.data(Qt.UserRole):
            return
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction(T("從清單移除", "Remove from list"), lambda: (remove_recent(it.data(Qt.UserRole)), self._fill_recent()))
        m.exec(self.recent.viewport().mapToGlobal(pos))

    def _browse(self):
        start = recent_folders()[0] if recent_folders() else os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, T("選擇工作資料夾", "Choose working folder"), os.path.dirname(start))
        if d:
            self._choose(os.path.normpath(d))

    def _clone(self):
        d = CloneDialog(self)
        if d.exec() and d.result_path:
            self._choose(d.result_path)

    def _choose(self, path):
        if not path:
            return
        top = ensure_repo(self, path)
        if top:
            add_recent(top)
            self.path = top
            self.accept()
