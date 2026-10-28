"""Update check against GitHub Releases, plus self-update for installed copies.

* newer release available  -> tell the user (status bar + dialog)
* running a newer version   -> mark as development build (開發版)
* installed copy (Windows installer / Linux .deb) -> download & install after consent
* portable / source copy    -> open the release page
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request

from PySide6.QtCore import QObject, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QProgressDialog, QPushButton

from . import APP_NAME, UPDATE_REPO, __version__
from .i18n import T

API_LATEST = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{UPDATE_REPO}/releases/latest"
IS_WIN = os.name == "nt"


# --------------------------------------------------------------------------- versions
def parse_version(v: str):
    nums = re.findall(r"\d+", (v or "").lstrip("vV").split("-")[0])
    return tuple(int(x) for x in nums[:4]) + (0,) * (4 - min(4, len(nums)))


def compare(a: str, b: str) -> int:
    pa, pb = parse_version(a), parse_version(b)
    return (pa > pb) - (pa < pb)


# --------------------------------------------------------------------------- install type
def install_kind() -> str:
    """'win-installer' | 'deb' | 'portable' | 'source'"""
    if not getattr(sys, "frozen", False):
        return "source"
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if IS_WIN:
        if any(f.lower().startswith("unins") and f.lower().endswith(".exe") for f in os.listdir(exe_dir)):
            return "win-installer"
        return "portable"
    if exe_dir.startswith("/opt/gitdesk") and shutil.which("dpkg"):
        return "deb"
    return "portable"


def kind_label(kind: str) -> str:
    return {"win-installer": T("安裝版", "installed"), "deb": T("安裝版 (.deb)", "installed (.deb)"),
            "portable": T("免安裝版", "portable"), "source": T("原始碼執行", "from source")}.get(kind, kind)


# --------------------------------------------------------------------------- network
def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{__version__}",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_latest() -> dict:
    data = json.loads(_get(API_LATEST).decode("utf-8"))
    return {"tag": data.get("tag_name", ""), "name": data.get("name") or data.get("tag_name", ""),
            "notes": data.get("body") or "", "url": data.get("html_url") or RELEASES_PAGE,
            "assets": [{"name": a["name"], "url": a["browser_download_url"], "size": a.get("size", 0),
                        "digest": a.get("digest") or ""} for a in data.get("assets", [])]}


def pick_asset(info: dict, kind: str):
    for a in info["assets"]:
        n = a["name"].lower()
        if kind == "win-installer" and n.startswith("gitdesk-setup") and n.endswith(".exe"):
            return a
        if kind == "deb" and n.endswith(".deb"):
            return a
    return None


class _Bridge(QObject):
    checked = Signal(object, object)           # info, error
    progress = Signal(int, int)                # done, total
    downloaded = Signal(object, object)        # path, error


# --------------------------------------------------------------------------- controller
class Updater(QObject):
    """Owned by the main window."""
    stateChanged = Signal(str, str)   # state ('dev' | 'update' | 'latest' | ''), text

    def __init__(self, window):
        super().__init__(window)
        self.win = window
        self.kind = install_kind()
        self.latest = None
        self.state = ""
        self._b = _Bridge()
        self._b.checked.connect(self._on_checked)
        self._manual = False
        self._progress = None
        self._cancel = threading.Event()

    # ------------------------------------------------------------------ check
    def check(self, manual=False):
        self._manual = manual

        def run():
            try:
                self._b.checked.emit(fetch_latest(), None)
            except Exception as e:
                self._b.checked.emit(None, e)
        threading.Thread(target=run, daemon=True).start()

    def _on_checked(self, info, err):
        if err or not info or not info.get("tag"):
            if self._manual:
                QMessageBox.warning(self.win, T("檢查更新", "Check for updates"),
                                    T("無法連線到 GitHub 取得最新版本資訊。\n請確認網路連線後再試。",
                                      "Could not reach GitHub to get the latest release.\n"
                                      "Check your internet connection and try again.") + f"\n\n{err or ''}")
            return
        self.latest = info
        c = compare(__version__, info["tag"])
        if c > 0:
            self.state = "dev"
            self.stateChanged.emit("dev", T(f"開發版 v{__version__}", f"Development build v{__version__}"))
            if self._manual:
                QMessageBox.information(self.win, T("檢查更新", "Check for updates"),
                                        T(f"你目前使用的是開發版 v{__version__}，比最新發布版 {info['tag']} 還新。",
                                          f"You are running development build v{__version__}, newer than the "
                                          f"latest release {info['tag']}."))
        elif c < 0:
            self.state = "update"
            self.stateChanged.emit("update", T(f"有新版本 {info['tag']}", f"Update available: {info['tag']}"))
            skipped = QSettings().value("update/skip", "")
            if self._manual or skipped != info["tag"]:
                self.prompt()
        else:
            self.state = "latest"
            self.stateChanged.emit("latest", "")
            if self._manual:
                QMessageBox.information(self.win, T("檢查更新", "Check for updates"),
                                        T(f"已是最新版本（v{__version__}）。", f"You're up to date (v{__version__})."))

    # ------------------------------------------------------------------ prompt
    def prompt(self):
        info = self.latest
        if not info:
            self.check(manual=True)
            return
        asset = pick_asset(info, self.kind)
        can_auto = asset is not None and self.kind in ("win-installer", "deb")
        notes = info["notes"].strip()
        if len(notes) > 1200:
            notes = notes[:1200] + "…"
        box = QMessageBox(self.win)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle(T("有新版本", "Update available"))
        box.setText(f"<b>{APP_NAME} {info['tag']}</b> " + T("已發布", "is available") +
                    f"<br>{T('目前版本', 'Current version')}: v{__version__}（{kind_label(self.kind)}）")
        if can_auto:
            body = T("要現在下載並安裝嗎？安裝時 GitDesk 會自動關閉，完成後重新開啟。",
                     "Download and install it now? GitDesk will close during the update and reopen afterwards.")
        elif self.kind == "source":
            body = T("你是從原始碼執行，請用 git pull 取得最新程式碼，或到發布頁下載。",
                     "You are running from source: git pull the latest code, or download from the release page.")
        else:
            body = T("這是免安裝版，無法自動更新。請到發布頁下載新版後取代舊的資料夾。",
                     "This is the portable version and can't update itself. Download the new version from the "
                     "release page and replace the old folder.")
        box.setInformativeText(body + (("\n\n" + T("更新內容：", "What's new:") + "\n" + notes) if notes else ""))
        btn_install = box.addButton(T("下載並安裝", "Download && install"), QMessageBox.AcceptRole) if can_auto else None
        btn_page = box.addButton(T("前往下載頁", "Open download page"), QMessageBox.ActionRole)
        btn_skip = box.addButton(T("略過此版本", "Skip this version"), QMessageBox.RejectRole)
        box.addButton(T("稍後提醒", "Remind me later"), QMessageBox.RejectRole)
        if btn_install:
            btn_install.setProperty("accent", True)
            btn_install.style().unpolish(btn_install)
            btn_install.style().polish(btn_install)
            box.setDefaultButton(btn_install)
        box.exec()
        clicked = box.clickedButton()
        if btn_install is not None and clicked is btn_install:
            self.download_and_install(asset)
        elif clicked is btn_page:
            QDesktopServices.openUrl(QUrl(info["url"]))
        elif clicked is btn_skip:
            QSettings().setValue("update/skip", info["tag"])

    # ------------------------------------------------------------------ download
    def download_and_install(self, asset):
        self._cancel.clear()
        dest_dir = tempfile.mkdtemp(prefix="gitdesk-update-")
        dest = os.path.join(dest_dir, asset["name"])
        dlg = QProgressDialog(T(f"正在下載 {asset['name']}…", f"Downloading {asset['name']}…"),
                              T("取消", "Cancel"), 0, max(1, asset["size"]), self.win)
        dlg.setWindowTitle(T("更新", "Update"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.canceled.connect(self._cancel.set)
        self._progress = dlg
        b = _Bridge(self)
        b.progress.connect(lambda done, total: (dlg.setMaximum(max(1, total)), dlg.setValue(done)))
        b.downloaded.connect(lambda path, err: self._downloaded(path, err, asset))
        self._bridge_dl = b

        def run():
            try:
                req = urllib.request.Request(asset["url"], headers={"User-Agent": f"{APP_NAME}/{__version__}"})
                h = hashlib.sha256()
                with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                    total = int(r.headers.get("Content-Length") or asset["size"] or 0)
                    done = 0
                    while True:
                        if self._cancel.is_set():
                            raise InterruptedError("cancelled")
                        chunk = r.read(256 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        b.progress.emit(done, total)
                want = asset.get("digest", "")
                if want.startswith("sha256:") and want[7:].lower() != h.hexdigest():
                    raise ValueError(T("下載的檔案校驗失敗（SHA-256 不符），已取消更新。",
                                       "Downloaded file failed verification (SHA-256 mismatch); update cancelled."))
                b.downloaded.emit(dest, None)
            except Exception as e:
                b.downloaded.emit(None, e)
        threading.Thread(target=run, daemon=True).start()

    def _downloaded(self, path, err, asset):
        if self._progress:
            self._progress.reset()
            self._progress = None
        if err:
            if not isinstance(err, InterruptedError):
                QMessageBox.warning(self.win, T("更新失敗", "Update failed"), str(err))
            return
        if self.kind == "win-installer":
            self._install_windows(path)
        elif self.kind == "deb":
            self._install_deb(path)

    # ------------------------------------------------------------------ install
    def _install_windows(self, setup):
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
        local = os.environ.get("LOCALAPPDATA", "")
        scope = "/CURRENTUSER" if local and app_dir.lower().startswith(local.lower()) else "/ALLUSERS"
        from .i18n import current_language
        lang = "chinesetraditional" if current_language() == "zh_TW" else "english"
        args = [setup, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", scope,
                f"/LANG={lang}", f'/DIR={app_dir}']
        try:
            try:
                DETACHED = 0x00000008
                subprocess.Popen(args, close_fds=True, creationflags=DETACHED)
            except OSError as e:
                if getattr(e, "winerror", None) != 740:      # 740 = elevation required
                    raise
                import ctypes
                params = subprocess.list2cmdline(args[1:])
                rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", setup, params, None, 1)
                if rc <= 32:
                    raise OSError(T("使用者取消了系統管理員權限要求", "Administrator permission was declined"))
        except Exception as e:
            QMessageBox.warning(self.win, T("更新失敗", "Update failed"),
                                T("無法啟動安裝程式：", "Could not start the installer: ") + str(e))
            return
        # quit so the installer can replace our files; it reopens GitDesk when done
        self.win.close()

    def _install_deb(self, deb):
        pk = shutil.which("pkexec")
        if not pk:
            QMessageBox.information(self.win, T("更新", "Update"), T(
                f"已下載到：\n{deb}\n\n請在終端機執行以下指令完成安裝：\nsudo apt install {deb}",
                f"Downloaded to:\n{deb}\n\nRun this in a terminal to install:\nsudo apt install {deb}"))
            return
        from PySide6.QtCore import QProcess
        proc = QProcess(self)
        self._proc = proc
        dlg = QProgressDialog(T("正在安裝更新（需要輸入系統密碼）…", "Installing update (your password is required)…"),
                              None, 0, 0, self.win)
        dlg.setWindowTitle(T("更新", "Update"))
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()
        apt = shutil.which("apt-get") or "apt-get"

        def done(code, _status):
            dlg.reset()
            if code == 0:
                if QMessageBox.question(self.win, T("更新完成", "Update installed"),
                                        T("更新已安裝。要現在重新啟動 GitDesk 嗎？", "Update installed. Restart GitDesk now?")) \
                        == QMessageBox.Yes:
                    rw = self.win.current_repo()
                    subprocess.Popen(["/usr/bin/gitdesk"] + ([rw.repo.path] if rw else []),
                                     start_new_session=True)
                    self.win.close()
            else:
                out = bytes(proc.readAllStandardError()).decode("utf-8", "replace")
                QMessageBox.warning(self.win, T("更新失敗", "Update failed"),
                                    T("安裝沒有完成（可能取消了密碼輸入）。\n可手動執行：", "Installation did not finish "
                                      "(the password prompt may have been cancelled).\nYou can run manually:")
                                    + f"\nsudo apt install {deb}\n\n{out[-1500:]}")
        proc.finished.connect(done)
        proc.start(pk, [apt, "install", "-y", deb])
