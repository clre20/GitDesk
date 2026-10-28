"""Thin wrapper around the git command line.

Everything the UI does is a real `git` invocation, so the app behaves exactly
like git on the command line and stays in sync with other tools (an AI agent,
a terminal, an IDE) that operate on the same repository.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSettings, Signal

IS_WIN = os.name == "nt"
NO_WINDOW = 0x08000000 if IS_WIN else 0
BASE_CFG = ["-c", "core.quotepath=false", "-c", "color.ui=false",
            "-c", "i18n.logOutputEncoding=utf-8", "-c", "log.showSignature=false"]


# --------------------------------------------------------------------------- log
class CommandLog(QObject):
    """Global log of every git command the UI runs (shown in the console dock)."""
    entry = Signal(str, str)  # kind: cmd | out | err | info, text


LOG = CommandLog()


def git_executable() -> str:
    s = QSettings().value("git/path", "")
    if s and os.path.exists(s):
        return s
    p = shutil.which("git")
    if p:
        return p
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     os.path.expandvars(r"%LOCALAPPDATA%\Programs")):
            c = os.path.join(base, "Git", "cmd", "git.exe")
            if os.path.exists(c):
                return c
    return "git"


def git_available() -> bool:
    try:
        r = subprocess.run([git_executable(), "--version"], capture_output=True,
                           creationflags=NO_WINDOW, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _config_dir() -> str:
    if IS_WIN:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(base, "GitDesk")
    os.makedirs(d, exist_ok=True)
    return d


def _askpass_script() -> Optional[str]:
    """A tiny wrapper so git/ssh can ask for credentials through our GUI."""
    if IS_WIN:
        return None  # Git for Windows ships Git Credential Manager / its own askpass
    path = os.path.join(_config_dir(), "askpass.sh")
    if getattr(sys, "frozen", False):
        cmd = f'exec "{sys.executable}" --askpass "$@"'
    else:
        pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = f'PYTHONPATH="{pkg_parent}" exec "{sys.executable}" -m gitdesk --askpass "$@"'
    content = "#!/bin/sh\n" + cmd + "\n"
    try:
        if not os.path.exists(path) or open(path).read() != content:
            with open(path, "w") as f:
                f.write(content)
            os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return path
    except OSError:
        return None


def base_env() -> dict:
    env = os.environ.copy()
    env["GIT_EDITOR"] = "true"          # never block waiting for an editor
    env["GIT_MERGE_AUTOEDIT"] = "no"
    env["GIT_PAGER"] = "cat"
    env["GIT_TERMINAL_PROMPT"] = "0"
    ap = _askpass_script()
    if ap and not env.get("GIT_ASKPASS"):
        env["GIT_ASKPASS"] = ap
        env["SSH_ASKPASS"] = ap
        env["SSH_ASKPASS_REQUIRE"] = "force"
    return env


class GitError(Exception):
    def __init__(self, args, code, out, err):
        self.args_ = args
        self.code = code
        self.out = out
        self.err = err
        super().__init__((err or out).strip() or f"git exited with {code}")


def run_git(args: List[str], cwd: Optional[str] = None, input: Optional[str] = None,
            check: bool = True, log: bool = False, env: Optional[dict] = None,
            binary: bool = False):
    full = [git_executable()] + BASE_CFG + list(args)
    if log:
        LOG.entry.emit("cmd", "git " + " ".join(shlex.quote(a) for a in args))
    e = base_env()
    if env:
        e.update(env)
    p = subprocess.run(full, cwd=cwd, input=input.encode("utf-8") if input is not None else None,
                       capture_output=True, env=e, creationflags=NO_WINDOW)
    if binary:
        out = p.stdout
    else:
        out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if log:
        if not binary and out.strip():
            LOG.entry.emit("out", out.rstrip())
        if err.strip():
            LOG.entry.emit("err" if p.returncode else "out", err.rstrip())
    if check and p.returncode != 0:
        raise GitError(args, p.returncode, out if not binary else "", err)
    return out


# --------------------------------------------------------------------------- async
class GitTask(QObject):
    """Runs a (possibly long) git command asynchronously, streaming output."""
    output = Signal(str)
    done = Signal(int, str, str)  # code, stdout, stderr

    def __init__(self, args: List[str], cwd: Optional[str], env: Optional[dict] = None,
                 parent=None, program: Optional[str] = None):
        super().__init__(parent)
        self.args = args
        self.cwd = cwd
        self._out = []
        self._err = []
        self.proc = QProcess(self)
        qenv = QProcessEnvironment()
        e = base_env()
        if env:
            e.update(env)
        for k, v in e.items():
            qenv.insert(k, v)
        self.proc.setProcessEnvironment(qenv)
        if cwd:
            self.proc.setWorkingDirectory(cwd)
        self.program = program
        self.proc.readyReadStandardOutput.connect(self._read_out)
        self.proc.readyReadStandardError.connect(self._read_err)
        self.proc.finished.connect(self._finished)
        self.proc.errorOccurred.connect(self._error)

    def start(self):
        if self.program:
            LOG.entry.emit("cmd", " ".join(shlex.quote(a) for a in [self.program] + self.args))
            self.proc.start(self.program, self.args)
        else:
            LOG.entry.emit("cmd", "git " + " ".join(shlex.quote(a) for a in self.args))
            self.proc.start(git_executable(), BASE_CFG + self.args)

    def kill(self):
        self.proc.kill()

    def _read_out(self):
        t = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._out.append(t)
        self.output.emit(t)

    def _read_err(self):
        t = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        self._err.append(t)
        self.output.emit(t)

    def _error(self, err):
        if err == QProcess.FailedToStart:
            msg = "Failed to start git. Is git installed?"
            self._err.append(msg)
            LOG.entry.emit("err", msg)
            self.done.emit(-1, "", msg)

    def _finished(self, code, _status):
        out = "".join(self._out)
        err = "".join(self._err)
        text = (out + err).rstrip()
        if text:
            LOG.entry.emit("err" if code else "out", text)
        self.done.emit(code, out, err)


# --------------------------------------------------------------------------- models
@dataclass
class FileStatus:
    path: str
    x: str = "."   # index status
    y: str = "."   # worktree status
    orig: str = ""
    kind: str = "1"  # 1 normal, 2 rename, u unmerged, ? untracked, ! ignored
    submodule: bool = False

    @property
    def conflicted(self):
        return self.kind == "u"


@dataclass
class Status:
    head: str = ""
    oid: str = ""
    upstream: str = ""
    ahead: int = 0
    behind: int = 0
    staged: List[FileStatus] = field(default_factory=list)
    unstaged: List[FileStatus] = field(default_factory=list)
    conflicts: List[FileStatus] = field(default_factory=list)
    raw: bytes = b""


@dataclass
class Branch:
    name: str
    sha: str
    upstream: str = ""
    track: str = ""
    current: bool = False
    subject: str = ""
    date: int = 0


@dataclass
class Commit:
    sha: str
    parents: List[str]
    author: str
    email: str
    time: int
    refs: str
    subject: str


@dataclass
class Stash:
    index: int
    ref: str
    message: str
    sha: str


@dataclass
class Worktree:
    path: str
    head: str = ""
    branch: str = ""
    bare: bool = False
    detached: bool = False
    locked: bool = False
    prunable: bool = False


@dataclass
class Submodule:
    path: str
    sha: str
    state: str  # ' ', '-', '+', 'U'
    describe: str = ""


# --------------------------------------------------------------------------- repo
class Repo:
    def __init__(self, path: str):
        top = run_git(["rev-parse", "--show-toplevel"], cwd=path).strip()
        self.path = os.path.normpath(top)
        gd = run_git(["rev-parse", "--git-dir"], cwd=self.path).strip()
        self.git_dir = os.path.normpath(gd if os.path.isabs(gd) else os.path.join(self.path, gd))
        cd = run_git(["rev-parse", "--git-common-dir"], cwd=self.path).strip()
        self.common_dir = os.path.normpath(cd if os.path.isabs(cd) else os.path.join(self.path, cd))

    # -- basic helpers -------------------------------------------------------
    @staticmethod
    def is_repo(path: str) -> bool:
        try:
            out = run_git(["rev-parse", "--is-inside-work-tree"], cwd=path).strip()
            return out == "true"
        except Exception:
            return False

    @staticmethod
    def init(path: str, initial_branch: str = "", bare: bool = False):
        args = ["init"]
        if initial_branch:
            args += ["-b", initial_branch]
        if bare:
            args.append("--bare")
        args.append(path)
        return run_git(args, log=True)

    def git(self, *args, input=None, check=True, log=False, env=None, binary=False):
        return run_git(list(args), cwd=self.path, input=input, check=check, log=log,
                       env=env, binary=binary)

    def task(self, args, env=None, parent=None) -> GitTask:
        return GitTask(list(args), self.path, env=env, parent=parent)

    @property
    def name(self):
        return os.path.basename(self.path)

    def head_valid(self) -> bool:
        return bool(self.git("rev-parse", "--verify", "-q", "HEAD", check=False).strip())

    # -- status ---------------------------------------------------------------
    def status(self) -> Status:
        raw = self.git("status", "--porcelain=v2", "-z", "--branch",
                       "--untracked-files=all", binary=True)
        st = Status(raw=raw)
        parts = raw.decode("utf-8", "replace").split("\0")
        i = 0
        while i < len(parts):
            line = parts[i]
            i += 1
            if not line:
                continue
            if line.startswith("# "):
                k, _, v = line[2:].partition(" ")
                if k == "branch.head":
                    st.head = v
                elif k == "branch.oid":
                    st.oid = v
                elif k == "branch.upstream":
                    st.upstream = v
                elif k == "branch.ab":
                    m = re.match(r"\+(\d+) -(\d+)", v)
                    if m:
                        st.ahead, st.behind = int(m.group(1)), int(m.group(2))
                continue
            t = line[0]
            if t == "1":
                f = line.split(" ", 8)
                fs = FileStatus(path=f[8], x=f[1][0], y=f[1][1], kind="1",
                                submodule=f[2].startswith("S"))
            elif t == "2":
                f = line.split(" ", 9)
                fs = FileStatus(path=f[9], x=f[1][0], y=f[1][1], kind="2",
                                orig=parts[i], submodule=f[2].startswith("S"))
                i += 1
            elif t == "u":
                f = line.split(" ", 10)
                fs = FileStatus(path=f[10], x=f[1][0], y=f[1][1], kind="u")
                st.conflicts.append(fs)
                continue
            elif t == "?":
                st.unstaged.append(FileStatus(path=line[2:], x="?", y="?", kind="?"))
                continue
            else:
                continue
            if fs.x != ".":
                st.staged.append(fs)
            if fs.y != ".":
                st.unstaged.append(fs)
        return st

    # -- state of in-progress operations ---------------------------------------
    def operation_state(self) -> str:
        g = self.git_dir
        if os.path.isdir(os.path.join(g, "rebase-merge")) or os.path.isdir(os.path.join(g, "rebase-apply")):
            if os.path.exists(os.path.join(g, "rebase-apply", "applying")):
                return "am"
            return "rebase"
        if os.path.exists(os.path.join(g, "MERGE_HEAD")):
            return "merge"
        if os.path.exists(os.path.join(g, "CHERRY_PICK_HEAD")):
            return "cherry-pick"
        if os.path.exists(os.path.join(g, "REVERT_HEAD")):
            return "revert"
        if os.path.exists(os.path.join(g, "BISECT_LOG")):
            return "bisect"
        return ""

    def rebase_progress(self):
        d = os.path.join(self.git_dir, "rebase-merge")
        try:
            n = int(open(os.path.join(d, "msgnum")).read())
            t = int(open(os.path.join(d, "end")).read())
            return n, t
        except Exception:
            return None

    # -- refs -------------------------------------------------------------------
    def current_branch(self) -> str:
        return self.git("branch", "--show-current", check=False).strip()

    def branches(self) -> List[Branch]:
        fmt = "%(HEAD)%00%(refname:short)%00%(objectname)%00%(upstream:short)%00%(upstream:track)%00%(committerdate:unix)%00%(contents:subject)"
        out = self.git("for-each-ref", "--format=" + fmt, "refs/heads", check=False)
        res = []
        for line in out.splitlines():
            p = line.split("\0")
            if len(p) < 7:
                continue
            res.append(Branch(name=p[1], sha=p[2], upstream=p[3], track=p[4],
                              current=p[0] == "*", date=int(p[5] or 0), subject=p[6]))
        return res

    def remote_branches(self) -> List[Branch]:
        fmt = "%(refname:short)%00%(objectname)%00%(symref)"
        out = self.git("for-each-ref", "--format=" + fmt, "refs/remotes", check=False)
        res = []
        for line in out.splitlines():
            p = line.split("\0")
            if len(p) < 3 or p[2]:  # skip origin/HEAD symref
                continue
            if "/" not in p[0]:
                continue
            res.append(Branch(name=p[0], sha=p[1]))
        return res

    def remotes(self) -> List[dict]:
        out = self.git("remote", "-v", check=False)
        rem = {}
        for line in out.splitlines():
            m = re.match(r"(\S+)\s+(\S+)\s+\((fetch|push)\)", line)
            if m:
                rem.setdefault(m.group(1), {"name": m.group(1), "fetch": "", "push": ""})[m.group(3)] = m.group(2)
        # remotes without URL still show up in `git remote`
        for n in self.git("remote", check=False).split():
            rem.setdefault(n, {"name": n, "fetch": "", "push": ""})
        return list(rem.values())

    def tags(self) -> List[dict]:
        fmt = "%(refname:short)%00%(objectname)%00%(*objectname)%00%(objecttype)%00%(contents:subject)%00%(creatordate:unix)"
        out = self.git("for-each-ref", "--sort=-creatordate", "--format=" + fmt, "refs/tags", check=False)
        res = []
        for line in out.splitlines():
            p = line.split("\0")
            if len(p) < 6:
                continue
            res.append({"name": p[0], "sha": p[2] or p[1], "annotated": p[3] == "tag",
                        "subject": p[4], "date": int(p[5] or 0)})
        return res

    def stashes(self) -> List[Stash]:
        out = self.git("stash", "list", "--format=%gd%x00%H%x00%gs", check=False)
        res = []
        for line in out.splitlines():
            p = line.split("\0")
            if len(p) < 3:
                continue
            m = re.search(r"\{(\d+)\}", p[0])
            res.append(Stash(index=int(m.group(1)) if m else len(res), ref=p[0], sha=p[1], message=p[2]))
        return res

    def worktrees(self) -> List[Worktree]:
        out = self.git("worktree", "list", "--porcelain", check=False)
        res, cur = [], None
        for line in out.splitlines():
            if line.startswith("worktree "):
                cur = Worktree(path=os.path.normpath(line[9:]))
                res.append(cur)
            elif cur is None:
                continue
            elif line.startswith("HEAD "):
                cur.head = line[5:]
            elif line.startswith("branch "):
                cur.branch = line[7:].replace("refs/heads/", "", 1)
            elif line == "bare":
                cur.bare = True
            elif line == "detached":
                cur.detached = True
            elif line.startswith("locked"):
                cur.locked = True
            elif line.startswith("prunable"):
                cur.prunable = True
        return res

    def submodules(self) -> List[Submodule]:
        if not os.path.exists(os.path.join(self.path, ".gitmodules")):
            return []
        out = self.git("submodule", "status", "--recursive", check=False)
        res = []
        for line in out.splitlines():
            if not line:
                continue
            state = line[0]
            rest = line[1:].split(" ", 2)
            if len(rest) < 2:
                continue
            res.append(Submodule(path=rest[1], sha=rest[0], state=state,
                                 describe=rest[2].strip("()") if len(rest) > 2 else ""))
        return res

    def all_refs_for_completion(self) -> List[str]:
        out = self.git("for-each-ref", "--format=%(refname:short)",
                       "refs/heads", "refs/remotes", "refs/tags", check=False)
        return [r for r in out.splitlines() if r and not r.endswith("/HEAD")]

    # -- history ------------------------------------------------------------------
    LOG_FMT = "%H%x1f%P%x1f%an%x1f%ae%x1f%at%x1f%D%x1f%s%x1e"

    def log(self, scope: str = "all", limit: int = 3000, skip: int = 0, extra=None,
            paths=None) -> List[Commit]:
        args = ["log", "--topo-order", "--decorate=full", f"--format={self.LOG_FMT}", f"-n{limit}"]
        if skip:
            args.append(f"--skip={skip}")
        if extra:
            args += extra
        if scope == "all":
            args += ["--branches", "--remotes", "--tags", "HEAD"]
        elif scope == "current":
            args.append("HEAD")
        elif scope:
            args.append(scope)
        if paths:
            args.append("--")
            args += paths
        out = self.git(*args, check=False)
        res = []
        for rec in out.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            p = rec.split("\x1f")
            if len(p) < 7:
                continue
            res.append(Commit(sha=p[0], parents=p[1].split() if p[1] else [], author=p[2],
                              email=p[3], time=int(p[4] or 0), refs=p[5], subject=p[6]))
        return res

    def commit_details(self, sha: str) -> dict:
        fmt = "%H%x00%P%x00%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%D%x00%G?%x00%GS%x00%N%x00%B"
        out = self.git("show", "-s", "--decorate=short", f"--format={fmt}", sha, check=False)
        p = out.split("\0")
        if len(p) < 13:
            return {}
        return {"sha": p[0], "parents": p[1].split(), "author": p[2], "email": p[3], "adate": p[4],
                "committer": p[5], "cemail": p[6], "cdate": p[7], "refs": p[8], "sig": p[9],
                "signer": p[10], "notes": p[11].strip(), "message": p[12].rstrip()}

    def changed_files(self, sha: str, parent: Optional[str] = None) -> List[tuple]:
        """List (status, path, orig) changed by a commit (vs first parent)."""
        if parent:
            out = self.git("diff", "--name-status", "-z", "-M", parent, sha, check=False)
        else:
            out = self.git("diff-tree", "--root", "--no-commit-id", "-r", "-M", "--name-status",
                           "-z", "-m", "--first-parent", sha, check=False)
        parts = out.split("\0")
        res, i = [], 0
        while i < len(parts):
            s = parts[i]
            i += 1
            if not s:
                continue
            if s[0] in "RC" and i + 1 < len(parts):
                res.append((s[0], parts[i + 1], parts[i]))
                i += 2
            elif i < len(parts):
                res.append((s[0], parts[i], ""))
                i += 1
        return res

    # -- diffs ------------------------------------------------------------------
    def diff_worktree(self, path: str, untracked=False, opts=None) -> str:
        opts = opts or []
        if untracked:
            full = os.path.join(self.path, path)
            if os.path.isdir(full):
                return ""
            return self.git("diff", "--no-index", "--no-color", *opts, "--",
                            "/dev/null", path, check=False)
        return self.git("diff", "--no-color", *opts, "--", path, check=False)

    def diff_staged(self, path: str, opts=None) -> str:
        opts = opts or []
        if self.head_valid():
            return self.git("diff", "--cached", "--no-color", *opts, "--", path, check=False)
        return self.git("diff", "--cached", "--no-color", *opts, "--", path, check=False)

    def diff_commit(self, sha: str, path: Optional[str] = None, opts=None, parent=None) -> str:
        opts = opts or []
        if parent:
            args = ["diff", "--no-color", "-M", *opts, parent, sha]
        else:
            args = ["show", "--no-color", "--format=", "-M", "--first-parent", "-m", *opts, sha]
        if path:
            args += ["--", path]
        return self.git(*args, check=False)

    def apply_patch(self, patch: str, args: List[str]):
        return self.git("apply", "--recount", "--whitespace=nowarn", *args, "-",
                        input=patch, log=True)

    # -- misc ------------------------------------------------------------------
    def config_get(self, key: str, scope: Optional[str] = None) -> str:
        args = ["config"]
        if scope:
            args.append("--" + scope)
        args += ["--get", key]
        return self.git(*args, check=False).strip()

    def lfs_available(self) -> bool:
        try:
            run_git(["lfs", "version"], cwd=self.path)
            return True
        except Exception:
            return False
