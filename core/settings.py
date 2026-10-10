"""Validated settings persisted by atomic replacement of a JSON file."""
from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path
from typing import Any

from core.models import DownloadOptions
from core.video_formats import VIDEO_FORMATS
from utils.paths import data_dir

DEFAULTS: dict[str, Any] = {
    "download_folder": str(Path.home() / "Downloads" / "Orvilo"),
    "parallel_downloads": 2,
    "clipboard_detection": True,
    "minimize_to_tray": True,
    "theme": "dark",
    "accent": "#7C5CFF",
    "first_run": True,
    **{k: v for k, v in DownloadOptions().to_dict().items() if k != "folder"},
}


def validate_options(options: DownloadOptions) -> None:
    """Reject malformed settings before launching an engine worker."""
    if options.kind not in {"video", "audio"}:
        raise ValueError("Choose video or audio.")
    if options.quality not in {"Best", "4K", "1440p", "1080p", "720p", "480p"}:
        raise ValueError("Choose a quality from the list.")
    if options.audio_format not in {"mp3", "m4a", "flac", "wav", "opus"}:
        raise ValueError("Choose a supported audio format.")
    if options.video_format not in VIDEO_FORMATS:
        raise ValueError("Choose a supported video format.")
    if options.subtitles not in {"none", "save", "embed"}:
        raise ValueError("Choose whether to save or embed subtitles.")
    if options.browser not in {"none", "chrome", "edge", "firefox"}:
        raise ValueError("Choose Chrome, Edge, Firefox or no browser cookies.")
    template = options.filename_template
    if not template or any(c in template for c in ("/", "\\", "\x00", "\n", "\r")) or template.startswith("."):
        raise ValueError("The filename template must be a filename, without folders or path separators.")
    if not template.endswith(".%(ext)s"):
        raise ValueError("The filename template must end with .%(ext)s.")
    if ":" in template or ".." in template or template.startswith("~"):
        raise ValueError("The filename template cannot contain an absolute path or parent folders.")
    if not options.folder.strip():
        raise ValueError("Choose a download folder.")
    if not isinstance(options.speed_limit_kib, int) or options.speed_limit_kib < 0:
        raise ValueError("The speed limit must be zero or a positive number in KiB/s.")
    for bound in (options.clip_start, options.clip_end):
        if bound is not None and (not math.isfinite(bound) or bound < 0):
            raise ValueError("Clip times must be zero or positive.")
    if options.clip_end is not None and options.clip_end <= (options.clip_start or 0):
        raise ValueError("The clip end must be later than the start.")
    if options.proxy and not re.match(r"^(https?|socks[45]h?)://", options.proxy, re.I):
        raise ValueError("A proxy must begin with http://, https://, socks4:// or socks5://.")


class SettingsStore:
    """A small validated settings store. The UI thread owns all writes."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or data_dir() / "settings.json"
        self.data = dict(DEFAULTS)
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    candidate = {**self.data, **value}
                    self._validate(candidate)
                    self.data = candidate
            except (OSError, ValueError, TypeError):
                logging.getLogger(__name__).warning("Invalid settings; using defaults", exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Read a persisted preference."""
        return self.data.get(key, default)

    def update(self, changes: dict[str, Any]) -> None:
        """Validate and atomically persist changes before publishing them."""
        candidate = {**self.data, **changes}
        self._validate(candidate)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)
        self.data = candidate

    def download_options(self) -> DownloadOptions:
        """Create an independent snapshot for a new job."""
        data = dict(self.data)
        data["folder"] = self.data["download_folder"]
        return DownloadOptions.from_dict(data)

    @staticmethod
    def _validate(data: dict[str, Any]) -> None:
        if data["theme"] not in {"dark", "light"}:
            raise ValueError("Choose the dark or light theme.")
        if not isinstance(data["accent"], str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", data["accent"]):
            raise ValueError("Choose an accent color such as #7C5CFF.")
        if not isinstance(data["parallel_downloads"], int) or not 1 <= data["parallel_downloads"] <= 6:
            raise ValueError("Choose between 1 and 6 parallel downloads.")
        options = DownloadOptions.from_dict({**data, "folder": data["download_folder"]})
        validate_options(options)
