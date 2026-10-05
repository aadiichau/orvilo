"""Searchable local library with safe file and record actions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QHeaderView, QHBoxLayout,
    QLineEdit, QMenu, QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from core.models import DownloadOptions
from ui.widgets import Button, EmptyState, Thumbnail, label, scroll_page
from utils.errors import friendly_error
from utils.formatting import human_bytes


class HistoryPage(QWidget):
    """Display completed files and keep destructive actions explicit."""

    notice = Signal(str)

    def __init__(self, history: Any, settings: Any, queue: Any) -> None:
        super().__init__()
        self.history, self.settings, self.queue = history, settings, queue
        self.records: list[dict[str, Any]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _, layout = scroll_page()
        root.addWidget(scroll)
        heading = QHBoxLayout()
        heading.addWidget(label("Your library", "heading"), 1)
        clear = Button("Clear history", "trash", "ghost")
        clear.clicked.connect(self.clear_history)
        heading.addWidget(clear)
        layout.addLayout(heading)
        layout.addWidget(label("Everything you've saved, right where you left it.", "muted"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by title or link…")
        self.search.setAccessibleName("Search download history")
        layout.addWidget(self.search)
        filters = QHBoxLayout()
        self.site = QComboBox()
        self.site.addItem("All sites", "")
        self.date = QComboBox()
        for title, days in (("All dates", 0), ("Last 24 hours", 1), ("Last 7 days", 7), ("Last 30 days", 30), ("Last year", 365)):
            self.date.addItem(title, days)
        self.kind = QComboBox()
        for title, value in (("All types", ""), ("Video", "video"), ("Audio", "audio")):
            self.kind.addItem(title, value)
        self.sort = QComboBox()
        for title, value in (("Newest first", "newest"), ("Oldest first", "oldest"), ("Title A–Z", "title"), ("Largest first", "size")):
            self.sort.addItem(title, value)
        for editor in (self.site, self.date, self.kind, self.sort):
            filters.addWidget(editor, 1)
            editor.currentIndexChanged.connect(self.refresh)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "TITLE", "FORMAT", "SAVED", "SIZE"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(330)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for index, width in ((0, 84), (2, 82), (3, 102), (4, 78)):
            self.table.setColumnWidth(index, width)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.menu)
        self.table.cellDoubleClicked.connect(lambda row, _column: self.open_file(row))
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        for text, glyph, operation in (("Open", "play", self.open_file), ("Show in folder", "folder", self.show_folder),
                                       ("Copy link", "copy", self.copy_link), ("Re-download", "refresh", self.redownload),
                                       ("Delete", "trash", self.delete_selected)):
            button = Button(text, glyph, "ghost")
            button.clicked.connect(lambda _checked=False, action=operation: action(self.table.currentRow()))
            actions.addWidget(button)
        layout.addLayout(actions)
        self.empty = EmptyState("Your favorites, within reach.", "Completed downloads appear here with their original link and saved file.")
        layout.addWidget(self.empty)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.timer.start())
        queue.completed.connect(lambda _job: self.refresh())
        self.refresh()

    def refresh(self, *_: Any) -> None:
        """Search/filter SQLite and mark missing files on each visit."""
        try:
            current = self.site.currentData()
            self.site.blockSignals(True)
            self.site.clear()
            self.site.addItem("All sites", "")
            for site in self.history.sites():
                self.site.addItem(site, site)
            self.site.setCurrentIndex(max(0, self.site.findData(current)))
            self.site.blockSignals(False)
            days = self.date.currentData() or 0
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days else ""
            self.records = self.history.search(self.search.text(), self.site.currentData() or "", since,
                                               self.kind.currentData() or "", self.sort.currentData() or "newest")
            self.table.setRowCount(len(self.records))
            for row, item in enumerate(self.records):
                self.table.setRowHeight(row, 67)
                thumbnail = Thumbnail(72, 44)
                thumbnail.load(item["thumbnail"])
                self.table.setCellWidget(row, 0, thumbnail)
                title = item["title"] + ("\nMissing file" if item["missing"] else "\n" + item["site"])
                date = datetime.fromisoformat(item["downloaded_at"]).astimezone().strftime("%d %b %Y")
                for column, text in enumerate((title, item["quality"], date, human_bytes(item["file_size"])), start=1):
                    cell = QTableWidgetItem(text)
                    cell.setToolTip(item["file_path"])
                    self.table.setItem(row, column, cell)
            self.empty.setVisible(not self.records)
            self.table.setVisible(bool(self.records))
        except Exception as error:
            self.notice.emit(friendly_error(error))

    def _record(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self.records):
            return self.records[row]
        self.notice.emit("Select a library item first.")
        return None

    def open_file(self, row: int) -> None:
        """Open a present media file using the Windows default player."""
        if item := self._record(row):
            if not Path(item["file_path"]).is_file():
                self.notice.emit("This file has moved or was deleted. You can re-download it.")
                self.refresh()
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(item["file_path"])):
                self.notice.emit("Windows could not open this file. Choose a default media player.")

    def show_folder(self, row: int) -> None:
        """Reveal the selected file in Explorer with safe argument passing."""
        if item := self._record(row):
            path = Path(item["file_path"])
            try:
                if os.name == "nt" and path.is_file():
                    subprocess.Popen(["explorer.exe", "/select,", str(path)])
                else:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
            except OSError as error:
                self.notice.emit(friendly_error(error))

    def copy_link(self, row: int) -> None:
        """Copy the original URL for reuse."""
        if item := self._record(row):
            QApplication.clipboard().setText(item["url"])
            self.notice.emit("Link copied.")

    def redownload(self, row: int) -> None:
        """Requeue a record using its format and current network preferences."""
        if item := self._record(row):
            try:
                options = DownloadOptions.from_dict(item["options"])
                current = self.settings.download_options()
                for key in ("browser", "browser_profile", "cookie_file", "proxy", "ffmpeg_path", "js_runtime_path", "speed_limit_kib"):
                    setattr(options, key, getattr(current, key))
                options.folder = current.folder
                self.queue.enqueue(item["url"], options)
                self.notice.emit("Added to your queue.")
            except Exception as error:
                self.notice.emit(friendly_error(error))

    def delete_selected(self, row: int) -> None:
        """Confirm removal with an optional, unchecked file-deletion choice."""
        if item := self._record(row):
            dialog = QMessageBox(QMessageBox.Icon.Question, "Remove download?", "Remove this item from your library?", parent=self)
            check = QCheckBox("Also delete the saved media file")
            dialog.setCheckBox(check)
            dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
            if dialog.exec() == QMessageBox.StandardButton.Yes:
                try:
                    self.history.delete(item["id"], check.isChecked())
                    self.refresh()
                except Exception as error:
                    self.notice.emit(friendly_error(error))

    def clear_history(self) -> None:
        """Confirm clearing records while preserving downloaded files."""
        if QMessageBox.question(self, "Clear all history?", "Remove all library records? Your downloaded files will be kept.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            try:
                self.history.clear()
                self.refresh()
            except Exception as error:
                self.notice.emit(friendly_error(error))

    def menu(self, position: Any) -> None:
        """Expose the same actions from a row's context menu."""
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        self.table.selectRow(row)
        menu = QMenu(self)
        for text, action in (("Open file", self.open_file), ("Show in folder", self.show_folder), ("Copy link", self.copy_link),
                             ("Re-download", self.redownload), ("Delete…", self.delete_selected)):
            menu.addAction(text, lambda _checked=False, operation=action: operation(row))
        menu.exec(self.table.viewport().mapToGlobal(position))
