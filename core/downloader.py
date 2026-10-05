"""Thread-safe yt-dlp integration, preview extraction and finalized downloads."""
from __future__ import annotations

import logging
import math
import re
import shutil
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from yt_dlp import YoutubeDL
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import DownloadError, UnsupportedError

from core.models import DownloadOptions, DownloadResult, MediaInfo
from core.plugins import load_extractors
from core.site_adapters import BiliBiliIE, ResilientYoutubeDL
from utils.paths import asset_path, data_dir

_LOG = logging.getLogger(__name__)
_HEIGHTS = {"4K": 2160, "1440p": 1440, "1080p": 1080, "720p": 720, "480p": 480}
_AUDIO_FORMATS = {"mp3", "m4a", "flac", "wav", "opus"}
_PATH_LOCK = threading.Lock()
_OUTPUT_LOCKS: dict[str, tuple[threading.Lock, int]] = {}


class Cancelled(Exception):
    """The user cancelled at a safe network or postprocessing checkpoint."""


class Control:
    """Cooperative controls; in-flight network reads and FFmpeg must return first."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._paused = False
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        with self._condition:
            return self._cancelled

    def pause(self) -> None:
        """Block at the next safe checkpoint, keeping the current partial file."""
        with self._condition:
            self._paused = True

    def resume(self) -> None:
        """Release a paused worker."""
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def cancel(self) -> None:
        """Wake the worker and cancel at its next safe checkpoint."""
        with self._condition:
            self._cancelled = True
            self._condition.notify_all()

    def checkpoint(self) -> None:
        """Wait while paused; raise Cancelled if cancellation was requested."""
        with self._condition:
            while self._paused and not self._cancelled:
                self._condition.wait(timeout=0.5)
            if self._cancelled:
                raise Cancelled("Download cancelled")

    def wait(self, seconds: float) -> None:
        """Wait between retries while remaining responsive to cancel and pause."""
        deadline = time.monotonic() + seconds
        with self._condition:
            while True:
                self.checkpoint()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._condition.wait(timeout=min(remaining, 0.2))


class _Logger:
    def __init__(self, control: Control) -> None:
        self.control = control

    def debug(self, message: str) -> None:
        self.control.checkpoint()
        _LOG.debug("%s", message)

    def warning(self, message: str) -> None:
        self.control.checkpoint()
        _LOG.warning("%s", message)

    def error(self, message: str) -> None:
        self.control.checkpoint()
        _LOG.error("%s", message)


def _validate_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Paste a complete http:// or https:// video link.")
    if parsed.username or parsed.password:
        raise ValueError("Use browser cookies in Settings instead of passwords inside a link.")
    return url


def _selection(url: str) -> tuple[str, int | None]:
    parsed = urlparse(url)
    match = re.search(r"(?:^|&)orvilo-item=([1-9][0-9]*)$", parsed.fragment)
    if match is None:
        return url, None
    fragment = parsed.fragment[:match.start()]
    return urlunparse(parsed._replace(fragment=fragment)), int(match[1])


def _selected_url(url: str, index: int) -> str:
    parsed = urlparse(url)
    separator = "&" if parsed.fragment else ""
    return urlunparse(parsed._replace(fragment=f"{parsed.fragment}{separator}orvilo-item={index}"))


def _runtime(name: str, configured: str = "") -> str:
    if configured.strip():
        path = Path(configured).expanduser()
        if path.is_dir():
            path /= name + (".exe" if (path / (name + ".exe")).is_file() else "")
        if not path.is_file():
            raise FileNotFoundError(f"{name} was not found at the path saved in Settings.")
        return str(path.resolve())
    for candidate in (asset_path(f"runtime/{name}.exe"), asset_path(f"runtime/{name}")):
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or ""


def _base_options(options: DownloadOptions, control: Control) -> dict[str, Any]:
    result: dict[str, Any] = {
        "quiet": True,
        "noprogress": True,
        "logger": _Logger(control),
        "socket_timeout": 25,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "file_access_retries": 3,
        "continuedl": True,
        "overwrites": False,
        "windowsfilenames": True,
        "trim_file_name": 200,
        "ignoreerrors": False,
        "allow_unplayable_formats": False,
        "cachedir": str(data_dir() / "engine-cache"),
        "concurrent_fragment_downloads": 1,
    }
    ffmpeg = _runtime("ffmpeg", options.ffmpeg_path)
    if ffmpeg:
        result["ffmpeg_location"] = ffmpeg
    deno = _runtime("deno", options.js_runtime_path)
    if deno:
        result["js_runtimes"] = {"deno": {"path": deno}}
    if options.browser != "none":
        if options.browser not in {"chrome", "edge", "firefox"}:
            raise ValueError("Choose Chrome, Edge or Firefox for browser cookies.")
        result["cookiesfrombrowser"] = (options.browser, options.browser_profile.strip() or None)
    if options.cookie_file.strip():
        if not Path(options.cookie_file).is_file():
            raise FileNotFoundError("The cookies file saved in Settings could not be found.")
        result["cookiefile"] = options.cookie_file
    if options.proxy.strip():
        proxy = options.proxy.strip()
        if urlparse(proxy).scheme not in {"http", "https", "socks4", "socks4a", "socks5", "socks5h"}:
            raise ValueError("Use an http://, https:// or socks5:// proxy address.")
        result["proxy"] = proxy
    if options.speed_limit_kib > 0:
        result["ratelimit"] = options.speed_limit_kib * 1024
    return result


def _new_ydl(params: dict[str, Any]) -> YoutubeDL:
    engine = ResilientYoutubeDL(params, auto_init=False)
    try:
        # Register local extractors before the built-ins and the generic fallback.
        for cls in load_extractors():
            engine.add_info_extractor(cls())
        engine.add_default_info_extractors()
        # Replacing this key retains the upstream extractor's position and URL
        # dispatch, including playlist entries and b23.tv redirects.
        engine.add_info_extractor(BiliBiliIE())
    except BaseException:
        engine.close()
        raise
    return engine


def _configure_transfer(engine: YoutubeDL, info: dict[str, Any], control: Control) -> None:
    """Use bounded, resumable requests for Bilibili's long-running CDN transfers."""
    key = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    if not key.startswith("bilibili"):
        return

    def retry_delay(n: int) -> float:
        control.wait(2 ** min(max(0, n), 3))
        # RetryManager normally sleeps after this callback. Waiting here instead
        # lets the queue wake the worker immediately when the user cancels.
        return 0.0

    engine.params.update({
        "http_chunk_size": 1024 * 1024,
        "retries": 10,
        "retry_sleep_functions": {**engine.params.get("retry_sleep_functions", {}), "http": retry_delay},
    })
    _LOG.info("Bilibili transfer: 1 MiB byte ranges, resumable partial files, up to 10 retries")


