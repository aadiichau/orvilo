"""Queue tests check concurrency, pausing, cancellation and persisted recovery."""
import time
from threading import Event, Lock

from core import downloader
from core.history import HistoryStore
from core.models import DownloadResult
from core.queue import QueueManager
from core.settings import SettingsStore


def spin(app, predicate, timeout=6):
    """Process Qt signals until a condition succeeds or fails deterministically."""
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    assert predicate(), "Qt worker condition did not complete in time"


def test_worker_concurrency_pause_cancel_history(app, tmp_path, monkeypatch):
    settings = SettingsStore()
    settings.update({"download_folder": str(tmp_path), "parallel_downloads": 2})
    history = HistoryStore()
    release = Event()
    lock = Lock()
    counts = {"active": 0, "peak": 0}

    def fake_download(url, options, control, progress):
        with lock:
            counts["active"] += 1
            counts["peak"] = max(counts["peak"], counts["active"])
        try:
            while not release.wait(0.01):
                control.checkpoint()
                progress({"status": "downloading", "progress": 35, "title": url})
            control.checkpoint()
            output = tmp_path / (url.rsplit("/", 1)[-1] + ".mkv")
            output.write_bytes(b"download complete")
            return DownloadResult(url, "", "fixture", url, "Best", "video", str(output), output.stat().st_size)
        finally:
            with lock:
                counts["active"] -= 1

    monkeypatch.setattr(downloader, "download", fake_download)
    queue = QueueManager(settings, history)
    first = queue.enqueue("https://example.com/one", settings.download_options())
    duplicate = queue.enqueue("https://example.com/one", settings.download_options())
    assert duplicate.id == first.id
    second = queue.enqueue("https://example.com/two", settings.download_options())
    third = queue.enqueue("https://example.com/three", settings.download_options())
    spin(app, lambda: first.status == "downloading" and second.status == "downloading")
    assert third.status == "queued"
    queue.pause(first.id)
    assert first.status == "paused"
    queue.cancel(first.id)
    spin(app, lambda: first.status == "cancelled" and third.status == "downloading")
    release.set()
    spin(app, lambda: queue.is_idle())
    assert counts["peak"] == 2
    assert second.status == third.status == "completed"
    assert len(history.search()) == 2
    settings.update({"browser": "firefox"})
    queue.retry(first.id)
    spin(app, lambda: queue.is_idle())
    assert first.status == "completed"
    assert first.options.browser == "firefox"
    queue.shutdown()
    history.close()


def test_queue_restores_paused_without_starting_network(app, tmp_path):
    settings = SettingsStore()
    settings.update({"download_folder": str(tmp_path)})
    history = HistoryStore()
    queue = QueueManager(settings, history)
    # Prevent scheduling so this test performs no network operations.
    queue._parallel = 0
    job = queue.enqueue("https://example.com/interrupted", settings.download_options())
    queue.shutdown()
    restored = QueueManager(settings, history)
    assert restored.jobs[0].id == job.id
    assert restored.jobs[0].status == "paused"
    assert restored.is_idle()
    restored.shutdown()
    history.close()


def test_queue_keeps_different_video_profiles_as_separate_jobs(app, tmp_path):
    from dataclasses import replace
    from core.downloader import _filename

    settings = SettingsStore()
    settings.update({"download_folder": str(tmp_path)})
    history = HistoryStore()
    queue = QueueManager(settings, history)
    queue._parallel = 0
    options = settings.download_options()
    jobs = [queue.enqueue("https://example.com/video", replace(options, video_format=profile))
            for profile in ("mp4", "mov", "prores", "mkv", "webm")]
    assert len({job.id for job in jobs}) == 5
    assert len({_filename(job.options) for job in jobs}) == 5
    assert queue.enqueue(jobs[0].url, options).id == jobs[0].id
    audio = queue.enqueue(jobs[0].url, replace(options, kind="audio"))
    assert queue.enqueue(jobs[0].url, replace(options, kind="audio", video_format="prores", quality="480p")).id == audio.id
    queue.shutdown()
    restored = QueueManager(settings, history)
    assert [job.options.video_format for job in restored.jobs if job.options.kind == "video"] == ["mp4", "mov", "prores", "mkv", "webm"]
    restored.shutdown()
    history.close()
