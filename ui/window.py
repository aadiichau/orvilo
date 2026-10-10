"""Frameless Windows shell, navigation, tray integration and clean shutdown."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from typing import Any

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QCursor, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout,
    QLabel, QMainWindow, QMenu, QMessageBox, QStackedWidget, QSystemTrayIcon,
    QToolButton, QVBoxLayout, QWidget,
)

from core.models import Job
from ui.history_page import HistoryPage
from ui.home import HomePage
from ui.queue_page import QueuePage
from ui.settings_page import SettingsPage
from ui.runtime_dialog import RuntimeDialog, ensure_runtime
from ui.theme import apply_theme, colors
from ui.widgets import Button, TaskRunner, icon, label
from utils.formatting import extract_urls
from utils.paths import asset_path


class TitleBar(QWidget):
    """Native drag/maximize behavior with compact custom window controls."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self.window = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(48)
        row = QHBoxLayout(self)
        row.setContentsMargins(18, 0, 8, 0)
        logo = QLabel()
        logo.setPixmap(QIcon(str(asset_path("logo.svg"))).pixmap(24, 24))
        row.addWidget(logo)
        name = label("Orvilo", "section")
        row.addWidget(name)
        row.addSpacing(15)
        row.addWidget(label("VIDEO, SAVED BEAUTIFULLY", "caption"))
        row.addStretch()
        for name, description, callback in (("minus", "Minimize", window.showMinimized),
                                             ("square", "Maximize or restore", self.toggle_maximized),
                                             ("x", "Close", window.close)):
            button = QToolButton()
            button.setIcon(icon(name))
            button.setFixedSize(37, 32)
            button.setAccessibleName(description)
            button.setToolTip(description)
            button.setProperty("role", "close" if name == "x" else "ghost")
            button.clicked.connect(callback)
            row.addWidget(button)

    def toggle_maximized(self) -> None:
        """Toggle the native maximized window state."""
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Use Windows' system move to preserve snapping and desktop behavior."""
        if event.button() == Qt.MouseButton.LeftButton and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double-click the title area to maximize or restore."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()


