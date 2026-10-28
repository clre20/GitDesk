import os
import sys


def askpass(prompt: str) -> int:
    """Invoked by git/ssh (GIT_ASKPASS) to ask the user for a username/password."""
    from PySide6.QtWidgets import QApplication, QInputDialog, QLineEdit
    app = QApplication(sys.argv[:1])
    secret = any(w in prompt.lower() for w in ("password", "passphrase", "token", "密碼"))
    text, ok = QInputDialog.getText(None, "GitDesk — Git", prompt,
                                    QLineEdit.Password if secret else QLineEdit.Normal)
    if not ok:
        return 1
    out = text + "\n"
    try:
        sys.stdout.write(out)
        sys.stdout.flush()
    except Exception:
        os.write(1, out.encode())
    return 0


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--askpass":
        sys.exit(askpass(" ".join(sys.argv[2:]) or "Password:"))

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    from . import APP_ID, APP_NAME, __version__
    QCoreApplication.setOrganizationName(APP_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setApplicationVersion(__version__)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setDesktopFileName(APP_ID)

    from . import icons, theme
    theme.apply_theme(app)
    app.setWindowIcon(icons.app_icon())

    from .mainwindow import MainWindow
    from .startup import LanguageDialog, StartupDialog, add_recent, ensure_repo
    from PySide6.QtCore import QSettings

    # very first launch: ask for the language before anything else
    if QSettings().value("ui/language", "") not in ("zh_TW", "en"):
        LanguageDialog().exec()     # closing it keeps the default (English)

    # The working folder for this session must be chosen before the main window opens.
    path = None
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.isdir(args[0]):
        path = ensure_repo(None, os.path.abspath(args[0]))
    while not path:
        d = StartupDialog()
        ok = d.exec()
        if d.relaunch:          # language switched on the start screen
            continue
        if not ok or not d.path:
            return 0
        path = d.path

    w = MainWindow()
    w.show()
    w.open_repo(path)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
