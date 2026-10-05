"""Small reusable widgets and safe background-task primitives."""
from __future__ import annotations

from collections.abc import Callable
import logging
import hashlib
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QByteArray, QEasingCurve, QObject, QPointF, Property, QPropertyAnimation,
    QRectF, QRunnable, QSize, Qt, QThreadPool, QUrl, Signal, Slot,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from utils.errors import friendly_error
from utils.paths import asset_path, data_dir

logger = logging.getLogger(__name__)
_icons: dict[tuple[str, str], QIcon] = {}


def icon(name: str, color: str = "#AAA7BF") -> QIcon:
    """Render bundled monochrome SVG icons at high-DPI sizes."""
    key = (name, color)
    if key in _icons:
        return _icons[key]
    result = QIcon()
    try:
        source = Path(asset_path(f"icons/{name}.svg")).read_text(encoding="utf-8")
        source = source.replace("currentColor", color).replace("#000000", color).replace('stroke="black"', f'stroke="{color}"')
        renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
        for scale in (1, 2, 3):
            pixmap = QPixmap(20 * scale, 20 * scale)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(scale)
            result.addPixmap(pixmap)
    except (OSError, RuntimeError):
        logger.exception("Unable to render icon %s", name)
    _icons[key] = result
    return result


def label(text: str, role: str = "", wrap: bool = False) -> QLabel:
    """Create a themed label whose remote titles cannot be interpreted as HTML."""
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setProperty("role", role)
    widget.setWordWrap(wrap)
    return widget


class Button(QPushButton):
    """A keyboard-accessible button with a subtle animated hover wash."""

    def __init__(self, text: str = "", icon_name: str = "", role: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = 0.0
        self._animation = QPropertyAnimation(self, b"hoverAmount", self)
        self._animation.setDuration(140)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        if icon_name:
            self.setIcon(icon(icon_name))
            self.setIconSize(QSize(18, 18))
        if role:
            self.setProperty("role", role)
        if role == "primary":
            self.setMinimumHeight(44)

    def get_hover(self) -> float:
        """Return the current hover interpolation."""
        return self._hover

    def set_hover(self, value: float) -> None:
        """Update the hover overlay and schedule a repaint."""
        self._hover = value
        self.update()

    hoverAmount = Property(float, get_hover, set_hover)

    def enterEvent(self, event: Any) -> None:
        """Animate entry without affecting keyboard focus."""
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: Any) -> None:
        """Fade the hover state out."""
        self._animate(0.0)
        super().leaveEvent(event)

    def _animate(self, target: float) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(target)
        self._animation.start()

    def paintEvent(self, event: Any) -> None:
        """Paint the normal Qt control followed by a quiet hover highlight."""
        super().paintEvent(event)
        if self._hover and self.isEnabled():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, int(9 * self._hover)))
            radius = 20 if self.property("role") == "primary" else 9
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), radius, radius)


def card() -> tuple[QFrame, QVBoxLayout]:
    """Create a standard spacious surface container."""
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 20, 22, 20)
    layout.setSpacing(14)
    return frame, layout


def scroll_page() -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    """Create a responsive page with a single vertical scrolling surface."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(34, 28, 34, 30)
    layout.setSpacing(22)
    scroll.setWidget(content)
    return scroll, content, layout


def field_row(caption: str, widget: QWidget, description: str = "") -> QWidget:
    """Place a field label above its editor, with an optional concise hint."""
    result = QWidget()
    layout = QVBoxLayout(result)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(7)
    layout.addWidget(label(caption, "muted"))
    layout.addWidget(widget)
    if description:
        layout.addWidget(label(description, "caption", True))
    return result


class _TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    done = Signal()


class _Task(QRunnable):
    def __init__(self, operation: Callable[[], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.signals = _TaskSignals()

    @Slot()
    def run(self) -> None:
        """Run a task while routing safe text errors to the GUI thread."""
        try:
            self.signals.result.emit(self.operation())
        except Exception as exc:
            logger.exception("Background task failed")
            self.signals.error.emit(friendly_error(exc))
        finally:
            self.signals.done.emit()


class TaskRunner(QObject):
    """Keep asynchronous jobs alive until their signal handlers have run."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self._tasks: set[_Task] = set()

    def start(self, operation: Callable[[], Any], success: Callable[[Any], None], error: Callable[[str], None], done: Callable[[], None] | None = None) -> None:
        """Execute a blocking operation without blocking the application."""
        task = _Task(operation)
        self._tasks.add(task)
        task.signals.result.connect(success, Qt.ConnectionType.QueuedConnection)
        task.signals.error.connect(error, Qt.ConnectionType.QueuedConnection)
        task.signals.done.connect(lambda: self._finish(task, done), Qt.ConnectionType.QueuedConnection)
        self.pool.start(task)

    def _finish(self, task: _Task, done: Callable[[], None] | None) -> None:
        self._tasks.discard(task)
        if done:
            done()

    def is_idle(self) -> bool:
        """Return whether all tasks and their GUI callbacks have completed."""
        return not self._tasks and self.pool.activeThreadCount() == 0


