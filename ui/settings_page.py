"""Persisted appearance, download, network and engine preferences."""
from __future__ import annotations

from typing import Any
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QGridLayout, QHBoxLayout,
    QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)

from core.engine import engine_version, update_engine
from ui.widgets import Button, TaskRunner, card, field_row, label, scroll_page
from ui.runtime_dialog import ensure_runtime
from utils.errors import friendly_error
from utils.paths import data_dir


class SettingsPage(QWidget):
    """Present focused groups of preferences with one explicit Save action."""

    saved = Signal()
    notice = Signal(str)

    def __init__(self, settings: Any, queue: Any, tasks: TaskRunner) -> None:
        super().__init__()
        self.settings, self.queue, self.tasks = settings, queue, tasks
        self.fields: dict[str, QWidget] = {}
        self.accent = settings.get("accent", "#7C5CFF")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _, layout = scroll_page()
        root.addWidget(scroll)
        heading = QHBoxLayout()
        heading.addWidget(label("Make it yours", "heading"), 1)
        save = Button("Save changes", "check", "primary")
        save.clicked.connect(self.save)
        heading.addWidget(save)
        layout.addLayout(heading)
        layout.addWidget(label("A quiet workspace, tuned to the way you save.", "muted"))

        appearance, box = card()
        box.addWidget(label("Appearance & behavior", "section"))
        row = QHBoxLayout()
        theme = self.combo("theme", (("Dark", "dark"), ("Light", "light")))
        row.addWidget(field_row("Theme", theme), 1)
        self.accent_button = Button(self.accent)
        self.accent_button.clicked.connect(self.choose_accent)
        row.addWidget(field_row("Accent color", self.accent_button), 1)
        box.addLayout(row)
        box.addWidget(self.checkbox("clipboard_detection", "Detect links on the clipboard"))
        box.addWidget(self.checkbox("minimize_to_tray", "Keep Orvilo in the system tray when minimized or closed"))
        layout.addWidget(appearance)

        downloads, box = card()
        box.addWidget(label("Downloads", "section"))
        box.addWidget(self.path_field("download_folder", "Save files to", directory=True))
        row = QHBoxLayout()
        parallel = self.spin("parallel_downloads", 1, 6)
        limit = self.spin("speed_limit_kib", 0, 1_000_000)
        limit.setSpecialValueText("Unlimited")
        row.addWidget(field_row("Parallel downloads", parallel), 1)
        row.addWidget(field_row("Limit per download (KiB/s)", limit), 1)
        box.addLayout(row)
        template = self.line("filename_template")
        box.addWidget(field_row("Filename template", template, "Use yt-dlp fields, for example %(title).160B [%(id)s].%(ext)s. Quality and clip range are appended automatically."))
        box.addWidget(self.checkbox("organize_by_site", "Create a subfolder for each site"))
        layout.addWidget(downloads)

        network, box = card()
        box.addWidget(label("Access & connection", "section"))
        browser = self.combo("browser", (("No browser cookies", "none"), ("Chrome", "chrome"), ("Edge", "edge"), ("Firefox", "firefox")))
        box.addWidget(field_row("Cookies from browser", browser, "Uses your existing login locally. Close the browser first if cookies are locked; Windows may require Firefox or a cookies file."))
        box.addWidget(field_row("Browser profile (optional)", self.line("browser_profile"), "Leave blank for the default profile, or enter its name/path."))
        box.addWidget(self.path_field("cookie_file", "Netscape cookies file (optional)", directory=False))
        proxy = self.line("proxy")
        proxy.setPlaceholderText("http://host:port or socks5://host:port")
        proxy.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        box.addWidget(field_row("Proxy (optional)", proxy, "Applied to extraction and downloads. Clips require HTTP(S) and an unlimited speed setting."))
        layout.addWidget(network)

        engine, box = card()
        box.addWidget(label("Download engine", "section"))
        self.engine_label = label(f"yt-dlp {engine_version()}", "muted")
        box.addWidget(self.engine_label)
        box.addWidget(self.path_field("ffmpeg_path", "FFmpeg folder or executable (optional override)", directory=True))
        box.addWidget(self.path_field("js_runtime_path", "Deno executable (optional override)", directory=False))
        box.addWidget(label("FFmpeg installs once from its publisher. Deno is included. Engine updates take effect after restarting Orvilo.", "caption", True))
        tools_button = Button("Set up FFmpeg", "download")
        tools_button.clicked.connect(self.setup_runtime)
        box.addWidget(tools_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.update_button = Button("Update yt-dlp", "refresh")
        self.update_button.clicked.connect(self.update_engine)
        box.addWidget(self.update_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.update_status = label("", "muted", True)
        box.addWidget(self.update_status)
        row = QHBoxLayout()
        for text, folder in (("Open logs", data_dir() / "logs"), ("Site plugins", data_dir() / "plugins")):
            button = Button(text, "folder", "ghost")
            button.clicked.connect(lambda _checked=False, target=folder: self.open_folder(target))
            row.addWidget(button)
        row.addStretch()
        box.addLayout(row)
        layout.addWidget(engine)
        layout.addWidget(label("Orvilo 1.1.0  ·  Runs on your computer. No telemetry. No Orvilo account.\nDownload only content you own or have permission to save. DRM-protected streams are not supported.", "caption", True))
        layout.addStretch()

    def setup_runtime(self) -> None:
        """Install missing media tools without losing the saved runtime location."""
        if ensure_runtime(self, self.settings):
            self.fields["ffmpeg_path"].setText(self.settings.get("ffmpeg_path", ""))
            self.notice.emit("FFmpeg is ready to use.")

    def line(self, key: str) -> QLineEdit:
        """Create an editor initialized from a string preference."""
        editor = QLineEdit(str(self.settings.get(key, "")))
        self.fields[key] = editor
        return editor

    def checkbox(self, key: str, text: str) -> QCheckBox:
        """Create a persisted boolean control."""
        editor = QCheckBox(text)
        editor.setChecked(bool(self.settings.get(key)))
        self.fields[key] = editor
        return editor

    def spin(self, key: str, minimum: int, maximum: int) -> QSpinBox:
        """Create a bounded integer preference."""
        editor = QSpinBox()
        editor.setRange(minimum, maximum)
        editor.setValue(int(self.settings.get(key, minimum)))
        self.fields[key] = editor
        return editor

    def combo(self, key: str, values: tuple[tuple[str, str], ...]) -> QComboBox:
        """Create a choice editor whose labels are separate from stored values."""
        editor = QComboBox()
        for text, value in values:
            editor.addItem(text, value)
        editor.setCurrentIndex(max(0, editor.findData(self.settings.get(key))))
        self.fields[key] = editor
        return editor

    def path_field(self, key: str, caption: str, directory: bool) -> QWidget:
        """Create a path field with a Windows folder or file chooser."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        editor = self.line(key)
        row.addWidget(editor, 1)
        browse = Button("Browse", "folder", "ghost")
        row.addWidget(browse)

        def select() -> None:
            value = QFileDialog.getExistingDirectory(self, caption, editor.text()) if directory else QFileDialog.getOpenFileName(self, caption, editor.text())[0]
            if value:
                editor.setText(value)

        browse.clicked.connect(select)
        return field_row(caption, container)

    def choose_accent(self) -> None:
        """Choose a color without committing unsaved preferences."""
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self.accent), self, "Choose an accent color")
        if color.isValid():
            self.accent = color.name()
            self.accent_button.setText(self.accent)

    def save(self) -> None:
        """Atomically save valid preferences, then notify the window."""
        values: dict[str, Any] = {"accent": self.accent}
        for key, editor in self.fields.items():
            if isinstance(editor, QLineEdit):
                values[key] = editor.text().strip()
            elif isinstance(editor, QCheckBox):
                values[key] = editor.isChecked()
            elif isinstance(editor, QComboBox):
                values[key] = editor.currentData()
            elif isinstance(editor, QSpinBox):
                values[key] = editor.value()
        try:
            self.settings.update(values)
            self.queue.set_parallel(values["parallel_downloads"])
            self.saved.emit()
            self.notice.emit("Settings saved. New downloads use these preferences.")
        except Exception as error:
            self.notice.emit(friendly_error(error))

    def update_engine(self) -> None:
        """Check and stage a verified engine update on a worker thread."""
        self.update_button.setEnabled(False)
        self.update_status.setText("Checking the latest engine release…")
        self.tasks.start(update_engine, self.update_status.setText, self.update_status.setText,
                         lambda: self.update_button.setEnabled(True))

    def open_folder(self, path: Any) -> None:
        """Open a local support folder, creating it on first use."""
        try:
            path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except OSError as error:
            self.notice.emit(friendly_error(error))
