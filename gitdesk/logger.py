"""Diagnostic logging to files, for debugging and bug reports.

Location:
  Windows: %APPDATA%\\GitDesk\\logs\\
  Linux:   ~/.config/GitDesk/logs/

Files:
  gitdesk.log   rotating text log (5 MB x 5): startup info, every git command with
                duration and exit code, errors, update checks, UI stalls
  crash.log     native crashes (faulthandler) — survives hard crashes

What is logged: app/OS/git versions, commands and their errors, Python tracebacks,
stack of the UI thread when the window stops responding (> 3 s).
What is NOT logged: passwords/tokens (credentials never pass through the log),
file contents, environment variables.
"""
from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import os
import platform
import sys
import threading
import time
import traceback
import zipfile

log = logging.getLogger("gitdesk")
_crash_file = None
_dir = None


def log_dir() -> str:
    global _dir
    if _dir is None:
        if os.name == "nt":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
        else:
            base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        _dir = os.path.join(base, "GitDesk", "logs")
        os.makedirs(_dir, exist_ok=True)
    return _dir


def log_file() -> str:
    return os.path.join(log_dir(), "gitdesk.log")


def setup(verbose: bool = False):
    """Call once at startup, before the UI is created."""
    global _crash_file
    if log.handlers:
        return
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    try:
        h = logging.handlers.RotatingFileHandler(log_file(), maxBytes=5 * 1024 * 1024, backupCount=5,
                                                 encoding="utf-8")
    except OSError:
        return
    h.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s [%(threadName)s] %(message)s",
                                     "%Y-%m-%d %H:%M:%S"))
    log.addHandler(h)
    log.propagate = False
    # native crashes (segfaults inside Qt etc.)
    try:
        _crash_file = open(os.path.join(log_dir(), "crash.log"), "a", encoding="utf-8")
        _crash_file.write(f"\n=== session {time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()} ===\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        pass
    sys.excepthook = _excepthook
    threading.excepthook = lambda a: _excepthook(a.exc_type, a.exc_value, a.exc_traceback, a.thread)


def set_verbose(on: bool):
    log.setLevel(logging.DEBUG if on else logging.INFO)


def system_info() -> str:
    from . import __version__
    lines = [f"GitDesk {__version__}"]
    try:
        from .updater import install_kind
        lines.append(f"install: {install_kind()}")
    except Exception:
        pass
    lines.append(f"OS: {platform.platform()} ({platform.machine()})")
    lines.append(f"Python: {sys.version.split()[0]}  frozen={getattr(sys, 'frozen', False)}")
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        lines.append(f"PySide6: {PySide6.__version__}  Qt: {qVersion()}")
    except Exception:
        pass
    try:
        from .git import git_executable, run_git
        lines.append(f"git: {run_git(['--version'], check=False).strip()}  ({git_executable()})")
    except Exception as e:
        lines.append(f"git: unavailable ({e})")
    try:
        from .i18n import current_language
        lines.append(f"language: {current_language()}")
    except Exception:
        pass
    return "\n".join(lines)


def log_startup():
    log.info("=" * 70)
    for line in system_info().splitlines():
        log.info(line)


# --------------------------------------------------------------------------- git commands
def git_command(cmd: str, code: int, seconds: float, err: str = "", out: str = ""):
    level = logging.WARNING if code else logging.INFO
    msg = f"git ({seconds * 1000:.0f} ms, exit {code}): {cmd}"
    if code and err:
        msg += "\n    " + err.strip()[-2000:].replace("\n", "\n    ")
    log.log(level, msg)
    if out and log.isEnabledFor(logging.DEBUG):
        log.debug("    output: " + out.strip()[:4000].replace("\n", "\n    "))
    if seconds > 5:
        log.warning(f"slow git command ({seconds:.1f} s): {cmd}")


# --------------------------------------------------------------------------- exceptions
_error_ui_hook = None


def set_error_ui(callback):
    """callback(summary_text) is invoked on the UI thread for uncaught exceptions."""
    global _error_ui_hook
    _error_ui_hook = callback


def _excepthook(etype, value, tb, thread=None):
    text = "".join(traceback.format_exception(etype, value, tb))
    log.error(f"Uncaught exception{' in thread ' + thread.name if thread else ''}:\n{text}")
    if _error_ui_hook and thread is None:
        try:
            _error_ui_hook(f"{etype.__name__}: {value}")
        except Exception:
            pass


# --------------------------------------------------------------------------- UI stall watchdog
class StallWatchdog:
    """Logs the UI thread's stack when the window stops responding for > threshold."""

    def __init__(self, threshold=3.0):
        from PySide6.QtCore import QTimer
        self.threshold = threshold
        self.main_id = threading.get_ident()
        self.beat = time.monotonic()
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(250)
        self._stalled = False
        threading.Thread(target=self._watch, name="stall-watchdog", daemon=True).start()

    def _tick(self):
        if self._stalled:
            log.warning(f"UI responsive again after {time.monotonic() - self.beat:.1f} s")
            self._stalled = False
        self.beat = time.monotonic()

    def _watch(self):
        while True:
            time.sleep(1.0)
            gap = time.monotonic() - self.beat
            if gap > self.threshold and not self._stalled:
                self._stalled = True
                frame = sys._current_frames().get(self.main_id)
                stack = "".join(traceback.format_stack(frame)[-15:]) if frame else "(no frame)"
                log.warning(f"UI not responding for {gap:.1f} s; UI thread is at:\n{stack}")


# --------------------------------------------------------------------------- export
def export_diagnostics(dest_zip: str, extra: str = "") -> str:
    """Zip logs + system info for a bug report."""
    for h in log.handlers:
        try:
            h.flush()
        except Exception:
            pass
    with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("system-info.txt", system_info() + ("\n\n" + extra if extra else ""))
        for name in sorted(os.listdir(log_dir())):
            p = os.path.join(log_dir(), name)
            if os.path.isfile(p) and (name.startswith("gitdesk.log") or name == "crash.log"):
                z.write(p, name)
    return dest_zip
