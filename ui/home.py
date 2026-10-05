"""Link entry, asynchronous previews and per-download choices."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from core.downloader import Control, probe
from core.models import DownloadOptions, MediaInfo
from utils.errors import friendly_error
from utils.formatting import duration_text, extract_urls, parse_time
from ui.widgets import Button, EmptyState, TaskRunner, Thumbnail, card, field_row, label, scroll_page


class HomePage(QWidget):
    """Prepare a single video, a collection, or many links for the queue."""

    notice = Signal(str)
    enqueued = Signal(int)

    def __init__(self, settings: Any, queue: Any, tasks: TaskRunner, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings, self.queue, self.tasks = settings, queue, tasks
        self._generation = 0
        self._control: Control | None = None
        self._controls: list[Control] = []
        self._media: list[MediaInfo] = []
        self._preview_urls: list[str] = []
        self._busy = False
        self._clipboard_link = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, content, page = scroll_page()
        outer.addWidget(scroll)
        page.addWidget(label("YOUR NEXT GREAT FIND", "eyebrow"))
        heading = QVBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(label("A link. A little possibility.", "hero"))
        heading.addWidget(label("Keep the videos and sounds that matter to you.", "muted"))
        page.addLayout(heading)

        self.clipboard_card, clipboard_layout = card()
        self.clipboard_card.setObjectName("Notice")
        clipboard_layout.setContentsMargins(14, 10, 14, 10)
        clipboard_row = QHBoxLayout()
        clipboard_row.addWidget(label("A video link is ready on your clipboard.", "muted"), 1)
        use_link = Button("Use link", "link", "ghost")
        use_link.clicked.connect(lambda: self.set_links(self._clipboard_link))
        clipboard_row.addWidget(use_link)
        clipboard_layout.addLayout(clipboard_row)
        self.clipboard_card.hide()
        page.addWidget(self.clipboard_card)

        input_card, input_layout = card()
        self.link_input = QPlainTextEdit()
        self.link_input.setObjectName("LinkInput")
        self.link_input.setPlaceholderText("Paste a video, playlist or profile link…")
        self.link_input.setAccessibleName("Video links, one per line")
        self.link_input.setFixedHeight(88)
        self.link_input.setTabChangesFocus(True)
        input_layout.addWidget(self.link_input)
        input_row = QHBoxLayout()
        paste = Button("Paste link", "link", "ghost")
        paste.clicked.connect(lambda: self.set_links(QApplication.clipboard().text()))
        input_row.addWidget(paste)
        batch_hint = label("or drop a link · multiple links welcome", "caption")
        batch_hint.setWordWrap(True)
        input_row.addWidget(batch_hint, 1)
        self.download_button = Button("Download", "arrow-down", "primary")
        self.download_button.setMinimumWidth(148)
        self.download_button.clicked.connect(self.download_selected)
        input_row.addWidget(self.download_button)
        input_layout.addLayout(input_row)
        self.status = label("", "muted", True)
        self.status.hide()
        input_layout.addWidget(self.status)
        page.addWidget(input_card)

        self.preview_card, preview_layout = card()
        preview_row = QHBoxLayout()
        preview_row.setSpacing(18)
        self.thumbnail = Thumbnail()
        preview_row.addWidget(self.thumbnail, 0, Qt.AlignmentFlag.AlignTop)
        preview_text = QVBoxLayout()
        preview_text.setSpacing(7)
        self.preview_site = label("", "eyebrow")
        self.preview_title = label("", "section", True)
        self.preview_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.preview_detail = label("", "muted", True)
        self.preview_qualities = label("", "caption", True)
        preview_text.addWidget(self.preview_site)
        preview_text.addWidget(self.preview_title)
        preview_text.addWidget(self.preview_detail)
        preview_text.addWidget(self.preview_qualities)
        preview_text.addStretch()
        preview_row.addLayout(preview_text, 1)
        preview_layout.addLayout(preview_row)
        self.selection_header = QWidget()
        select_row = QHBoxLayout(self.selection_header)
        select_row.setContentsMargins(0, 0, 0, 0)
        self.selection_count = label("", "muted")
        select_row.addWidget(self.selection_count, 1)
        select_all = Button("Select all", role="ghost")
        select_all.clicked.connect(lambda: self._select_all(True))
        select_none = Button("None", role="ghost")
        select_none.clicked.connect(lambda: self._select_all(False))
        select_row.addWidget(select_all)
        select_row.addWidget(select_none)
        preview_layout.addWidget(self.selection_header)
        self.entries = QListWidget()
        self.entries.setAccessibleName("Choose videos to download")
        self.entries.setMinimumHeight(180)
        self.entries.setMaximumHeight(320)
        self.entries.itemChanged.connect(self._selection_changed)
        preview_layout.addWidget(self.entries)
        self.preview_card.hide()
        page.addWidget(self.preview_card)

        options_card, options_layout = card()
        choice_row = QHBoxLayout()
        choice_row.setSpacing(14)
        self.kind = QComboBox()
        self.kind.addItem("Video", "video")
        self.kind.addItem("Audio only", "audio")
        self.quality = QComboBox()
        self.quality.addItems(["Best", "4K", "1440p", "1080p", "720p", "480p"])
        self.audio_format = QComboBox()
        for value in ("MP3", "M4A", "FLAC", "WAV", "Opus"):
            self.audio_format.addItem(value, value.lower())
        self.audio_field = field_row("Audio format", self.audio_format)
        self.quality_field = field_row("Quality", self.quality)
        choice_row.addWidget(field_row("Save as", self.kind), 1)
        choice_row.addWidget(self.quality_field, 1)
        choice_row.addWidget(self.audio_field, 1)
        self.audio_field.hide()
        options_layout.addLayout(choice_row)
        self.format_hint = label("Video saved as MKV · original quality · best available up to your choice", "caption", True)
        options_layout.addWidget(self.format_hint)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        more = Button("More options", "plus", "ghost")
        more.setCheckable(True)
        more.setAccessibleName("Show clip, subtitle and artwork options")
        options_layout.addWidget(more, 0, Qt.AlignmentFlag.AlignLeft)
        self.advanced = QWidget()
        advanced_grid = QGridLayout(self.advanced)
        advanced_grid.setContentsMargins(0, 4, 0, 0)
        advanced_grid.setHorizontalSpacing(14)
        advanced_grid.setVerticalSpacing(14)
        self.clip_start = QLineEdit()
        self.clip_start.setPlaceholderText("00:00:00")
        self.clip_end = QLineEdit()
        self.clip_end.setPlaceholderText("Until the end")
        advanced_grid.addWidget(field_row("Clip start (optional)", self.clip_start), 0, 0)
        advanced_grid.addWidget(field_row("Clip end (optional)", self.clip_end), 0, 1)
        self.subtitles = QComboBox()
        self.subtitles.addItem("No subtitles", "none")
        self.subtitles.addItem("Save .srt file", "save")
        self.subtitles.addItem("Embed in video", "embed")
        self.subtitles.setCurrentIndex(max(0, self.subtitles.findData(settings.get("subtitles", "none"))))
        self.language = QLineEdit(settings.get("subtitle_language", "en"))
        self.language.setPlaceholderText("en,hi or all")
        advanced_grid.addWidget(field_row("Subtitles", self.subtitles), 1, 0)
        advanced_grid.addWidget(field_row("Subtitle languages", self.language), 1, 1)
        self.auto_subtitles = QCheckBox("Include automatic captions")
        self.auto_subtitles.setChecked(settings.get("auto_subtitles", False))
        self.save_thumbnail = QCheckBox("Save thumbnail")
        self.save_thumbnail.setChecked(settings.get("save_thumbnail", False))
        self.embed_metadata = QCheckBox("Embed title and metadata")
        self.embed_metadata.setChecked(settings.get("embed_metadata", True))
        self.embed_cover = QCheckBox("Embed cover artwork")
        self.embed_cover.setChecked(settings.get("embed_cover", False))
        advanced_grid.addWidget(self.auto_subtitles, 2, 0)
        advanced_grid.addWidget(self.save_thumbnail, 2, 1)
        advanced_grid.addWidget(self.embed_metadata, 3, 0)
        advanced_grid.addWidget(self.embed_cover, 3, 1)
        advanced_grid.addWidget(label("Precise clips may re-encode. Clips require an unlimited speed setting and cannot pause. Audio subtitles and WAV artwork are saved beside the file.", "caption", True), 4, 0, 1, 2)
        self.advanced.hide()
        more.toggled.connect(self.advanced.setVisible)
        more.toggled.connect(lambda opened: more.setText("Fewer options" if opened else "More options"))
        options_layout.addWidget(self.advanced)
        page.addWidget(options_card)
        self.empty = EmptyState("Good things, kept close.", "YouTube, Bilibili, Vimeo and hundreds more. Start with a link above.")
        page.addWidget(self.empty)
        page.addStretch()
        page.addWidget(label("LOCAL BY DESIGN     ·     No accounts. No telemetry. Just your library.", "caption"), 0, Qt.AlignmentFlag.AlignHCenter)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(750)
        self.timer.timeout.connect(self._begin_probe)
        self.link_input.textChanged.connect(self._text_changed)
        self._kind_changed()

    def set_links(self, text: str) -> None:
        """Accept a pasted or dropped group of links and begin a preview."""
        urls = extract_urls(text)
        if not urls:
            self._set_status("Paste a full http:// or https:// video link to get started.", True)
            return
        self.link_input.setPlainText("\n".join(urls))
        self.clipboard_card.hide()
        self.link_input.setFocus()

    def offer_clipboard(self, text: str) -> None:
        """Offer detected clipboard links without replacing a user's work."""
        urls = extract_urls(text)
        current = extract_urls(self.link_input.toPlainText())
        if self.settings.get("clipboard_detection", True) and urls and urls != current:
            self._clipboard_link = "\n".join(urls)
            self.clipboard_card.show()
        else:
            self.clipboard_card.hide()

    def _kind_changed(self) -> None:
        audio = self.kind.currentData() == "audio"
        self.audio_field.setVisible(audio)
        self.quality_field.setVisible(not audio)
        self.format_hint.setText("Audio conversion uses FFmpeg · lossless output does not restore lost source quality" if audio else "Video saved as MKV · original quality · best available up to your choice")

    def _text_changed(self) -> None:
        self._generation += 1
        if self._control:
            self._control.cancel()
        self._busy = False
        self._media = []
        self._preview_urls = []
        self.preview_card.hide()
        self.empty.show()
        self.download_button.setText("Download")
        self.download_button.setEnabled(True)
        self._set_status("")
        self.timer.start()

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setProperty("role", "error" if error else "muted")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setVisible(bool(text))

    def _options(self) -> DownloadOptions:
        options = self.settings.download_options()
        start_text, end_text = self.clip_start.text().strip(), self.clip_end.text().strip()
        start = parse_time(start_text) if start_text else None
        end = parse_time(end_text) if end_text else None
        if start is not None and start < 0:
            raise ValueError("Clip start must be zero or later.")
        if end is not None and end <= (start or 0):
            raise ValueError("Clip end must be later than the start.")
        return replace(options, kind=self.kind.currentData(), quality=self.quality.currentText(),
                       audio_format=self.audio_format.currentData(), clip_start=start, clip_end=end,
                       subtitles=self.subtitles.currentData(), subtitle_language=self.language.text().strip() or "en",
                       auto_subtitles=self.auto_subtitles.isChecked(), save_thumbnail=self.save_thumbnail.isChecked(),
                       embed_metadata=self.embed_metadata.isChecked(), embed_cover=self.embed_cover.isChecked())

    def _begin_probe(self, download_after: bool = False) -> None:
        urls = extract_urls(self.link_input.toPlainText())
        if not urls:
            if self.link_input.toPlainText().strip():
                self._set_status("That doesn't look like a video link. Use a complete http:// or https:// URL.", True)
            return
        if self._busy:
            return
        self.timer.stop()
        try:
            options = self.settings.download_options()
        except Exception as exc:
            self._set_status(friendly_error(exc), True)
            return
        generation = self._generation
        control = Control()
        self._control = control
        self._controls.append(control)
        self._busy = True
        self.download_button.setEnabled(False)
        self.download_button.setText("Reading…")
        self._set_status("Finding video details and available qualities…" if len(urls) == 1 else f"Reading {len(urls)} links and their collections…")

        def read_links() -> list[MediaInfo]:
            result = []
            for url in urls:
                control.checkpoint()
                result.append(probe(url, options, control=control))
            return result

        def success(media: list[MediaInfo]) -> None:
            if generation != self._generation:
                return
            self._media = media
            self._preview_urls = urls
            self._busy = False
            self.download_button.setEnabled(True)
            self._display_preview()
            if download_after and len(media) == 1 and not media[0].is_playlist:
                self.download_selected()

        def error(message: str) -> None:
            if generation != self._generation:
                return
            self._busy = False
            self.download_button.setEnabled(True)
            self.download_button.setText("Try again")
            self._set_status(message, True)

        def done() -> None:
            if control in self._controls:
                self._controls.remove(control)

        self.tasks.start(read_links, success, error, done)

    def _display_preview(self) -> None:
        if not self._media:
            return
        first = self._media[0]
        self.preview_title.setText(first.title)
        self.preview_site.setText((first.site or "VIDEO").upper())
        pieces = [first.uploader]
        if first.duration is not None:
            pieces.append(duration_text(first.duration))
        if len(self._media) > 1:
            pieces.append(f"{len(self._media)} links")
        self.preview_detail.setText(" · ".join(p for p in pieces if p))
        self.preview_qualities.setText("Available: " + " · ".join(f"{height}p" for height in sorted(set(first.qualities), reverse=True)) if first.qualities else "Best available format will be selected automatically.")
        self.thumbnail.load(first.thumbnail)
        collection = len(self._media) > 1 or first.is_playlist
        self.entries.blockSignals(True)
        self.entries.clear()
        for media in self._media:
            candidates = media.entries if media.is_playlist else [media]
            for item in candidates:
                if not item.url:
                    continue
                text = item.title
                subtitle = " · ".join(v for v in (item.uploader, duration_text(item.duration) if item.duration is not None else "") if v)
                if subtitle:
                    text += "\n" + subtitle
                row = QListWidgetItem(text)
                row.setFlags(row.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(Qt.CheckState.Checked)
                row.setData(Qt.ItemDataRole.UserRole, item)
                self.entries.addItem(row)
        self.entries.blockSignals(False)
        self.entries.setVisible(collection)
        self.selection_header.setVisible(collection)
        self.preview_card.show()
        self.empty.hide()
        self._selection_changed()
        if not self.entries.count():
            self._set_status("No downloadable videos were found in this collection. Try a direct video link or enable browser cookies in Settings.", True)
        elif collection:
            self._set_status("Choose the videos you'd like to keep, then download.")
        else:
            self._set_status("")

    def _select_all(self, checked: bool) -> None:
        self.entries.blockSignals(True)
        for index in range(self.entries.count()):
            self.entries.item(index).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.entries.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self, *_: Any) -> None:
        count = sum(self.entries.item(index).checkState() == Qt.CheckState.Checked for index in range(self.entries.count()))
        self.selection_count.setText(f"{count} of {self.entries.count()} selected")
        self.download_button.setText(f"Download {count}" if self.entries.count() > 1 else "Download")
        self.download_button.setEnabled(count > 0)

    def download_selected(self) -> None:
        """Queue checked items using a validated snapshot of current choices."""
        urls = extract_urls(self.link_input.toPlainText())
        if not urls:
            self._set_status("Paste a video link first.", True)
            self.link_input.setFocus()
            return
        if self._preview_urls != urls or not self._media:
            self._begin_probe(download_after=True)
            return
        try:
            options = self._options()
            selected = [self.entries.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.entries.count()) if self.entries.item(i).checkState() == Qt.CheckState.Checked]
            if not selected:
                self._set_status("Select at least one video to download.", True)
                return
            for media in selected:
                self.queue.enqueue(media.url, replace(options), preview=media)
            self._set_status(f"Added {len(selected)} {'download' if len(selected) == 1 else 'downloads'} to your queue.")
            self.enqueued.emit(len(selected))
        except Exception as exc:
            self._set_status(friendly_error(exc), True)

    def cancel_pending(self) -> None:
        """Cooperatively stop previews before application shutdown."""
        self.timer.stop()
        self._generation += 1
        for control in self._controls:
            control.cancel()