def _unsupported(error: Exception) -> bool:
    cause = getattr(error, "exc_info", (None, None, None))
    inner = cause[1] if cause else None
    return (
        isinstance(error, UnsupportedError)
        or isinstance(inner, UnsupportedError)
        or "unsupported url" in str(error).lower()
        or "no suitable extractor" in str(error).lower()
    )


def _extract(engine: YoutubeDL, url: str) -> dict[str, Any]:
    try:
        info = engine.extract_info(url, download=False)
    except (DownloadError, UnsupportedError) as exc:
        if not _unsupported(exc):
            raise
        try:
            info = engine.extract_info(url, download=False, ie_key="Generic")
        except (DownloadError, UnsupportedError) as generic_exc:
            if _unsupported(generic_exc):
                raise ValueError(
                    "This link is not supported yet. Try the video's own page, update the "
                    "download engine, or install a trusted site extractor plugin."
                ) from generic_exc
            raise
    if not isinstance(info, dict):
        raise ValueError("No playable video was found at this link.")
    return info


def _resolve_selection(engine: YoutubeDL, url: str, index: int | None) -> dict[str, Any]:
    info = _extract(engine, url)
    if index is None:
        return info
    if info.get("_type") not in {"playlist", "multi_video", "compat_list"}:
        raise ValueError("The selected video is no longer in this collection. Preview the original link again.")
    entry = next((item for item in info.get("entries") or () if isinstance(item, dict)), None)
    if entry is None:
        raise ValueError("The selected video is no longer available in this collection.")
    # The caller sets playlist_items before extraction, so this is the selected
    # entry even for lazily evaluated or very large collections.
    resolved = engine.process_ie_result(entry, download=False)
    if not isinstance(resolved, dict):
        raise ValueError("The selected video could not be read. Preview the original link again.")
    return resolved


