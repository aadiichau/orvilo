"""Exercise real Qt navigation, preview selection, settings and queue controls."""
import time

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from core.history import HistoryStore
from core.models import MediaInfo
from core.queue import QueueManager
from core.settings import SettingsStore
from ui.window import MainWindow


def spin(app, predicate):
    """Pump queued Qt callbacks while waiting for a worker response."""
    end = time.monotonic() + 5
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_preview_selection_queue_and_settings(app, tmp_path, monkeypatch):
    settings = SettingsStore()
    settings.update({"first_run": False, "minimize_to_tray": False, "clipboard_detection": False,
                     "download_folder": str(tmp_path)})
    history = HistoryStore()
    queue = QueueManager(settings, history)
    queue._parallel = 0
    one = MediaInfo("https://example.com/one", "First video", "Creator", 30, site="Fixture")
    two = MediaInfo("https://example.com/two", "Second video", "Creator", 45, site="Fixture")
    monkeypatch.setattr("ui.home.probe", lambda *_args, **_kwargs: MediaInfo("https://example.com/collection", "A collection", entries=[one, two], is_playlist=True))
    window = MainWindow(settings, history, queue)
    window.show()
    window.home.set_links("https://example.com/collection")
    window.home.timer.stop()
    window.home._begin_probe()
    spin(app, lambda: window.home.entries.count() == 2)
    window.home.entries.item(0).setCheckState(Qt.CheckState.Unchecked)
    window.home.video_format.setCurrentIndex(window.home.video_format.findData("prores"))
    QTest.mouseClick(window.home.download_button, Qt.MouseButton.LeftButton)
    assert len(queue.jobs) == 1 and queue.jobs[0].url == two.url
    assert queue.jobs[0].options.video_format == "prores"
    assert SettingsStore().get("video_format") == "prores"
    window.home.kind.setCurrentIndex(window.home.kind.findData("audio"))
    assert window.home.video_field.isHidden() and not window.home.audio_field.isHidden()
    window.home.kind.setCurrentIndex(window.home.kind.findData("video"))
    assert not window.home.video_field.isHidden()
    assert window.stack.currentIndex() == 1
    assert queue.jobs[0].id in window.queue_page.rows
    queue.pause(queue.jobs[0].id)
    assert window.queue_page.rows[queue.jobs[0].id].resume.isVisible()
    queue.cancel(queue.jobs[0].id)
    window.navigate(3, animate=False)
    window.settings_page.fields["theme"].setCurrentIndex(1)
    window.settings_page.fields["parallel_downloads"].setValue(3)
    window.settings_page.save()
    assert settings.get("theme") == "light"
    assert SettingsStore().get("parallel_downloads") == 3
    queue.shutdown()
    window.home.cancel_pending()
    spin(app, window.tasks.is_idle)
    window._ready_to_close = True
    window.tray.hide()
    window.close()
    history.close()
