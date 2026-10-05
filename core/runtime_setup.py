"""Install the publisher's verified FFmpeg release locally, without elevation."""
from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from threading import Event
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4
import zipfile

from utils.paths import data_dir

VERSION = "9.0.2"
ARCHIVE_URL = "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip"
CHECKSUM_URL = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip.sha256"
ARCHIVE_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
_ALLOWED_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "www.gyan.dev"}
_ARCHIVE_LIMIT = 200 * 1024 * 1024
Progress = Callable[[int, str], None]


class SetupCancelled(Exception):
    """The user stopped runtime setup before publication."""


def _check_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise SetupCancelled("Setup cancelled.")


def _download(url: str, destination: Path, limit: int, progress: Progress, cancel: Event) -> str:
    """Stream an HTTPS artifact, bound its size, and calculate its checksum."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
        raise ValueError("The download source is not an approved FFmpeg publisher.")
    _check_cancel(cancel)
    request = Request(url, headers={"User-Agent": "Orvilo runtime setup", "Accept-Encoding": "identity"})
    digest = hashlib.sha256()
    count = 0
    with urlopen(request, timeout=20) as response, destination.open("wb") as output:
        final = urlparse(response.url)
        if final.scheme != "https" or final.hostname not in _ALLOWED_HOSTS:
            raise ValueError("The download redirected away from an approved secure publisher.")
        total = int(response.headers.get("Content-Length") or 0)
        if total > limit:
            raise ValueError("The FFmpeg download is unexpectedly large.")
        while chunk := response.read(256 * 1024):
            _check_cancel(cancel)
            count += len(chunk)
            if count > limit:
                raise ValueError("The FFmpeg download is unexpectedly large.")
            digest.update(chunk)
            output.write(chunk)
            if limit > 1024 * 1024:
                percent = min(89, int(count * 89 / total)) if total else 0
                size = f"{count / (1024 * 1024):.1f} MB"
                progress(percent, f"Downloading FFmpeg · {size}")
        if total and count != total:
            raise ValueError("The FFmpeg download was interrupted. Please try again.")
    _check_cancel(cancel)
    return digest.hexdigest()


def _extract(archive: Path, destination: Path, cancel: Event) -> dict[str, str]:
    """Extract only two unique Windows executables and the publisher's notices."""
    destination.mkdir()
    hashes: dict[str, str] = {}
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.orig_filename or ":" in entry.filename:
                raise ValueError("The FFmpeg archive contains an unsafe path.")
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("The FFmpeg archive contains an unsafe link.")
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            matches = [entry for entry in entries if PurePosixPath(entry.filename).name.lower() == name and not entry.is_dir()]
            if len(matches) != 1 or not 2 <= matches[0].file_size <= 200 * 1024 * 1024:
                raise ValueError("The FFmpeg archive is missing a required Windows tool.")
            digest = hashlib.sha256()
            count = 0
            with bundle.open(matches[0]) as source, (destination / name).open("wb") as output:
                while chunk := source.read(256 * 1024):
                    _check_cancel(cancel)
                    count += len(chunk)
                    if count > 200 * 1024 * 1024:
                        raise ValueError("An FFmpeg tool is unexpectedly large.")
                    digest.update(chunk)
                    output.write(chunk)
            with (destination / name).open("rb") as stream:
                if stream.read(2) != b"MZ":
                    raise ValueError("The FFmpeg package is not a Windows executable.")
            hashes[name] = digest.hexdigest()
        notices = destination / "licenses"
        notices.mkdir()
        for entry in entries:
            leaf = PurePosixPath(entry.filename).name
            if not entry.is_dir() and any(token in leaf.lower() for token in ("license", "copying", "readme")):
                if entry.file_size > 4 * 1024 * 1024:
                    raise ValueError("An FFmpeg notice is unexpectedly large.")
                safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", leaf)
                (notices / safe_name).write_bytes(bundle.read(entry))
        if not any(notices.iterdir()):
            raise ValueError("The FFmpeg package is missing its license notices.")
    return hashes


def install_ffmpeg(progress: Progress, cancel: Event) -> Path:
    """Install a verified, pinned FFmpeg package and return its executable folder.

    Downloads go directly from the publisher to this computer. No administrator
    privileges are required. A cancelled or invalid download never replaces an
    installed runtime; successful publication uses one atomic directory rename.
    """
    runtime = data_dir() / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    progress(0, "Connecting to the FFmpeg publisher…")
    with tempfile.TemporaryDirectory(prefix=".setup-", dir=runtime) as temporary:
        stage = Path(temporary)
        checksum_path = stage / "checksum.txt"
        _download(CHECKSUM_URL, checksum_path, 16384, progress, cancel)
        match = re.search(r"\b[0-9a-fA-F]{64}\b", checksum_path.read_text(encoding="utf-8"))
        if not match or match.group(0).lower() != ARCHIVE_SHA256:
            raise ValueError("The publisher's FFmpeg checksum changed. Update Orvilo before installing.")
        archive = stage / "ffmpeg.zip"
        actual = _download(ARCHIVE_URL, archive, _ARCHIVE_LIMIT, progress, cancel)
        if actual != ARCHIVE_SHA256:
            raise ValueError("FFmpeg verification failed. Nothing was installed. Please try again.")
        progress(91, "Verified download. Installing the media tools…")
        package = stage / "package"
        hashes = _extract(archive, package, cancel)
        record = {"version": VERSION, "publisher": "Gyan Doshi", "url": ARCHIVE_URL,
                  "archive_sha256": actual, "sha256": hashes,
                  "source": "https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2"}
        (package / "versions.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        _check_cancel(cancel)
        installed = runtime / f"ffmpeg-{VERSION}-{uuid4().hex[:8]}"
        os.replace(package, installed)
    progress(100, "FFmpeg is ready. You're all set to download.")
    return installed
