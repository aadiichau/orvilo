"""Bilibili mirror discovery and recovery, without contacting a remote site."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
from pathlib import Path
import re
import threading
from unittest.mock import patch

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from core.downloader import Cancelled
from core.site_adapters import BiliBiliIE, ResilientYoutubeDL
from utils.errors import friendly_error


def test_extractor_preserves_signed_video_and_audio_backup_urls() -> None:
    """Both Bilibili API field conventions retain each stream's own mirrors."""
    video_url = "https://primary.example/video-100026.m4s?signature=video"
    audio_url = "https://primary.example/audio-30280.m4s?signature=audio"
    video_backups = ["https://backup.example/video-100026.m4s?signature=video-backup"]
    audio_backups = ["https://backup.example/audio-30280.m4s?signature=audio-backup"]
    play_info = {
        "support_formats": [{"quality": 80, "new_description": "1080P"}],
        "dash": {
            "video": [{"id": 80, "baseUrl": video_url, "backupUrl": video_backups,
                       "mimeType": "video/mp4", "codecs": "avc1.640032", "width": 1920,
                       "height": 1080, "bandwidth": 1000000, "frameRate": "30"}],
            "audio": [{"id": 30280, "base_url": audio_url, "backup_url": audio_backups,
                       "mime_type": "audio/mp4", "codecs": "mp4a.40.2", "bandwidth": 128000}],
        },
    }
    with YoutubeDL({"quiet": True}) as engine:
        formats = BiliBiliIE(engine).extract_formats(play_info)
    by_url = {item["url"]: item for item in formats}
    assert by_url[video_url]["_orvilo_backup_urls"] == video_backups
    assert by_url[audio_url]["_orvilo_backup_urls"] == audio_backups
    assert by_url[video_url]["format_id"] == "100026"
    assert by_url[video_url]["height"] == 1080
    assert by_url[audio_url]["format_id"] == "30280"
    assert by_url[audio_url]["vcodec"] == "none"


@pytest.fixture
def mirror_server():
    """An interrupted primary and a healthy mirror serve identical test bytes."""
    payload = bytes(range(256)) * 4096 + b"Orvilo mirror integrity fixture"
    requests: list[tuple[str, int, str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            """Suppress routine local fixture request logs."""

        def do_GET(self) -> None:
            """Close primary streams early, but serve complete mirror ranges."""
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
            start = int(match[1]) if match else 0
            end = min(int(match[2]), len(payload) - 1) if match and match[2] else len(payload) - 1
            requests.append((self.path, start, self.headers.get("Referer", ""),
                             self.headers.get("X-Media-Token", "")))
            self.send_response(206 if match else 200)
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Connection", "close")
            if match:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.end_headers()
            response = payload[start:end + 1]
            if self.path.startswith("/primary"):
                response = response[:65536]
            try:
                self.wfile.write(response)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", payload, requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def test_real_mirror_transfer_resumes_partial_without_changing_bytes(
    mirror_server, tmp_path: Path,
) -> None:
    """A primary connection failure resumes on the API mirror with intact data."""
    base, payload, requests = mirror_server
    destination = tmp_path / "same-format.bin"
    partial = destination.with_suffix(".bin.part")
    seed_size = 32768
    partial.write_bytes(payload[:seed_size])
    info = {"id": "fixture", "title": "Local mirror test", "ext": "bin", "protocol": "http",
            "url": base + "/primary?signature=primary", "format_id": "100026",
            "extractor_key": "BiliBili",
            "_orvilo_backup_urls": [base + "/backup?signature=backup"],
            "http_headers": {"Referer": "https://www.bilibili.com/", "X-Media-Token": "fixture"}}
    events: list[dict] = []
    with ResilientYoutubeDL({"quiet": True, "noprogress": True, "continuedl": True,
                             "retries": 0, "proxy": "", "socket_timeout": 3,
                             "progress_hooks": [events.append]}) as engine:
        success, attempted = engine.dl(str(destination), info)
    assert success and attempted
    assert len(requests) == 2
    assert requests[0][0] == "/primary?signature=primary"
    assert requests[0][1] == seed_size
    assert requests[1][0] == "/backup?signature=backup"
    assert seed_size < requests[1][1] <= seed_size + 65536
    assert all(referer == "https://www.bilibili.com/" and token == "fixture"
               for _, _, referer, token in requests)
    assert info["format_id"] == "100026"
    assert hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(payload).digest()
    assert not partial.exists()
    assert events[-1]["status"] == "finished"
    assert events[-1]["downloaded_bytes"] == len(payload)


@pytest.mark.parametrize("failure", [DownloadError("unable to write data: disk full"),
                                     DownloadError("unable to download video data: No space left on device"),
                                     DownloadError("unable to open for writing: Permission denied"),
                                     Cancelled("Download cancelled")])
def test_local_failures_and_cancellation_do_not_try_another_mirror(failure: Exception) -> None:
    """Mirrors cannot repair local storage problems or override cancellation."""
    info = {"id": "fixture", "url": "https://primary.example/video.mp4", "extractor_key": "BiliBili",
            "_orvilo_backup_urls": ["https://backup.example/video.mp4"]}
    with ResilientYoutubeDL({"quiet": True}) as engine:
        with patch.object(YoutubeDL, "dl", side_effect=failure) as native_download:
            with pytest.raises(type(failure), match=re.escape(str(failure))):
                engine.dl("owned-fixture.mp4", info)
            assert native_download.call_count == 1


def test_incomplete_transfer_message_explains_partial_file_recovery() -> None:
    """The reported Bilibili transport error gives the user a useful next step."""
    error = DownloadError("[download] Got error: 23337 bytes read, 566170105 more expected. Giving up after 3 retries")
    message = friendly_error(error)
    assert "interrupted" in message.lower()
    assert "partial download is saved" in message.lower()
    assert "retry" in message.lower()
    assert "566170105" not in message
