"""Downloader contracts that do not require an external website."""
import threading
from unittest.mock import MagicMock

import pytest
from yt_dlp.utils import DownloadError, UnsupportedError

from core.downloader import (
    Cancelled, Control, _extract, _filename, _media, _selected_url, _selection, _validate_url,
)
from core.models import DownloadOptions


def test_control_pauses_resumes_and_cancellation_wakes_waiter():
    control = Control()
    control.pause()
    arrived = threading.Event()
    completed = threading.Event()
    failures = []

    def worker():
        arrived.set()
        try:
            control.checkpoint()
        except Cancelled:
            failures.append("cancelled")
        completed.set()

    thread = threading.Thread(target=worker)
    thread.start()
    assert arrived.wait(1)
    assert not completed.wait(0.03)
    control.resume()
    assert completed.wait(1)
    thread.join(1)
    assert not failures
    completed.clear()
    control.pause()
    thread = threading.Thread(target=worker)
    thread.start()
    control.cancel()
    assert completed.wait(1)
    thread.join(1)
    assert failures == ["cancelled"]
    assert control.cancelled


def test_formats_and_clip_ranges_cannot_reuse_other_outputs():
    names = {
        _filename(DownloadOptions(quality="720p")),
        _filename(DownloadOptions(quality="1080p")),
        _filename(DownloadOptions(kind="audio", audio_format="mp3")),
        _filename(DownloadOptions(clip_start=0, clip_end=10)),
        _filename(DownloadOptions(clip_start=10, clip_end=20)),
    }
    assert len(names) == 5
    assert all(name.endswith(".%(ext)s") for name in names)


@pytest.mark.parametrize("template", ["../%(title)s.%(ext)s", "C:\\%(title)s.%(ext)s", "a\n%(ext)s", "%(title)s.mp4"])
def test_filename_rejects_escaping_templates(template):
    with pytest.raises(ValueError):
        _filename(DownloadOptions(filename_template=template))


def test_generic_fallback_only_on_unsupported_urls():
    engine = MagicMock()
    engine.extract_info.side_effect = [UnsupportedError("https://test.invalid/a"), {"title": "Found"}]
    assert _extract(engine, "https://test.invalid/a")["title"] == "Found"
    assert engine.extract_info.call_args.kwargs["ie_key"] == "Generic"
    engine.reset_mock()
    engine.extract_info.side_effect = DownloadError("This video is private")
    with pytest.raises(DownloadError):
        _extract(engine, "https://test.invalid/a")
    assert engine.extract_info.call_count == 1


def test_selected_attachment_preserves_original_fragment():
    source = "https://example.org/post#section"
    selected = _selected_url(source, 3)
    assert selected == "https://example.org/post#section&orvilo-item=3"
    assert _selection(selected) == (source, 3)
    assert _selection(source) == (source, None)
    assert _selection("https://example.org/post#orvilo-item=0")[1] is None


def test_media_uses_stable_webpage_and_excludes_drm_qualities():
    media = _media({
        "title": "Sample", "url": "https://cdn.example.org/expiring.mp4", "extractor_key": "Youtube",
        "formats": [{"height": 1080, "vcodec": "h264"}, {"height": 2160, "has_drm": True}],
    }, "https://example.org/post")
    assert media.url == "https://example.org/post"
    assert media.qualities == [1080]
    assert media.site == "YouTube"


@pytest.mark.parametrize("url", ["file:///secret.txt", "not a URL", "https://user:password@example.org/video"])
def test_unsupported_url_schemes_and_credentials(url):
    with pytest.raises(ValueError):
        _validate_url(url)
