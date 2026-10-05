"""The first-run installer verifies origin, integrity, cancellation and publication."""
import hashlib
import io
import json
from pathlib import Path
from threading import Event
import time
import zipfile

import pytest

from core import runtime_setup
from core.settings import SettingsStore
from utils.paths import data_dir


def package(extra: str | None = None, missing: bool = False) -> bytes:
    """Create a small archive with the same shape as the publisher's package."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("ffmpeg-9.0.2/bin/ffmpeg.exe", b"MZfake-test-binary")
        if not missing:
            archive.writestr("ffmpeg-9.0.2/bin/ffprobe.exe", b"MZfake-test-probe")
        archive.writestr("ffmpeg-9.0.2/LICENSE", "Test license")
        archive.writestr("ffmpeg-9.0.2/README.txt", "Test build information")
        if extra:
            entry = zipfile.ZipInfo(extra)
            entry.filename = extra
            archive.writestr(entry, "invalid")
    return stream.getvalue()


def mock_download(monkeypatch, payload: bytes, *, tamper: bool = False) -> None:
    """Use deterministic fixture bytes without connecting to the publisher."""
    expected = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(runtime_setup, "ARCHIVE_SHA256", expected)

    def fetch(url, destination, limit, progress, cancel):
        runtime_setup._check_cancel(cancel)
        content = expected.encode() if url == runtime_setup.CHECKSUM_URL else payload
        if tamper and url == runtime_setup.ARCHIVE_URL:
            content += b"changed"
        destination.write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    monkeypatch.setattr(runtime_setup, "_download", fetch)


def test_installer_publishes_both_tools_and_notices(monkeypatch):
    mock_download(monkeypatch, package())
    updates = []
    folder = runtime_setup.install_ffmpeg(lambda *args: updates.append(args), Event())
    assert (folder / "ffmpeg.exe").read_bytes().startswith(b"MZ")
    assert (folder / "ffprobe.exe").is_file()
    assert (folder / "licenses" / "LICENSE").is_file()
    record = json.loads((folder / "versions.json").read_text())
    assert record["archive_sha256"] == runtime_setup.ARCHIVE_SHA256
    assert record["sha256"]["ffmpeg.exe"] == hashlib.sha256((folder / "ffmpeg.exe").read_bytes()).hexdigest()
    assert updates[-1][0] == 100
    assert list((data_dir() / "runtime").iterdir()) == [folder]


@pytest.mark.parametrize("bad_path", ["../escaped.exe", "/absolute.exe", "C:/outside.exe", "folder\\outside.exe"])
def test_installer_rejects_unsafe_archive(monkeypatch, bad_path):
    mock_download(monkeypatch, package(extra=bad_path))
    with pytest.raises(ValueError, match="unsafe path"):
        runtime_setup.install_ffmpeg(lambda *_args: None, Event())
    assert list((data_dir() / "runtime").iterdir()) == []


def test_installer_rejects_bad_checksum_and_preserves_old_install(monkeypatch):
    old = data_dir() / "runtime" / "existing"
    old.mkdir(parents=True)
    (old / "ffmpeg.exe").write_bytes(b"existing")
    mock_download(monkeypatch, package(), tamper=True)
    with pytest.raises(ValueError, match="verification failed"):
        runtime_setup.install_ffmpeg(lambda *_args: None, Event())
    assert (old / "ffmpeg.exe").read_bytes() == b"existing"
    assert list(old.parent.iterdir()) == [old]


def test_installer_rejects_missing_tool(monkeypatch):
    mock_download(monkeypatch, package(missing=True))
    with pytest.raises(ValueError, match="missing a required"):
        runtime_setup.install_ffmpeg(lambda *_args: None, Event())
    assert list((data_dir() / "runtime").iterdir()) == []


def test_installer_cancellation_before_publication(monkeypatch):
    mock_download(monkeypatch, package())
    cancel = Event()

    def progress(percent, _message):
        if percent == 91:
            cancel.set()

    with pytest.raises(runtime_setup.SetupCancelled):
        runtime_setup.install_ffmpeg(progress, cancel)
    assert list((data_dir() / "runtime").iterdir()) == []


def test_download_rejects_unapproved_origin(tmp_path):
    with pytest.raises(ValueError, match="approved"):
        runtime_setup._download("https://example.com/tool.zip", tmp_path / "archive", 100, lambda *_: None, Event())


def test_missing_configured_runtime_offers_setup(tmp_path):
    from ui.runtime_dialog import runtime_available
    settings = SettingsStore()
    settings.update({"ffmpeg_path": str(tmp_path / "not-present" / "ffmpeg.exe")})
    assert not runtime_available(settings)


def test_dialog_installs_without_blocking_event_loop(app, monkeypatch):
    from ui import runtime_dialog
    settings = SettingsStore()
    destination = data_dir() / "runtime" / "test"
    destination.mkdir(parents=True)

    def install(progress, cancel):
        progress(25, "Test progress")
        time.sleep(0.05)
        progress(100, "Ready")
        return destination

    monkeypatch.setattr(runtime_dialog, "install_ffmpeg", install)
    dialog = runtime_dialog.RuntimeDialog(None, settings)
    dialog.show()
    dialog.start_install()
    assert dialog.worker is not None and dialog.worker.isRunning()
    deadline = time.monotonic() + 5
    while dialog.isVisible() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert not dialog.isVisible()
    assert settings.get("ffmpeg_path") == str(destination)
    assert dialog.result() == dialog.DialogCode.Accepted