def _thumbnail(info: dict[str, Any]) -> str:
    if info.get("thumbnail"):
        return str(info["thumbnail"])
    thumbs = [item for item in info.get("thumbnails", []) if item and item.get("url")]
    return str(thumbs[-1]["url"]) if thumbs else ""


def _site(info: dict[str, Any], url: str) -> str:
    key = str(info.get("extractor_key") or info.get("ie_key") or info.get("extractor") or "")
    names = {
        "youtube": "YouTube", "bilibili": "Bilibili", "twitter": "X", "tiktok": "TikTok",
        "instagram": "Instagram", "xiaohongshu": "RedNote", "kuaishou": "Kuaishou",
        "facebook": "Facebook", "reddit": "Reddit", "twitch": "Twitch", "vimeo": "Vimeo",
    }
    for prefix, name in names.items():
        if key.lower().startswith(prefix):
            return name
    return key.split(":")[0] if key and key.lower() != "generic" else (urlparse(url).hostname or "Other")


def _entry_url(info: dict[str, Any], fallback: str) -> str:
    reference = info.get("url") if info.get("_type") in {"url", "url_transparent"} else None
    url = str(info.get("webpage_url") or info.get("original_url") or reference or fallback)
    if not url.startswith(("http://", "https://")):
        if str(info.get("ie_key", "")).lower() == "youtube" and info.get("id"):
            return "https://www.youtube.com/watch?v=" + str(info["id"])
        return fallback
    return url


def _media(info: dict[str, Any], fallback: str) -> MediaInfo:
    url = _entry_url(info, fallback)
    heights = {
        int(fmt["height"]) for fmt in info.get("formats", [])
        if fmt.get("height") and fmt.get("vcodec") != "none" and not fmt.get("has_drm")
    }
    return MediaInfo(
        url=url,
        title=str(info.get("title") or info.get("fulltitle") or info.get("id") or "Untitled video"),
        uploader=str(info.get("uploader") or info.get("channel") or info.get("creator") or ""),
        duration=info.get("duration"),
        thumbnail=_thumbnail(info),
        site=_site(info, url),
        qualities=sorted(heights, reverse=True),
    )


def probe(
    url: str,
    options: DownloadOptions,
    control: Control | None = None,
    playlist_limit: int | None = None,
) -> MediaInfo:
    """Read metadata and flatten a complete collection into selectable entries.

    A positive explicit limit bounds previews and sets ``more_entries`` when an
    additional entry exists. No implicit cap hides the rest of a collection.
    """
    url = _validate_url(url)
    control = control or Control()
    control.checkpoint()
    if playlist_limit is not None and playlist_limit < 1:
        raise ValueError("The playlist preview limit must be greater than zero.")
    params = _base_options(options, control)
    params.update({"extract_flat": "in_playlist", "lazy_playlist": True, "noplaylist": False})
    source_url, selection = _selection(url)
    if selection is not None:
        params["playlist_items"] = str(selection)
    with _new_ydl(params) as engine:
        info = _resolve_selection(engine, source_url, selection)
        preview = _media(info, url)
        if selection is not None:
            preview.url = url
        if info.get("_type") not in {"playlist", "multi_video", "compat_list"}:
            return preview
        preview.is_playlist = True
        seen: set[str] = set()
        visited: set[str] = {url}

        def entries(collection: dict[str, Any], depth: int = 0) -> Iterator[MediaInfo]:
            if depth > 8:
                raise ValueError("This collection nests too many playlists. Open a child playlist directly.")
            collection_url = _entry_url(collection, url)
            for position, item in enumerate(collection.get("entries") or (), 1):
                control.checkpoint()
                if not isinstance(item, dict):
                    continue
                if item.get("_type") in {"playlist", "multi_video", "compat_list"}:
                    yield from entries(item, depth + 1)
                    continue
                child_url = _entry_url(item, url)
                # Some channel extractors expose their tabs as URL references.
                key = str(item.get("ie_key") or "").lower()
                if any(word in key for word in ("playlist", "youtubetab", "channel", "profile")):
                    if child_url in visited:
                        continue
                    visited.add(child_url)
                    child = _extract(engine, child_url)
                    if child.get("_type") in {"playlist", "multi_video", "compat_list"}:
                        yield from entries(child, depth + 1)
                        continue
                    item = child
                media = _media(item, url)
                if media.url in {url, collection_url} and item.get("_type") not in {"url", "url_transparent"}:
                    media.url = _selected_url(collection_url, int(item.get("playlist_index") or position))
                if media.url in seen:
                    continue
                seen.add(media.url)
                yield media

        for entry in entries(info):
            if playlist_limit is not None and len(preview.entries) >= playlist_limit:
                preview.more_entries = True
                break
            preview.entries.append(entry)
        control.checkpoint()
        if not preview.entries:
            raise ValueError("This collection has no available videos. It may be empty or require login.")
        if not preview.thumbnail:
            preview.thumbnail = preview.entries[0].thumbnail
        return preview


