"""Persistence tests exercise corruption recovery and file deletion boundaries."""
from pathlib import Path

import pytest

from core.history import HistoryStore
from core.models import DownloadOptions, DownloadResult
from core.settings import SettingsStore, validate_options
from utils.errors import friendly_error
from utils.formatting import extract_urls, parse_time


def test_settings_atomic_validation_and_corruption(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    store.update({"theme": "light", "parallel_downloads": 3})
    assert SettingsStore(store.path).get("theme") == "light"
    old = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.update({"parallel_downloads": 100})
    assert store.path.read_bytes() == old
    store.path.write_text("{broken", encoding="utf-8")
    assert SettingsStore(store.path).get("theme") == "dark"


def test_legacy_outputs_keep_mkv_and_new_settings_default_to_mp4(tmp_path):
    legacy = DownloadOptions.from_dict({"kind": "video", "quality": "1080p"})
    assert legacy.video_format == "mkv"
    store = SettingsStore(tmp_path / "settings.json")
    assert store.download_options().video_format == "mp4"
    store.update({"video_format": "mov"})
    assert SettingsStore(store.path).download_options().video_format == "mov"
    old = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.update({"video_format": "unrecognized"})
    assert store.path.read_bytes() == old


def test_history_search_filters_and_deletion(tmp_path):
    media = tmp_path / "file.mkv"
    media.write_bytes(b"test media")
    store = HistoryStore(tmp_path / "history.sqlite3")
    options = DownloadOptions(folder=str(tmp_path), proxy="https://secret:password@localhost")
    record = DownloadResult("A 100%_video", "https://example.com/image.jpg", "Local", "https://example.com/video", "720p", "video", str(media), media.stat().st_size)
    record_id = store.add(record, options)
    assert len(store.search(query="100%_")) == 1
    assert store.search(site="Other") == []
    assert store.search(kind="audio") == []
    row = store.search(site="Local", kind="video")[0]
    assert row["options"]["proxy"] == ""
    assert not row["missing"]
    store.delete(record_id)
    assert media.exists()
    record_id = store.add(record, options)
    media.unlink()
    assert store.search()[0]["missing"]
    store.delete(record_id, delete_file=True)
    assert not store.search()
    store.close()


def test_reject_unsafe_template_and_invalid_clip(tmp_path):
    with pytest.raises(ValueError):
        validate_options(DownloadOptions(folder=str(tmp_path), filename_template="../%(title)s.%(ext)s"))
    with pytest.raises(ValueError):
        validate_options(DownloadOptions(folder=str(tmp_path), clip_start=10, clip_end=5))


def test_time_links_and_human_errors():
    assert parse_time("1:02:03.5") == 3723.5
    assert parse_time("") is None
    with pytest.raises(ValueError):
        parse_time("1:60")
    assert extract_urls("watch https://example.com/a and https://example.com/a") == ["https://example.com/a"]
    assert "private" in friendly_error("ERROR: This video is private")
    assert "DRM" in friendly_error("DRM protected stream")
    assert "Traceback" not in friendly_error("Traceback technical stuff")
