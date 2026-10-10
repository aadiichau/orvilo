"""Threaded queue orchestration and restart-safe queue persistence."""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot

from core import downloader
from core.history import HistoryStore
from core.models import DownloadOptions, DownloadResult, Job, MediaInfo
from core.settings import SettingsStore, validate_options
from utils.errors import friendly_error
from utils.formatting import extract_urls
from utils.paths import data_dir

log = logging.getLogger(__name__)
TERMINAL = {"completed", "failed", "cancelled"}


class WorkerSignals(QObject):
    """Only these queued signals transport results back to the UI thread."""

    progress = Signal(str, object)
    succeeded = Signal(str, object)
    failed = Signal(str, str)
    stopped = Signal(str)
    done = Signal(str)


class DownloadWorker(QRunnable):
    """Run one library download on an independent pool thread."""

    def __init__(self, job: Job, control: downloader.Control) -> None:
        super().__init__()
        self.job = replace(job, options=replace(job.options))
        self.control = control
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        """Report every exit path, including cancellation, without UI access."""
        try:
            result = downloader.download(self.job.url, self.job.options, self.control,
                                         lambda value: self.signals.progress.emit(self.job.id, value))
            # A finalized successful file must be retained even if Cancel was
            # clicked in the tiny interval after the last engine checkpoint.
            self.signals.succeeded.emit(self.job.id, result)
        except downloader.Cancelled:
            self.signals.stopped.emit(self.job.id)
        except Exception as error:
            if self.control.cancelled:
                self.signals.stopped.emit(self.job.id)
            else:
                log.exception("Download failed")
                self.signals.failed.emit(self.job.id, friendly_error(error))
        finally:
            self.signals.done.emit(self.job.id)


