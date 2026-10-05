"""Orvilo desktop entry point and repeatable offscreen UI smoke check."""
from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
from pathlib import Path


def main() -> int:
    """Launch the app, preserving its single-instance local data stores."""
    parser = argparse.ArgumentParser(description="Orvilo — video, saved beautifully")
    parser.add_argument("--smoke-test", metavar="DIRECTORY", help="Render app pages offscreen and exit")
    parser.add_argument("--verify-runtime", metavar="DIRECTORY", help="Verify bundled conversions using local generated media and exit")
    parser.add_argument("--ffmpeg-path", default="", help="FFmpeg folder for an isolated runtime verification")
    args = parser.parse_args()
    if args.smoke_test or args.verify_runtime:
        destination = Path(args.smoke_test or args.verify_runtime).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["ORVILO_DATA_DIR"] = str(destination / "smoke-data")
        os.environ["ORVILO_SKIP_RUNTIME_SETUP"] = "1"

    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtGui import QFont, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox
    from utils.paths import asset_path, data_dir
    from utils.logging_setup import configure_logging

    app = QApplication(sys.argv[:1])
    # The offscreen Qt platform does not discover Windows fonts automatically.
    # Register existing system fonts for reproducible previews without bundling them.
    if args.smoke_test:
        from PySide6.QtGui import QFontDatabase
        font_folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for filename in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "SegUIVar.ttf"):
            if (font_folder / filename).is_file():
                QFontDatabase.addApplicationFont(str(font_folder / filename))
    os.environ.setdefault("DENO_NO_UPDATE_CHECK", "1")
    app.setApplicationName("Orvilo")
    app.setOrganizationName("Orvilo")
    app.setApplicationVersion("1.0.2")
    app.setFont(QFont("Segoe UI Variable", 10))
    app.setWindowIcon(QIcon(str(asset_path("logo.ico"))))
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Orvilo.Desktop.1")
        except OSError:
            pass
    try:
        configure_logging()
        lock = QLockFile(str(data_dir() / "orvilo.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            QMessageBox.information(None, "Orvilo is already running", "Open Orvilo from the Windows system tray.")
            return 0
        from core.engine import activate_engine
        activate_engine()
        if args.verify_runtime:
            from core.diagnostics import verify_runtime
            verify_runtime(destination, args.ffmpeg_path)
            lock.unlock()
            return 0
        from core.history import HistoryStore
        from core.queue import QueueManager
        from core.settings import SettingsStore
        from ui.window import MainWindow
        settings = SettingsStore()
        if args.smoke_test:
            settings.update({"first_run": False, "clipboard_detection": False, "minimize_to_tray": False})
        history = HistoryStore()
        queue = QueueManager(settings, history)
        window = MainWindow(settings, history, queue)
        window.show()

        def unexpected_error(error_type: type[BaseException], value: BaseException, trace: object) -> None:
            logging.getLogger(__name__).error("Unhandled UI error", exc_info=(error_type, value, trace))
            QMessageBox.warning(window, "Something went wrong", "Orvilo could not finish that action. Try again. Details are saved in the local log.")

        sys.excepthook = unexpected_error
        if args.smoke_test:
            def capture() -> None:
                from PySide6.QtWidgets import QStackedWidget
                from ui.theme import apply_theme
                stack = window.findChild(QStackedWidget)
                for theme in ("dark", "light"):
                    apply_theme(app, theme, settings.get("accent"))
                    for index, name in enumerate(("download", "queue", "history", "settings")):
                        if stack:
                            window.navigate(index, animate=False)
                        app.processEvents()
                        window.grab().save(str(destination / f"{theme}-{name}.png"))
                queue.shutdown()
                app.quit()
            QTimer.singleShot(700, capture)
        result = app.exec()
        queue.shutdown()
        history.close()
        lock.unlock()
        return result
    except Exception:
        logging.getLogger(__name__).exception("Startup failed")
        if args.smoke_test or args.verify_runtime:
            import traceback
            (destination / "verification-error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            return 1
        QMessageBox.critical(None, "Orvilo could not start", "Check that setup completed, then try again. Local diagnostics are in %LOCALAPPDATA%\\Orvilo\\logs.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
