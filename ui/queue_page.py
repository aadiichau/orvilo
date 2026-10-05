"""Live queue cards with animated progress and explicit processing states."""
from __future__ import annotations

from typing import Any
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtWidgets import QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from core.models import Job
from ui.widgets import Button, EmptyState, Thumbnail, card, label, scroll_page
from utils.formatting import duration_text, human_bytes


class JobCard(QWidget):
    """Render one queue item and its currently valid actions."""

    def __init__(self, job: Job, queue: Any) -> None:
        super().__init__()
        self.queue = queue
        self.job_id = job.id
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        surface, layout = card()
        root.addWidget(surface)
        row = QHBoxLayout()
        self.thumbnail = Thumbnail(104, 60)
        row.addWidget(self.thumbnail)
        text = QVBoxLayout()
        self.title = label("", "section", True)
        self.title.setMinimumWidth(0)
        text.addWidget(self.title)
        self.detail = label("", "caption", True)
        text.addWidget(self.detail)
        row.addLayout(text, 1)
        layout.addLayout(row)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.animation = QPropertyAnimation(self.progress, b"value", self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        bottom = QHBoxLayout()
        self.state = label("", "muted", True)
        bottom.addWidget(self.state, 1)
        self.pause = Button("Pause", "pause", "ghost")
        self.resume = Button("Resume", "play", "ghost")
        self.cancel = Button("Cancel", "x", "ghost")
        self.retry = Button("Retry", "refresh", "ghost")
        for button, method in ((self.pause, queue.pause), (self.resume, queue.resume),
                               (self.cancel, queue.cancel), (self.retry, queue.retry)):
            button.clicked.connect(lambda _checked=False, fn=method: fn(self.job_id))
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.update_job(job)

    def update_job(self, job: Job) -> None:
        """Update progress and action visibility without recreating the row."""
        self.title.setText(job.title)
        self.thumbnail.load(job.thumbnail)
        quality = job.options.audio_format.upper() if job.options.kind == "audio" else job.options.quality
        self.detail.setText(" · ".join(filter(None, (job.site, quality, job.options.kind.title()))))
        busy = job.status in {"extracting", "processing", "cancelling"}
        if busy:
            self.animation.stop()
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            target = min(1000, max(0, int(job.progress * 10)))
            if target != self.animation.endValue():
                self.animation.stop()
                self.animation.setStartValue(self.progress.value())
                self.animation.setEndValue(target)
                self.animation.start()
        descriptions = {
            "queued": "Waiting for a free slot", "extracting": "Reading video details…",
            "paused": "Paused · ready to resume", "processing": "Merging, converting or clipping…",
            "cancelling": "Cancelling after the current network or FFmpeg step…",
            "completed": "Saved to your library", "cancelled": "Cancelled · partial files kept for retry",
            "failed": job.error,
        }
        state = descriptions.get(job.status, f"{job.progress:.0f}%  ·  {human_bytes(job.speed)}/s  ·  {duration_text(job.eta)} left")
        self.state.setText(state)
        self.pause.setVisible(job.status in {"queued", "extracting", "downloading"})
        self.resume.setVisible(job.status == "paused")
        self.cancel.setVisible(job.status not in {"completed", "failed", "cancelled", "cancelling"})
        self.retry.setVisible(job.status in {"failed", "cancelled"})


class QueuePage(QWidget):
    """Keep a stable card per job as signals arrive from the queue manager."""

    def __init__(self, queue: Any) -> None:
        super().__init__()
        self.queue = queue
        self.rows: dict[str, JobCard] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll, _, layout = scroll_page()
        root.addWidget(scroll)
        heading = QHBoxLayout()
        heading.addWidget(label("Your queue", "heading"), 1)
        clear = Button("Clear finished", "check", "ghost")
        clear.clicked.connect(queue.remove_finished)
        heading.addWidget(clear)
        layout.addLayout(heading)
        self.summary = label("", "muted")
        layout.addWidget(self.summary)
        self.container = QVBoxLayout()
        self.container.setSpacing(14)
        layout.addLayout(self.container)
        self.empty = EmptyState("A little room for something good.", "Your downloads will appear here. Paste a link to get started.")
        layout.addWidget(self.empty)
        layout.addStretch()
        layout.addWidget(label("Pause takes effect between transfer chunks. FFmpeg steps finish before cancellation.\nPaused transfers keep their parallel slot; cancel and retry to release it.", "caption", True))
        queue.jobs_changed.connect(self.refresh)
        queue.job_changed.connect(self.changed)
        self.refresh()

    def refresh(self) -> None:
        """Reconcile visible rows against the persisted queue."""
        ids = {job.id for job in self.queue.jobs}
        for key in list(self.rows):
            if key not in ids:
                self.rows.pop(key).deleteLater()
        for job in self.queue.jobs:
            if job.id not in self.rows:
                row = JobCard(job, self.queue)
                self.rows[job.id] = row
                self.container.addWidget(row)
        self.empty.setVisible(not self.queue.jobs)
        self._summary()

    def changed(self, job: Job) -> None:
        """Refresh just the affected progress card."""
        if job.id not in self.rows:
            self.refresh()
        self.rows[job.id].update_job(job)
        self._summary()

    def _summary(self) -> None:
        active = sum(j.status in {"extracting", "downloading", "processing"} for j in self.queue.jobs)
        waiting = sum(j.status == "queued" for j in self.queue.jobs)
        self.summary.setText(f"{active} downloading  ·  {waiting} waiting  ·  {len(self.queue.jobs)} total")