def _filename(options: DownloadOptions) -> str:
    template = options.filename_template.strip()
    if not template or any(char in template for char in ("/", "\\", "\x00", "\r", "\n")):
        raise ValueError("The filename template must be a filename, without folder separators.")
    if template.startswith((".", "~")) or ":" in template or ".." in template:
        raise ValueError("The filename template cannot contain parent folders or an absolute path.")
    if not template.endswith(".%(ext)s"):
        raise ValueError("The filename template must end with .%(ext)s.")
    suffix = f" [{options.audio_format.upper() if options.kind == 'audio' else options.quality}]"
    if options.clip_start is not None or options.clip_end is not None:
        start = f"{options.clip_start or 0:g}"
        end = f"{options.clip_end:g}" if options.clip_end is not None else "end"
        suffix += f" [clip {start}-{end}s]"
    return template[:-8] + suffix + ".%(ext)s"


def _download_options(options: DownloadOptions, control: Control) -> dict[str, Any]:
    params = _base_options(options, control)
    if not params.get("ffmpeg_location"):
        raise FileNotFoundError("FFmpeg is required. Run setup.ps1 or select FFmpeg in Settings.")
    if options.kind not in {"video", "audio"}:
        raise ValueError("Choose video or audio for this download.")
    if options.quality not in {"Best", *_HEIGHTS}:
        raise ValueError("Choose one of the available video qualities.")
    if options.audio_format not in _AUDIO_FORMATS:
        raise ValueError("Choose MP3, M4A, FLAC, WAV or Opus for audio.")
    if options.subtitles not in {"none", "save", "embed"}:
        raise ValueError("Choose no subtitles, save subtitles, or embed subtitles.")
    for value in (options.clip_start, options.clip_end):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Clip times must be finite, non-negative times.")
    if options.clip_end is not None and options.clip_end <= (options.clip_start or 0):
        raise ValueError("The clip end must be later than its start.")
    if options.clip_start is not None or options.clip_end is not None:
        if options.proxy.lower().startswith("socks"):
            raise ValueError("Clips need an HTTP(S) proxy. Choose an HTTP(S) proxy or download the full video.")
        if options.speed_limit_kib:
            raise ValueError("Clips use FFmpeg, which cannot honor the speed limit. Set the limit to zero or download the full video.")
    folder = Path(options.folder).expanduser() if options.folder else Path.home() / "Downloads" / "Orvilo"
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    template = _filename(options)
    if options.organize_by_site:
        template = "%(extractor_key)s/" + template
    params.update({
        "paths": {"home": str(folder)},
        "outtmpl": {"default": template},
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "lazy_playlist": True,
        "merge_output_format": "mkv",
        "writethumbnail": options.save_thumbnail or options.embed_cover,
        "allow_playlist_files": False,
    })
    postprocessors: list[dict[str, Any]] = []
    if options.kind == "audio":
        params["format"] = "bestaudio/best"
        params["final_ext"] = options.audio_format
        postprocessors.append({"key": "FFmpegExtractAudio", "preferredcodec": options.audio_format,
                               "preferredquality": "0"})
    else:
        height = _HEIGHTS.get(options.quality)
        ceiling = f"[height<=?{height}]" if height else ""
        params["format"] = f"bestvideo*{ceiling}+bestaudio/best{ceiling}/bestvideo{ceiling}"
        params["final_ext"] = "mkv"
        postprocessors.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mkv"})
    if options.subtitles != "none":
        languages = [part.strip() for part in options.subtitle_language.split(",") if part.strip()]
        params.update({"writesubtitles": True, "writeautomaticsub": options.auto_subtitles,
                       "subtitleslangs": languages or ["en"], "subtitlesformat": "srt/vtt/best"})
        postprocessors.insert(0, {"key": "FFmpegSubtitlesConvertor", "format": "srt", "when": "before_dl"})
        if options.subtitles == "embed" and options.kind == "video":
            postprocessors.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": False})
    if options.embed_metadata:
        postprocessors.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
    if options.embed_cover:
        if options.kind == "audio" and options.audio_format == "wav":
            _LOG.warning("WAV cover art is saved as a thumbnail alongside the audio file.")
        else:
            postprocessors.insert(0, {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
            postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": options.save_thumbnail})
    params["postprocessors"] = postprocessors
    if options.clip_start is not None or options.clip_end is not None:
        if options.speed_limit_kib > 0:
            raise ValueError("Clip transfers cannot enforce a byte speed limit. Set the speed limit to 0 or download the full video.")
        if options.proxy.lower().startswith("socks"):
            raise ValueError("Clip transfers cannot use SOCKS. Choose an HTTP connection setting or download the full video.")
        def ranges(info: dict[str, Any], _engine: YoutubeDL) -> list[dict[str, float]]:
            control.checkpoint()
            start = options.clip_start or 0.0
            duration = info.get("duration")
            if duration is not None and start >= duration:
                raise ValueError("The clip start is after the end of this video.")
            return [{"start_time": start, "end_time": options.clip_end if options.clip_end is not None else math.inf}]
        params["download_ranges"] = ranges
        params["force_keyframes_at_cuts"] = True
    return params


@contextmanager
def _lock_output(path: str, control: Control) -> Iterator[None]:
    """Serialize jobs targeting the same filename without blocking the UI."""
    key = str(Path(path).resolve()).casefold()
    with _PATH_LOCK:
        lock, users = _OUTPUT_LOCKS.get(key, (threading.Lock(), 0))
        _OUTPUT_LOCKS[key] = lock, users + 1
    acquired = False
    try:
        while not acquired:
            control.checkpoint()
            acquired = lock.acquire(timeout=0.2)
        yield
    finally:
        if acquired:
            lock.release()
        with _PATH_LOCK:
            _, users = _OUTPUT_LOCKS[key]
            if users == 1:
                del _OUTPUT_LOCKS[key]
            else:
                _OUTPUT_LOCKS[key] = lock, users - 1


class _FinalPath(PostProcessor):
    def __init__(self, engine: YoutubeDL, paths: list[str], control: Control) -> None:
        super().__init__(engine)
        self.paths = paths
        self.control = control

    def run(self, info: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        self.control.checkpoint()
        if info.get("filepath"):
            self.paths.append(str(info["filepath"]))
        return [], info


@contextmanager
def _ffmpeg_context(params: dict[str, Any]) -> Iterator[None]:
    """Provide yt-dlp's external-downloader discovery a thread-local location."""
    token = FFmpegPostProcessor._ffmpeg_location.set(params.get("ffmpeg_location"))
    try:
        yield
    finally:
        FFmpegPostProcessor._ffmpeg_location.reset(token)


def download(
    url: str,
    options: DownloadOptions,
    control: Control,
    progress_callback: Callable[[dict[str, Any]], None],
) -> DownloadResult:
    """Download one selected item and return only a verified final media path.

    Native HTTP/HLS partial files are retained for retry or restart. FFmpeg
    clipping, merging and conversion complete their current subprocess before
    pause/cancellation can be observed; a clipped transfer has no byte progress.
    """
    url = _validate_url(url)
    control.checkpoint()
    params = _download_options(options, control)
    source_url, selection = _selection(url)
    if selection is not None:
        params["playlist_items"] = str(selection)
        params["noplaylist"] = False
    metadata: dict[str, Any] = {"title": "Reading video…", "thumbnail": "", "site": urlparse(url).hostname or ""}
    progress_callback({"status": "metadata", "progress": 0.0, "speed": 0.0, "eta": None, **metadata})
    fractions: dict[str, float] = {}
    stream_count = 1
    last_progress = 0.0
    clipping = options.clip_start is not None or options.clip_end is not None

    def report(event: dict[str, Any]) -> None:
        nonlocal last_progress
        control.checkpoint()
        info = event.get("info_dict") or {}
        if info.get("title"):
            metadata.update(title=str(info["title"]), thumbnail=_thumbnail(info), site=_site(info, url))
        total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
        identifier = str(info.get("format_id") or event.get("filename") or "media")
        if event.get("status") == "finished":
            fractions[identifier] = 1.0
        elif total:
            fractions[identifier] = min(1.0, (event.get("downloaded_bytes") or 0) / total)
        last_progress = max(last_progress, min(100.0, sum(fractions.values()) / stream_count * 100.0))
        progress_callback({"status": "processing" if clipping else "downloading", "progress": last_progress,
                           "speed": event.get("speed") or 0.0, "eta": event.get("eta"), **metadata})

    def processing(_event: dict[str, Any]) -> None:
        control.checkpoint()
        progress_callback({"status": "processing", "progress": last_progress,
                           "speed": 0.0, "eta": None, **metadata})

    params["progress_hooks"] = [report]
    params["postprocessor_hooks"] = [processing]
    captured: list[str] = []
    with _ffmpeg_context(params), _new_ydl(params) as engine:
        info = _resolve_selection(engine, source_url, selection)
        control.checkpoint()
        if info.get("_type") in {"playlist", "multi_video", "compat_list"}:
            raise ValueError("This is a collection. Preview the link and select its videos before downloading.")
        if info.get("has_drm"):
            raise ValueError("This video is DRM-protected and cannot be downloaded by Orvilo.")
        _configure_transfer(engine, info, control)
        metadata.update(title=str(info.get("title") or "Untitled video"), thumbnail=_thumbnail(info), site=_site(info, url))
        stream_count = max(1, len(info.get("requested_formats") or []))
        progress_callback({"status": "processing" if clipping else "metadata", "progress": 0.0,
                           "speed": 0.0, "eta": None, **metadata})
        engine.add_post_processor(_FinalPath(engine, captured, control), when="after_move")
        expected_path = str(Path(engine.prepare_filename(info)).with_suffix("." + params["final_ext"]))
        with _lock_output(expected_path, control):
            finalized = engine.process_ie_result(info, download=True)
        control.checkpoint()
        if not captured and isinstance(finalized, dict):
            for item in finalized.get("requested_downloads") or [finalized]:
                if item.get("filepath"):
                    captured.append(str(item["filepath"]))
        final_path = next((Path(path).resolve() for path in reversed(captured) if Path(path).is_file()), None)
        if final_path is None:
            raise FileNotFoundError("The download finished but its final media file could not be found. Please retry.")
        size = final_path.stat().st_size
        if size == 0:
            raise ValueError("The downloaded file is empty. Please retry or choose another quality.")
        height = info.get("height")
        quality = options.audio_format.upper() if options.kind == "audio" else (f"{height}p" if height else options.quality)
        progress_callback({"status": "processing", "progress": 100.0, "speed": 0.0, "eta": None, **metadata})
        return DownloadResult(title=metadata["title"], thumbnail=metadata["thumbnail"], site=metadata["site"],
                              url=url, quality=quality, kind=options.kind, file_path=str(final_path), file_size=size)