class Thumbnail(QLabel):
    """A bounded asynchronous thumbnail loader with aspect-fill rendering."""

    def __init__(self, width: int = 188, height: int = 106, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName("Video thumbnail")
        self.network = QNetworkAccessManager(self)
        self.reply: QNetworkReply | None = None
        self.source = QPixmap()
        self._url = ""
        self.setText("▶")

    def load(self, url: str) -> None:
        """Load an HTTP thumbnail, cancelling an obsolete image request."""
        if url == self._url:
            return
        self._url = url
        if self.reply:
            self.reply.abort()
        self.source = QPixmap()
        self.setText("▶")
        cached = data_dir() / "thumbnails" / (hashlib.sha256(url.encode()).hexdigest() + ".img")
        if url and cached.is_file() and self.source.load(str(cached)):
            self.setText("")
            self.update()
            return
        if not url or QUrl(url).scheme() not in ("https", "http"):
            self.update()
            return
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(15000)
        reply = self.network.get(request)
        self.reply = reply
        reply.setReadBufferSize(8 * 1024 * 1024)
        reply.downloadProgress.connect(lambda received, total: reply.abort() if received > 8 * 1024 * 1024 or total > 8 * 1024 * 1024 else None)
        reply.finished.connect(lambda: self._received(reply, url))

    def _received(self, reply: QNetworkReply, url: str) -> None:
        if reply.error() == QNetworkReply.NetworkError.NoError and url == self._url:
            raw = reply.readAll()
            if len(raw) <= 8 * 1024 * 1024:
                self.source.loadFromData(raw)
                if not self.source.isNull():
                    self.setText("")
                    try:
                        cached = data_dir() / "thumbnails" / (hashlib.sha256(url.encode()).hexdigest() + ".img")
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        cached.write_bytes(bytes(raw))
                    except OSError:
                        logger.warning("Thumbnail could not be cached")
        if self.reply is reply:
            self.reply = None
        reply.deleteLater()
        self.update()

    def paintEvent(self, event: Any) -> None:
        """Draw a rounded crop without stretching the original image."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(bounds, 10, 10)
        painter.setClipPath(path)
        painter.fillRect(bounds, QColor("#242232"))
        if not self.source.isNull():
            scaled = self.source.scaled(self.size() * self.devicePixelRatioF(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(self.devicePixelRatioF())
            offset = QPointF((self.width() - scaled.width() / scaled.devicePixelRatio()) / 2, (self.height() - scaled.height() / scaled.devicePixelRatio()) / 2)
            painter.drawPixmap(offset, scaled)
        else:
            painter.setPen(QColor("#8E84BA"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▶")


class EmptyArt(QWidget):
    """A small geometric download illustration drawn crisply at any scale."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(170, 114)
        self.accent = QColor("#7C5CFF")

    def paintEvent(self, event: Any) -> None:
        """Paint floating media tiles and a download arrow."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        soft = QColor(self.accent)
        soft.setAlpha(18)
        p.setBrush(soft)
        p.drawEllipse(QRectF(25, 6, 120, 100))
        p.save()
        p.translate(61, 45)
        p.rotate(-12)
        soft.setAlpha(34)
        p.setBrush(soft)
        p.setPen(QPen(QColor("#6E648F"), 1.3))
        p.drawRoundedRect(QRectF(-28, -21, 57, 44), 7, 7)
        p.restore()
        soft.setAlpha(45)
        p.setBrush(soft)
        p.setPen(QPen(self.accent, 1.8))
        p.drawRoundedRect(QRectF(66, 32, 59, 45), 8, 8)
        p.setBrush(self.accent)
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath(QPointF(90, 45))
        path.lineTo(90, 63)
        path.lineTo(104, 54)
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(QPen(self.accent, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(85, 82, 85, 99)
        p.drawLine(78, 92, 85, 99)
        p.drawLine(92, 92, 85, 99)
        p.setPen(QPen(QColor("#777088"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(34, 83, 40, 83)
        p.drawLine(135, 28, 140, 28)
        p.drawLine(137, 25, 137, 31)


class EmptyState(QWidget):
    """A calm first-use state with concise guidance."""

    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 26, 20, 26)
        layout.setSpacing(9)
        layout.addWidget(EmptyArt(), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(label(title, "section"), 0, Qt.AlignmentFlag.AlignHCenter)
        text = label(description, "muted", True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setMaximumWidth(460)
        layout.addWidget(text, 0, Qt.AlignmentFlag.AlignHCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
