"""A calm, asynchronous first-run installer for the media tools."""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Event

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from core.downloader import _runtime
from core.runtime_setup import SetupCancelled, install_ffmpeg
from core.settings import SettingsStore
from ui.widgets import Button, label

_LOG = logging.getLogger(__name__)


class _Installer(QThread):
    progress = Signal(int, str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.cancel = Event()
        self.result: Path | None = None
        self.error = ""
        self.cancelled = False

    def run(self) -> None:
        """Download and verify tools off the main thread."""
        try:
            self.result = install_ffmpeg(self.progress.emit, self.cancel)
        except SetupCancelled:
            self.cancelled = True
        except ValueError as error:
            self.error = str(error)
            _LOG.warning("Media tool setup failed: %s", error)
        except OSError as error:
            _LOG.exception("Media tool setup could not complete")
            if isinstance(error, PermissionError):
                self.error = "Orvilo couldn't write its media tools. Check your folder permissions and try again."
            else:
                self.error = "FFmpeg couldn't be downloaded. Check your connection and free disk space, then try again."
        except Exception:
            _LOG.exception("Unexpected media tool setup failure")
            self.error = "Media tool setup couldn't finish. Please try again or choose an existing FFmpeg folder."


def runtime_available(settings: SettingsStore) -> bool:
    """Return whether both required media tools can already be located."""
    configured = str(settings.get("ffmpeg_path", ""))
    if configured and Path(configured).is_file():
        configured = str(Path(configured).parent)
    try:
        return bool(_runtime("ffmpeg", configured) and _runtime("ffprobe", configured))
    except OSError:
        return False


class RuntimeDialog(QDialog):
    """Install once, choose existing tools, or postpone setup without blocking Qt."""

    def __init__(self, parent: QWidget | None, settings: SettingsStore) -> None:
        super().__init__(parent)
        self.settings = settings
        self.worker: _Installer | None = None
        self.closing = False
        self.setWindowTitle("One last thing · Orvilo")
        self.setMinimumWidth(490)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)
        layout.addWidget(label("Make room for your favorites", "heading", True))
        layout.addWidget(label(
            "Orvilo uses FFmpeg to combine video and audio, save clips, and convert audio. "
            "Install it once and you're ready to go.", wrap=True))
        layout.addWidget(label(
            "About 110 MB · downloaded directly from Gyan, an FFmpeg Windows build publisher · "
            "verified before installation · no administrator access needed", "caption", True))
        self.status = label("Your downloads and preferences stay on this computer.", "muted", True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.browse = Button("Use existing folder", "folder", "ghost")
        self.later = Button("Later", role="ghost")
        self.install = Button("Install FFmpeg", "download", "primary")
        buttons.addWidget(self.browse)
        buttons.addStretch()
        buttons.addWidget(self.later)
        buttons.addWidget(self.install)
        layout.addLayout(buttons)
        self.install.clicked.connect(self.start_install)
        self.browse.clicked.connect(self.choose_existing)
        self.later.clicked.connect(self.reject)

    def start_install(self) -> None:
        """Begin one background attempt while keeping cancel and progress live."""
        if self.worker and self.worker.isRunning():
            return
        self.closing = False
        self.install.setEnabled(False)
        self.browse.setEnabled(False)
        self.later.setEnabled(True)
        self.later.setText("Cancel")
        self.progress.show()
        self.progress.setValue(0)
        self.status.setText("Connecting to the FFmpeg publisher…")
        self.worker = _Installer(self)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.finished_install)
        self.worker.start()

    def update_progress(self, value: int, message: str) -> None:
        """Show updates delivered on the GUI thread."""
        self.progress.setValue(value)
        if not self.closing:
            self.status.setText(message)

    def finished_install(self) -> None:
        """Persist a completed runtime, or allow another attempt after failure."""
        worker = self.worker
        if worker is None:
            return
        if worker.result is not None:
            try:
                self.settings.update({"ffmpeg_path": str(worker.result)})
                self.accept()
                return
            except (OSError, ValueError):
                _LOG.exception("Could not save installed runtime preference")
                self.status.setText("FFmpeg installed, but Orvilo couldn't save its folder. Try again after checking folder permissions.")
        elif self.closing or worker.cancelled:
            super().reject()
            return
        else:
            self.status.setText(worker.error)
        self.install.setText("Try again")
        self.install.setEnabled(True)
        self.browse.setEnabled(True)
        self.later.setEnabled(True)
        self.later.setText("Later")

    def choose_existing(self) -> None:
        """Validate both executables before saving a user-selected tool folder."""
        folder = QFileDialog.getExistingDirectory(self, "Choose the folder containing FFmpeg and FFprobe")
        if not folder:
            return
        path = Path(folder)
        if not all((path / name).is_file() for name in ("ffmpeg.exe", "ffprobe.exe")):
            self.status.setText("Choose the bin folder containing both ffmpeg.exe and ffprobe.exe.")
            return
        try:
            self.settings.update({"ffmpeg_path": folder})
            self.accept()
        except (OSError, ValueError):
            _LOG.exception("Could not save selected runtime preference")
            self.status.setText("Orvilo couldn't save that folder. Check your folder permissions and try again.")

    def reject(self) -> None:
        """Cancel cooperatively and keep the worker alive until it has cleaned up."""
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.worker.cancel.set()
            self.later.setEnabled(False)
            self.status.setText("Cancelling setup…")
        else:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Prevent closing from destroying a running installer thread."""
        if self.worker and self.worker.isRunning():
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)


def ensure_runtime(parent: QWidget | None, settings: SettingsStore) -> bool:
    """Offer setup only when needed and report whether media tools are ready."""
    if runtime_available(settings):
        return True
    return RuntimeDialog(parent, settings).exec() == QDialog.DialogCode.Accepted
