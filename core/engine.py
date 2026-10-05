"""Restart-safe updates from verified, pure-Python wheels on official PyPI.

An update never reloads code while downloads are active. A tiny atomic pointer
selects an immutable release directory the next time Orvilo starts.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import threading
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from utils.paths import data_dir

LOG = logging.getLogger(__name__)
_UPDATE_LOCK = threading.Lock()
_MAX_WHEEL = 50 * 1024 * 1024


def _fetch(url: str, limit: int = _MAX_WHEEL) -> bytes:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {"pypi.org", "files.pythonhosted.org"}:
        raise ValueError("The update source is not official PyPI.")
    request = Request(url, headers={"User-Agent": "Orvilo/1.0 engine-updater", "Accept": "application/json, application/octet-stream"})
    with urlopen(request, timeout=45) as response:
        destination = urlsplit(response.url)
        if destination.scheme != "https" or destination.hostname not in {"pypi.org", "files.pythonhosted.org"}:
            raise ValueError("The update redirected to an unexpected source.")
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("The update is unexpectedly large.")
    return payload


def _metadata(package: str, version: str = "") -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9._+-]+", package + version):
        raise ValueError("Invalid engine release identifier.")
    part = f"/{version}" if version else ""
    return json.loads(_fetch(f"https://pypi.org/pypi/{package}{part}/json", 8 * 1024 * 1024))


def _compatible_python(metadata: dict[str, Any]) -> None:
    requires = metadata["info"].get("requires_python")
    current = ".".join(map(str, sys.version_info[:3]))
    if requires and not SpecifierSet(requires).contains(current):
        raise ValueError("This engine release needs a newer Python runtime. Rebuild Orvilo with a newer Python version.")


def _applicable_requirements(metadata: dict[str, Any]) -> list[Requirement]:
    environment = default_environment()
    environment["extra"] = "default"
    result = []
    for value in metadata["info"].get("requires_dist") or []:
        requirement = Requirement(value)
        if requirement.marker is None or requirement.marker.evaluate(environment):
            result.append(requirement)
    return result


def _check_dependencies(metadata: dict[str, Any], updated: set[str]) -> None:
    for requirement in _applicable_requirements(metadata):
        if canonicalize_name(requirement.name) in updated:
            continue
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ValueError(f"The new engine needs {requirement.name}. Run setup and build again to update the application dependencies.") from exc
        if requirement.specifier and not requirement.specifier.contains(installed, prereleases=True):
            raise ValueError(f"The new engine needs a newer {requirement.name}. Run setup and build again to update the application dependencies.")


def _select_ejs(engine: dict[str, Any]) -> dict[str, Any]:
    requirements = [item for item in _applicable_requirements(engine) if canonicalize_name(item.name) == "yt-dlp-ejs"]
    constraint = requirements[0].specifier if requirements else SpecifierSet()
    latest = _metadata("yt-dlp-ejs")
    if constraint.contains(latest["info"]["version"], prereleases=False):
        return latest
    versions = sorted((Version(value) for value in latest["releases"] if constraint.contains(value, prereleases=False)), reverse=True)
    for version in versions:
        metadata = _metadata("yt-dlp-ejs", str(version))
        if any(not item.get("yanked") and item["filename"].endswith("-none-any.whl") for item in metadata["urls"]):
            return metadata
    raise ValueError("A compatible JavaScript solver is not available yet. Please try updating later.")


def _extract_wheel(metadata: dict[str, Any], stage: Path, module: str) -> dict[str, str]:
    _compatible_python(metadata)
    candidates = [item for item in metadata["urls"] if item.get("packagetype") == "bdist_wheel" and item["filename"].endswith("-none-any.whl") and not item.get("yanked")]
    if not candidates:
        raise ValueError("This release has no compatible Python wheel. Please try updating later.")
    wheel = candidates[0]
    payload = _fetch(wheel["url"])
    expected = wheel["digests"]["sha256"]
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("Update verification failed. Nothing was installed; please try again.")
    hashes: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 200 * 1024 * 1024:
            raise ValueError("The expanded update is unexpectedly large.")
        for item in archive.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or ":" in item.filename:
                raise ValueError("The update contains an unsafe path.")
            if not path.parts or item.is_dir():
                continue
            # Wheels may also carry pip-only share/man/completion files. They
            # are neither imports nor dependencies of the embedded library.
            if path.parts[0].startswith(module + "-") and path.parts[0].endswith(".data"):
                continue
            if path.parts[0] != module and not (path.parts[0].startswith(module + "-") and path.parts[0].endswith(".dist-info")):
                raise ValueError("The wheel contains unexpected executable content.")
            if (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("The wheel contains a symbolic link.")
            destination = stage.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = archive.read(item)
            destination.write_bytes(content)
            hashes[item.filename] = hashlib.sha256(content).hexdigest()
    if not (stage / module / "__init__.py").is_file():
        raise ValueError("The update is missing its main package.")
    return hashes


def engine_version() -> str:
    """Return the version used by the current process, not a staged update."""
    try:
        from yt_dlp.version import __version__
        return __version__
    except ImportError:
        return "unavailable"


def activate_engine() -> str:
    """Activate a validated overlay at startup, falling back to bundled code."""
    if "yt_dlp" in sys.modules:
        return engine_version()
    base = data_dir() / "engine"
    pointer = base / "current.json"
    if not pointer.is_file():
        return engine_version()
    overlay: Path | None = None
    try:
        record = json.loads(pointer.read_text(encoding="utf-8"))
        release = record["release"]
        if not re.fullmatch(r"[A-Za-z0-9._+-]+", release):
            raise ValueError("Invalid release path")
        overlay = base / "releases" / release
        manifest = json.loads((overlay / "manifest.json").read_text(encoding="utf-8"))
        for relative, digest in manifest["files"].items():
            candidate = overlay.joinpath(*PurePosixPath(relative).parts).resolve()
            if not candidate.is_relative_to(overlay.resolve()):
                raise ValueError("Unsafe engine file")
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != digest:
                raise ValueError("Engine file failed verification")
        sys.path.insert(0, str(overlay))
        importlib.invalidate_caches()
        importlib.import_module("yt_dlp")
        LOG.info("Activated engine %s", manifest["version"])
    except Exception:
        LOG.exception("The updated engine could not load; using the bundled engine")
        if overlay is not None and str(overlay) in sys.path:
            sys.path.remove(str(overlay))
        for module in list(sys.modules):
            if module == "yt_dlp" or module.startswith("yt_dlp.") or module == "yt_dlp_ejs" or module.startswith("yt_dlp_ejs."):
                sys.modules.pop(module, None)
        importlib.invalidate_caches()
    return engine_version()


def update_engine() -> str:
    """Stage official yt-dlp and matching EJS wheels; return a friendly result."""
    if not _UPDATE_LOCK.acquire(blocking=False):
        raise ValueError("An engine update is already running.")
    stage: Path | None = None
    try:
        engine = _metadata("yt-dlp")
        _compatible_python(engine)
        version = engine["info"]["version"]
        current = engine_version()
        if current != "unavailable" and Version(version) <= Version(current):
            return f"yt-dlp {current} is already up to date."
        ejs = _select_ejs(engine)
        updated = {"yt-dlp", "yt-dlp-ejs"}
        _check_dependencies(engine, updated)
        _check_dependencies(ejs, updated)
        base = data_dir() / "engine"
        releases = base / "releases"
        releases.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases))
        hashes = _extract_wheel(engine, stage, "yt_dlp")
        hashes.update(_extract_wheel(ejs, stage, "yt_dlp_ejs"))
        manifest = {"version": version, "ejs_version": ejs["info"]["version"], "files": hashes}
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        release = f"{version}-{stage.name.removeprefix('.staging-')}"
        destination = releases / release
        stage.rename(destination)
        stage = None
        pointer_temp = base / "current.new.json"
        with pointer_temp.open("w", encoding="utf-8") as handle:
            json.dump({"release": release, "version": version}, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(pointer_temp, base / "current.json")
        LOG.info("Staged yt-dlp %s with EJS %s", version, ejs["info"]["version"])
        return f"yt-dlp {version} is ready. Restart Orvilo to use the update."
    except ValueError:
        raise
    except Exception as exc:
        LOG.exception("Engine update failed")
        raise ValueError("The engine update could not be completed. Check your connection and try again; the installed engine is unchanged.") from exc
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        _UPDATE_LOCK.release()