class QueueManager(QObject):
    """Keep all queue state on the UI thread and all network work off it."""

    job_changed = Signal(object)
    jobs_changed = Signal()
    completed = Signal(object)
    notice = Signal(str)

    def __init__(self, settings: SettingsStore, history: HistoryStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.history = history
        self.jobs: list[Job] = []
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(6)
        self._workers: dict[str, DownloadWorker] = {}
        self._controls: dict[str, downloader.Control] = {}
        self._parallel = settings.get("parallel_downloads", 2)
        self._closing = False
        self._path = data_dir() / "queue.json"
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save)
        self._load()

    @property
    def active_count(self) -> int:
        """Number of workers, including cooperatively paused transfers."""
        return len(self._workers)

    def is_idle(self) -> bool:
        """Return whether workers have exited and can be safely disposed."""
        return not self._workers and self.pool.activeThreadCount() == 0

    def enqueue(self, url: str, options: DownloadOptions, preview: MediaInfo | None = None) -> Job:
        """Validate and queue one item, suppressing competing duplicate writes."""
        if self._closing:
            raise ValueError("Orvilo is closing. Reopen it to add downloads.")
        if extract_urls(url) != [url]:
            raise ValueError("Paste a complete http:// or https:// video link.")
        validate_options(options)
        # Browser/proxy changes must not allow two workers to write one file.
        signature_keys = ("kind", "quality", "audio_format", "video_format", "folder", "organize_by_site",
                          "filename_template", "clip_start", "clip_end")
        def signature_for(candidate: DownloadOptions) -> tuple[Any, ...]:
            ignored = {"audio_format"} if candidate.kind == "video" else {"quality", "video_format"}
            return tuple(None if key in ignored else getattr(candidate, key) for key in signature_keys)
        signature = signature_for(options)
        for current in self.jobs:
            if current.status not in TERMINAL and current.url == url and signature == signature_for(current.options):
                self.notice.emit("This download is already in the queue.")
                return current
        job = Job(url=url, options=replace(options))
        if preview:
            job.title, job.thumbnail, job.site = preview.title, preview.thumbnail, preview.site
        self.jobs.append(job)
        self.jobs_changed.emit()
        self._changed(job)
        self._schedule()
        return job

    def pause(self, item_id: str) -> None:
        """Pause at the next network progress hook; never suspend FFmpeg."""
        job = self._find(item_id)
        if not job or job.status in TERMINAL | {"paused", "cancelling"}:
            return
        if job.status == "processing":
            self.notice.emit("Merging and conversion cannot pause. You can cancel after the current processing step.")
            return
        if item_id in self._controls:
            self._controls[item_id].pause()
        job.status = "paused"
        job.speed = 0
        self._changed(job)

    def resume(self, item_id: str) -> None:
        """Resume a live pause or a persisted partial download."""
        job = self._find(item_id)
        if not job or job.status != "paused":
            return
        if item_id in self._controls:
            self._controls[item_id].resume()
            job.status = "downloading"
        else:
            job.status = "queued"
        self._changed(job)
        self._schedule()

    def cancel(self, item_id: str) -> None:
        """Request cooperative cancellation, retaining resumable partial files."""
        job = self._find(item_id)
        if not job or job.status in TERMINAL:
            return
        if item_id in self._controls:
            self._controls[item_id].cancel()
            job.status = "cancelling"
        else:
            job.status = "cancelled"
        self._changed(job)
        self._schedule()

    def retry(self, item_id: str) -> None:
        """Retry retained parts with current access and network preferences."""
        job = self._find(item_id)
        if not job or job.status not in {"failed", "cancelled"} or item_id in self._workers:
            return
        current = self.settings.download_options()
        for key in ("browser", "browser_profile", "cookie_file", "proxy", "speed_limit_kib", "ffmpeg_path", "js_runtime_path"):
            setattr(job.options, key, getattr(current, key))
        job.status, job.error, job.speed, job.eta = "queued", "", 0, None
        self._changed(job)
        self._schedule()

    def set_parallel(self, count: int) -> None:
        """Apply a 1–6 worker limit; running downloads finish when lowering it."""
        self._parallel = max(1, min(6, count))
        self._schedule()

    def remove_finished(self) -> None:
        """Remove terminal queue rows without deleting files or history."""
        self.jobs = [j for j in self.jobs if j.status not in TERMINAL or j.id in self._workers]
        self.jobs_changed.emit()
        self._save_timer.start()

    def shutdown(self) -> None:
        """Stop scheduling and cancel workers without blocking the event loop."""
        self._closing = True
        for control in self._controls.values():
            control.cancel()
        self._save_timer.stop()
        self._save()

    def _find(self, item_id: str) -> Job | None:
        return next((job for job in self.jobs if job.id == item_id), None)

    def _schedule(self) -> None:
        if self._closing:
            return
        for job in self.jobs:
            if len(self._workers) >= self._parallel:
                break
            if job.status != "queued" or job.id in self._workers:
                continue
            control = downloader.Control()
            worker = DownloadWorker(job, control)
            worker.signals.progress.connect(self._progress)
            worker.signals.succeeded.connect(self._succeeded)
            worker.signals.failed.connect(self._failed)
            worker.signals.stopped.connect(self._stopped)
            worker.signals.done.connect(self._done)
            self._controls[job.id] = control
            self._workers[job.id] = worker
            job.status = "extracting"
            self._changed(job)
            self.pool.start(worker)

    @Slot(str, object)
    def _progress(self, item_id: str, value: dict[str, Any]) -> None:
        job = self._find(item_id)
        if not job or job.status in TERMINAL:
            return
        for key in ("title", "thumbnail", "site", "progress", "speed", "eta"):
            if key in value and value[key] is not None:
                setattr(job, key, value[key])
        if job.status not in {"paused", "cancelling"}:
            state = value.get("status", job.status)
            job.status = "extracting" if state == "metadata" else state
        self._changed(job)

    @Slot(str, object)
    def _succeeded(self, item_id: str, result: DownloadResult) -> None:
        job = self._find(item_id)
        if not job:
            return
        job.status, job.progress, job.speed, job.eta = "completed", 100, 0, 0
        job.title, job.thumbnail, job.site = result.title, result.thumbnail, result.site
        job.file_path = result.file_path
        try:
            self.history.add(result, job.options)
        except Exception:
            log.exception("Could not write download history")
            self.notice.emit("Your file was saved, but history could not be updated. Check free disk space.")
        self._changed(job)
        self.completed.emit(job)

    @Slot(str, str)
    def _failed(self, item_id: str, message: str) -> None:
        job = self._find(item_id)
        if job:
            job.status, job.error, job.speed = "failed", message, 0
            self._changed(job)

    @Slot(str)
    def _stopped(self, item_id: str) -> None:
        job = self._find(item_id)
        if job:
            job.status, job.speed = ("paused" if self._closing else "cancelled"), 0
            self._changed(job)

    @Slot(str)
    def _done(self, item_id: str) -> None:
        self._workers.pop(item_id, None)
        self._controls.pop(item_id, None)
        self._schedule()
        if self._closing:
            self._save()

    def _changed(self, job: Job) -> None:
        self.job_changed.emit(job)
        if not self._save_timer.isActive():
            self._save_timer.start()

    def _save(self) -> None:
        try:
            snapshot = []
            for job in self.jobs:
                record = job.to_dict()
                # Credentials remain in settings only, not replicated in queue.
                for key in ("proxy", "cookie_file", "browser_profile"):
                    record["options"][key] = ""
                snapshot.append(record)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self._path)
        except (OSError, TypeError):
            log.exception("Could not persist queue")
            self.notice.emit("The queue could not be saved. Check free disk space before closing Orvilo.")

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            records = json.loads(self._path.read_text(encoding="utf-8"))
            for record in records:
                try:
                    job = Job.from_dict(record)
                    if job.status not in TERMINAL:
                        job.status = "paused"
                    for key in ("proxy", "cookie_file", "browser_profile"):
                        setattr(job.options, key, self.settings.get(key, ""))
                    validate_options(job.options)
                    self.jobs.append(job)
                except (ValueError, TypeError, KeyError):
                    log.warning("Skipped an invalid queue item")
        except (OSError, ValueError, TypeError):
            log.exception("Could not restore queue")