class MainWindow(QMainWindow):
    """Compose the four app pages without doing network work on the UI thread."""

    def __init__(self, settings: Any, history: Any, queue: Any) -> None:
        super().__init__()
        self.settings, self.history, self.queue = settings, history, queue
        self._quitting = False
        self._ready_to_close = False
        self.setWindowTitle("Orvilo")
        self.setWindowIcon(QIcon(str(asset_path("logo.ico"))))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(940, 680)
        self.resize(1160, 820)
        self.setAcceptDrops(True)
        self.tasks = TaskRunner(self)
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(10, 10, 10, 10)
        self.shell = QFrame()
        self.shell.setObjectName("WindowShell")
        wrapper_layout.addWidget(self.shell)
        self.setCentralWidget(wrapper)
        layout = QVBoxLayout(self.shell)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)
        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(176)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 24, 14, 22)
        side.setSpacing(7)
        side.addWidget(label("WORKSPACE", "caption"))
        side.addSpacing(9)
        self.nav: list[Button] = []
        self.stack = QStackedWidget()
        for index, (title, glyph) in enumerate((("Download", "download"), ("Queue", "list"), ("History", "history"), ("Settings", "settings"))):
            button = Button(title, glyph, "nav")
            button.setCheckable(True)
            button.setMinimumHeight(43)
            button.clicked.connect(lambda _checked=False, page=index: self.navigate(page))
            side.addWidget(button)
            self.nav.append(button)
        side.addStretch()
        side.addWidget(label("Made for keeping.", "caption"))
        side.addWidget(label("Orvilo 1.1.0", "caption"))
        body.addWidget(sidebar)
        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self.notice_label = label("", "muted", True)
        self.notice_label.setContentsMargins(28, 12, 28, 10)
        self.notice_label.hide()
        content.addWidget(self.notice_label)
        content.addWidget(self.stack, 1)
        body.addWidget(main, 1)
        layout.addLayout(body, 1)
        self.home = HomePage(settings, queue, self.tasks)
        self.queue_page = QueuePage(queue)
        self.history_page = HistoryPage(history, settings, queue)
        self.settings_page = SettingsPage(settings, queue, self.tasks)
        for page in (self.home, self.queue_page, self.history_page, self.settings_page):
            self.stack.addWidget(page)
        self.home.enqueued.connect(lambda _count: self.navigate(1))
        for source in (self.home, self.history_page, self.settings_page, queue):
            source.notice.connect(self.show_notice)
        self.settings_page.saved.connect(self.apply_settings)
        self.notice_timer = QTimer(self)
        self.notice_timer.setSingleShot(True)
        self.notice_timer.setInterval(9000)
        self.notice_timer.timeout.connect(self.notice_label.hide)
        self.fade = QGraphicsOpacityEffect(self.stack)
        self.stack.setGraphicsEffect(self.fade)
        self.animation = QPropertyAnimation(self.fade, b"opacity", self)
        self.animation.setDuration(170)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Orvilo — your local video library")
        menu = QMenu(self)
        menu.addAction("Open Orvilo", self.reveal)
        menu.addSeparator()
        menu.addAction("Quit Orvilo", self.request_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        queue.completed.connect(self.download_finished)
        QApplication.clipboard().dataChanged.connect(self.clipboard_changed)
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setInterval(150)
        self.shutdown_timer.timeout.connect(self._finish_shutdown)
        self.apply_settings()
        self.navigate(0, animate=False)
        if settings.get("first_run", True):
            QTimer.singleShot(200, self.first_run)
        elif os.environ.get("ORVILO_SKIP_RUNTIME_SETUP") != "1":
            QTimer.singleShot(200, self.prepare_runtime)

    def apply_settings(self) -> None:
        """Apply theme changes immediately after successful persistence."""
        app = QApplication.instance()
        if app:
            apply_theme(app, self.settings.get("theme"), self.settings.get("accent"))
        self.clipboard_changed()

    def first_run(self) -> None:
        """Show the one-time permission notice requested by the product brief."""
        QMessageBox.information(self, "Welcome to Orvilo", "Download only content you own or have permission to save.")
        try:
            self.settings.update({"first_run": False})
        except OSError:
            self.show_notice("The welcome preference could not be saved. Check free disk space.")
        self.prepare_runtime()

    def prepare_runtime(self) -> None:
        """Offer the verified media-tool setup once the main window is ready."""
        if self._quitting or os.environ.get("ORVILO_SKIP_RUNTIME_SETUP") == "1":
            return
        if ensure_runtime(self, self.settings):
            self.settings_page.fields["ffmpeg_path"].setText(self.settings.get("ffmpeg_path", ""))
        elif not self._quitting:
            self.show_notice("Install FFmpeg in Settings when you're ready to download.")

    def navigate(self, index: int, animate: bool = True) -> None:
        """Select a page, refreshing history when it becomes visible."""
        self.stack.setCurrentIndex(index)
        for current, button in enumerate(self.nav):
            button.setChecked(index == current)
        if index == 2:
            self.history_page.refresh()
        if animate:
            self.animation.stop()
            self.animation.setStartValue(0.35)
            self.animation.setEndValue(1.0)
            self.animation.start()
        else:
            self.fade.setOpacity(1)

    def show_notice(self, text: str) -> None:
        """Display a quiet, temporary status message above the active page."""
        self.notice_label.setText(text)
        self.notice_label.setVisible(bool(text))
        self.notice_timer.start()

    def clipboard_changed(self) -> None:
        """Offer a detected link only while the setting is enabled."""
        if hasattr(self, "home"):
            self.home.offer_clipboard(QApplication.clipboard().text() if self.settings.get("clipboard_detection") else "")

    def dragEnterEvent(self, event: Any) -> None:
        """Accept browser URL drags and plain-text HTTP links."""
        mime = event.mimeData()
        text = "\n".join(url.toString() for url in mime.urls()) if mime.hasUrls() else mime.text()
        if extract_urls(text):
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        """Paste dropped links into the home page and start metadata loading."""
        mime = event.mimeData()
        text = "\n".join(url.toString() for url in mime.urls()) if mime.hasUrls() else mime.text()
        self.navigate(0)
        self.home.set_links(text)
        event.acceptProposedAction()

    def reveal(self) -> None:
        """Bring a minimized or hidden app back to the foreground."""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.reveal()

    def download_finished(self, job: Job) -> None:
        """Notify through Windows' system tray after a verified successful save."""
        if self.tray.isVisible():
            self.tray.showMessage("Download complete", job.title, QSystemTrayIcon.MessageIcon.Information, 6000)

    def changeEvent(self, event: QEvent) -> None:
        """Honor minimize-to-tray without hiding a window that has no tray icon."""
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and self.settings.get("minimize_to_tray") and self.tray.isVisible():
            QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Keep working in the tray or wait safely for running workers to exit."""
        if self._ready_to_close:
            event.accept()
            return
        event.ignore()
        if not self._quitting and self.settings.get("minimize_to_tray") and self.tray.isVisible():
            self.hide()
            return
        self.request_quit()

    def request_quit(self) -> None:
        """Stop scheduling and begin nonblocking cooperative shutdown."""
        if self._quitting:
            return
        self._quitting = True
        for dialog in self.findChildren(RuntimeDialog):
            dialog.reject()
        self.reveal()
        self.home.cancel_pending()
        self.queue.shutdown()
        self.show_notice("Closing safely… waiting for current network or FFmpeg steps to finish.")
        self.stack.setEnabled(False)
        self.shutdown_timer.start()
        self._finish_shutdown()

    def _finish_shutdown(self) -> None:
        if self.queue.is_idle() and self.tasks.is_idle() and not any(worker.isRunning() for worker in self.findChildren(QThread)):
            self.shutdown_timer.stop()
            self.tray.hide()
            self._ready_to_close = True
            self.close()
            QApplication.quit()

    def nativeEvent(self, event_type: Any, message: Any) -> tuple[bool, int]:
        """Return Windows edge hit-tests for native frameless resizing."""
        if os.name == "nt" and not self.isMaximized():
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                point = self.mapFromGlobal(QCursor.pos())
                left, right = point.x() < 7, point.x() >= self.width() - 7
                top, bottom = point.y() < 7, point.y() >= self.height() - 7
                if top and left: return True, 13
                if top and right: return True, 14
                if bottom and left: return True, 16
                if bottom and right: return True, 17
                if left: return True, 10
                if right: return True, 11
                if top: return True, 12
                if bottom: return True, 15
        return super().nativeEvent(event_type, message)

    def paintEvent(self, event: Any) -> None:
        """Draw a soft outer shadow without nesting Qt graphics effects."""
        from PySide6.QtGui import QPainter, QPen
        from PySide6.QtCore import QRectF
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for spread in range(1, 9):
            painter.setPen(QPen(QColor(0, 0, 0, max(2, 24 - spread * 3)), 1))
            painter.drawRoundedRect(QRectF(10 - spread, 12 - spread, self.width() - 20 + spread * 2,
                                           self.height() - 22 + spread * 2), 14 + spread, 14 + spread)
