"""Command log + built-in git command line (for anything not in the UI)."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme
from .git import IS_WIN, LOG
from .i18n import T


class HistoryLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hist = []
        self.pos = 0

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up and self.hist:
            self.pos = max(0, self.pos - 1)
            self.setText(self.hist[self.pos])
            return
        if e.key() == Qt.Key_Down and self.hist:
            self.pos = min(len(self.hist), self.pos + 1)
            self.setText(self.hist[self.pos] if self.pos < len(self.hist) else "")
            return
        super().keyPressEvent(e)

    def push(self, t):
        if t and (not self.hist or self.hist[-1] != t):
            self.hist.append(t)
        self.pos = len(self.hist)


class Console(QWidget):
    def __init__(self, main, parent=None):
        super().__init__(parent)
        self.main = main
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 0, 6, 6)
        v.setSpacing(4)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(theme.mono_font(9))
        self.log.setMaximumBlockCount(5000)
        v.addWidget(self.log, 1)
        row = QHBoxLayout()
        prompt = QLabel("git ›")
        prompt.setFont(theme.mono_font(10))
        self.cmd = HistoryLineEdit()
        self.cmd.setFont(theme.mono_font(10))
        self.cmd.setPlaceholderText(T("輸入任何 git 指令並按 Enter，例如：log --oneline -5、worktree list、rerere status",
                                      "Type any git command and press Enter, e.g. log --oneline -5, worktree list, rerere status"))
        self.cmd.returnPressed.connect(self._run)
        clear = QPushButton(T("清除", "Clear"))
        clear.setProperty("flat", True)
        clear.clicked.connect(self.log.clear)
        term = QPushButton(T("開啟系統終端機", "Open system terminal"))
        term.setProperty("flat", True)
        term.clicked.connect(self.open_terminal)
        row.addWidget(prompt)
        row.addWidget(self.cmd, 1)
        row.addWidget(clear)
        row.addWidget(term)
        v.addLayout(row)
        LOG.entry.connect(self.append)

    def append(self, kind, text):
        color = {"cmd": theme.C["accent"], "err": theme.C["del_fg"], "info": theme.C["muted"]}.get(kind, theme.C["text"])
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        c = self.log.textCursor()
        c.movePosition(QTextCursor.End)
        if kind == "cmd":
            c.insertText(time.strftime("%H:%M:%S ") + "$ " + text + "\n", fmt)
        else:
            c.insertText(text + "\n", fmt)
        self.log.setTextCursor(c)
        self.log.ensureCursorVisible()

    def _run(self):
        t = self.cmd.text().strip()
        if not t:
            return
        self.cmd.push(t)
        self.cmd.clear()
        if t.startswith("git "):
            t = t[4:]
        try:
            args = shlex.split(t, posix=not IS_WIN) if not IS_WIN else _win_split(t)
        except ValueError as e:
            self.append("err", str(e))
            return
        rw = self.main.current_repo()
        if rw is None:
            self.append("err", T("請先開啟儲存庫", "Open a repository first"))
            return
        if args and args[0] in ("commit", "merge", "rebase", "tag") and not any(
                a in args for a in ("-m", "-F", "--message", "--file", "--no-edit", "--continue", "--abort", "--skip",
                                   "-d", "-l", "--list", "--quit")):
            if args[0] in ("commit",) and "--amend" not in args:
                self.append("info", T("提示：請使用 -m 提供訊息（內建終端機不會開啟編輯器）",
                                      "Hint: pass -m (the built-in console does not open an editor)"))
        rw.run(args, "git " + t, quiet=True)

    def open_terminal(self):
        rw = self.main.current_repo()
        cwd = rw.repo.path if rw else os.path.expanduser("~")
        try:
            if IS_WIN:
                if shutil.which("wt"):
                    subprocess.Popen(["wt", "-d", cwd])
                else:
                    git_bash = None
                    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),):
                        c = os.path.join(base, "Git", "git-bash.exe")
                        if os.path.exists(c):
                            git_bash = c
                    if git_bash:
                        subprocess.Popen([git_bash, f"--cd={cwd}"])
                    else:
                        subprocess.Popen(["cmd.exe", "/K", f"cd /d {cwd}"], creationflags=0x00000010)
            else:
                for term in (["x-terminal-emulator"], ["gnome-terminal", f"--working-directory={cwd}"],
                             ["konsole", "--workdir", cwd], ["xfce4-terminal", f"--working-directory={cwd}"],
                             ["tilix", "-w", cwd], ["kitty", "-d", cwd], ["alacritty", "--working-directory", cwd],
                             ["xterm"]):
                    if shutil.which(term[0]):
                        subprocess.Popen(term, cwd=cwd)
                        return
                self.append("err", T("找不到終端機程式", "No terminal emulator found"))
        except Exception as e:
            self.append("err", str(e))


def _win_split(s):
    """Windows-friendly split keeping backslashes."""
    import re
    return [a.strip('"') if a.startswith('"') else a.strip("'") for a in re.findall(r'"[^"]*"|\'[^\']*\'|\S+', s)]
