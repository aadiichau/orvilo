"""Shared, serializable values passed between the UI and workers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class DownloadOptions:
    """An immutable-in-practice snapshot of a download's preferences."""

    kind: str = "video"
    quality: str = "Best"
    audio_format: str = "mp3"
    video_format: str = "mp4"
    folder: str = ""
    organize_by_site: bool = True
    filename_template: str = "%(title).160B [%(id)s].%(ext)s"
    clip_start: float | None = None
    clip_end: float | None = None
    subtitle_language: str = "en"
    subtitles: str = "none"
    auto_subtitles: bool = False
    save_thumbnail: bool = False
    embed_metadata: bool = True
    embed_cover: bool = False
    browser: str = "none"
    browser_profile: str = ""
    cookie_file: str = ""
    proxy: str = ""
    speed_limit_kib: int = 0
    ffmpeg_path: str = ""
    js_runtime_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible snapshot."""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> DownloadOptions:
        """Load known fields, ignoring fields from newer versions."""
        data = {k: v for k, v in value.items() if k in cls.__dataclass_fields__}
        # Existing queue/history snapshots used MKV and may have partial files.
        data.setdefault("video_format", "mkv")
        return cls(**data)


@dataclass
class MediaInfo:
    """A preview or a selectable entry in a collection."""

    url: str
    title: str = "Untitled video"
    uploader: str = ""
    duration: float | None = None
    thumbnail: str = ""
    site: str = ""
    qualities: list[int] = field(default_factory=list)
    entries: list[MediaInfo] = field(default_factory=list)
    is_playlist: bool = False
    more_entries: bool = False


@dataclass
class DownloadResult:
    """A successfully finalized media file."""

    title: str
    thumbnail: str
    site: str
    url: str
    quality: str
    kind: str
    file_path: str
    file_size: int


@dataclass
class Job:
    """UI-owned queue state. Workers communicate through signals only."""

    url: str
    options: DownloadOptions
    id: str = field(default_factory=lambda: uuid4().hex)
    title: str = "Reading video…"
    thumbnail: str = ""
    site: str = ""
    status: str = "queued"
    progress: float = 0.0
    speed: float = 0.0
    eta: float | None = None
    error: str = ""
    file_path: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize a resumable queue entry."""
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Job:
        """Load persisted state while tolerating newer optional fields."""
        data = {k: v for k, v in value.items() if k in cls.__dataclass_fields__}
        data["options"] = DownloadOptions.from_dict(data.get("options", {}))
        return cls(**data)
