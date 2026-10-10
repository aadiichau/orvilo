"""Offline verification of the actual packaged engine and helper executables."""
from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
from typing import Any

from core.downloader import Control, _runtime, download
from core.engine import engine_version
from core.models import DownloadOptions
from core.video_formats import VIDEO_FORMATS


def verify_runtime(destination: Path, ffmpeg_path: str = "") -> dict[str, Any]:
    """Generate owned media locally and verify real downloads and conversions."""
    destination.mkdir(parents=True, exist_ok=True)
    ffmpeg = _runtime("ffmpeg", ffmpeg_path)
    ffprobe = _runtime("ffprobe", str(Path(ffmpeg_path).parent) if ffmpeg_path and Path(ffmpeg_path).is_file() else ffmpeg_path)
    deno = _runtime("deno")
    if not all((ffmpeg, ffprobe, deno)):
        raise ValueError("Runtime verification needs FFmpeg, FFprobe and Deno. Run setup first.")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    def run(command: list[str]) -> str:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              check=True, timeout=90, creationflags=flags).stdout

    run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "color=c=0x7C5CFF:s=320x180:r=25:d=3", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=3", "-c:v", "libx264", "-preset", "ultrafast",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(destination / "fixture.mp4")])

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, _message: str, *_args: Any) -> None:
            """Suppress routine localhost request logs."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(destination)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    reports = []
    try:
        for mode in (*VIDEO_FORMATS, "mp3", "m4a", "flac", "wav", "opus", "clip"):
            options = DownloadOptions(folder=str(destination / "downloads"), organize_by_site=False, ffmpeg_path=ffmpeg)
            if mode == "clip":
                options.clip_start, options.clip_end = 0.5, 2.0
            elif mode in VIDEO_FORMATS:
                options.video_format = mode
            else:
                options.kind, options.audio_format = "audio", mode
            result = download(f"http://127.0.0.1:{server.server_port}/fixture.mp4", options, Control(), lambda _event: None)
            info = json.loads(run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", result.file_path]))
            duration = float(info["format"]["duration"])
            expected = ".mp4" if mode == "clip" else ("." + VIDEO_FORMATS[mode].extension if mode in VIDEO_FORMATS else "." + mode)
            if Path(result.file_path).suffix != expected or result.file_size <= 0:
                raise ValueError(f"Runtime verification failed for {mode} output.")
            if mode == "clip" and not 1.3 <= duration <= 1.8:
                raise ValueError("Runtime verification found an incorrect clip duration.")
            if mode in VIDEO_FORMATS or mode == "clip":
                video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
                audio = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")
                codecs = {"mp4": ("h264", "aac"), "mov": ("h264", "aac"), "prores": ("prores", "pcm_s16le"),
                          "mkv": ("h264", "aac"), "webm": ("vp9", "opus"), "clip": ("h264", "aac")}
                if (video["codec_name"], audio["codec_name"]) != codecs[mode]:
                    raise ValueError(f"Runtime verification found incorrect codecs for {mode}.")
                run([ffmpeg, "-v", "error", "-i", result.file_path, "-f", "null", "-"])
            reports.append({"mode": mode, "file": result.file_path, "size": result.file_size, "duration": duration})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)
    report = {"engine": engine_version(), "deno": run([deno, "--version"]).splitlines()[0], "checks": reports, "passed": True}
    (destination / "runtime-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
