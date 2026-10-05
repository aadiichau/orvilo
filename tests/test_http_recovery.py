"""Exercise Bilibili transfer recovery against an intentionally unreliable server."""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
import time

import pytest
from yt_dlp import YoutubeDL
from yt_dlp.downloader.http import HttpFD

from core.downloader import Cancelled, Control, _configure_transfer


@pytest.fixture
def unreliable_media_server():
    """Serve deterministic bytes, dropping long and one bounded connection."""
    payload = bytes(range(256)) * 12289
    requests: list[tuple[int, int | None, str]] = []
    state = {"interrupted": False}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            """Keep expected interrupted fixture requests out of test output."""

        def do_GET(self) -> None:
            """Only complete finite ranges; interrupt the first one partway."""
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
            start = int(match[1]) if match else 0
            requested_end = int(match[2]) if match and match[2] else None
            requests.append((start, requested_end, self.headers.get("Referer", "")))
            end = min(requested_end, len(payload) - 1) if requested_end is not None else len(payload) - 1
            self.send_response(206 if match else 200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            if match:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(payload)}")
            self.send_header("Connection", "close")
            self.end_headers()
            response = payload[start:end + 1]
            if requested_end is None:
                response = response[:16384]
            elif not state["interrupted"]:
                state["interrupted"] = True
                response = response[:65536]
            try:
                self.wfile.write(response)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/media", payload, requests, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_bilibili_ranges_resume_partial_and_recover_without_corruption(
    unreliable_media_server, tmp_path: Path,
) -> None:
    """The actual yt-dlp HTTP path survives a dropped range and keeps all bytes."""
    url, payload, requests, state = unreliable_media_server
    final_path = tmp_path / "owned-test-media.bin"
    partial_path = final_path.with_suffix(".bin.part")
    prefix_size = 32768
    partial_path.write_bytes(payload[:prefix_size])
    control = Control()
    events: list[dict] = []
    info = {"id": "owned-test-media", "title": "Local recovery test", "url": url,
            "extractor_key": "BiliBiliFixture", "ext": "bin",
            "http_headers": {"Referer": "https://www.bilibili.com/"}}
    params = {"quiet": True, "noprogress": True, "continuedl": True,
              "socket_timeout": 3, "retries": 3, "proxy": ""}
    with YoutubeDL(params) as engine:
        _configure_transfer(engine, info, control)
        downloader = HttpFD(engine, engine.params)
        downloader.add_progress_hook(events.append)
        success, attempted = downloader.download(str(final_path), info)
    assert success and attempted
    assert state["interrupted"]
    assert len(requests) >= 4
    assert requests[0][0] == prefix_size
    assert prefix_size < requests[1][0] <= prefix_size + 65536
    assert all(end is not None and end - start + 1 <= 1024 * 1024 for start, end, _ in requests)
    assert all(referer == "https://www.bilibili.com/" for _, _, referer in requests)
    assert hashlib.sha256(final_path.read_bytes()).digest() == hashlib.sha256(payload).digest()
    assert not partial_path.exists()
    assert events[-1]["status"] == "finished"
    assert events[-1]["downloaded_bytes"] == len(payload)


def test_transfer_tuning_does_not_change_other_extractors() -> None:
    """Site-specific recovery does not overwrite another site's parameters."""
    with YoutubeDL({"quiet": True, "http_chunk_size": 4321, "retries": 4}) as engine:
        original = dict(engine.params)
        _configure_transfer(engine, {"extractor_key": "Youtube"}, Control())
        assert engine.params == original


def test_cancellation_interrupts_retry_backoff() -> None:
    """Cancel wakes a worker inside backoff instead of waiting out its delay."""
    control = Control()
    failures: list[BaseException] = []
    entered = threading.Event()
    with YoutubeDL({"quiet": True}) as engine:
        _configure_transfer(engine, {"extractor_key": "BiliBili"}, control)
        backoff = engine.params["retry_sleep_functions"]["http"]

        def retry_worker() -> None:
            entered.set()
            try:
                backoff(n=10)
            except BaseException as exc:
                failures.append(exc)

        worker = threading.Thread(target=retry_worker, daemon=True)
        worker.start()
        assert entered.wait(timeout=1)
        time.sleep(0.05)
        started = time.monotonic()
        control.cancel()
        worker.join(timeout=1)
        assert not worker.is_alive()
        assert time.monotonic() - started < 1
        assert len(failures) == 1
        assert isinstance(failures[0], Cancelled)
