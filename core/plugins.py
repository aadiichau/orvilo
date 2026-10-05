"""Load explicitly installed local yt-dlp extractor classes."""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import sys
import threading
from pathlib import Path
from types import ModuleType

from yt_dlp.extractor.common import InfoExtractor

from utils.paths import data_dir

_LOG = logging.getLogger(__name__)
_LOCK = threading.Lock()
_CACHE: dict[Path, tuple[int, ModuleType]] = {}


def load_extractors() -> list[type[InfoExtractor]]:
    """Return extractor classes exported by trusted user-installed Python files.

    Each module must export an ``EXTRACTORS`` list of InfoExtractor subclasses.
    Nothing is fetched remotely. Plug-ins run with the app's permissions.
    """
    directory = data_dir() / "plugins"
    directory.mkdir(parents=True, exist_ok=True)
    result: list[type[InfoExtractor]] = []
    with _LOCK:
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                modified = path.stat().st_mtime_ns
                cached = _CACHE.get(path)
                if cached is not None and cached[0] == modified:
                    module = cached[1]
                else:
                    name = "orvilo_site_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
                    spec = importlib.util.spec_from_file_location(name, path)
                    if spec is None or spec.loader is None:
                        raise ValueError("Python could not create a module loader")
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[name] = module
                    try:
                        spec.loader.exec_module(module)
                    except BaseException:
                        sys.modules.pop(name, None)
                        raise
                    _CACHE[path] = (modified, module)
                classes = getattr(module, "EXTRACTORS", None)
                if not isinstance(classes, (list, tuple)) or not classes:
                    raise ValueError("EXTRACTORS must be a non-empty list")
                for cls in classes:
                    if not isinstance(cls, type) or not issubclass(cls, InfoExtractor):
                        raise ValueError("EXTRACTORS must contain InfoExtractor subclasses")
                    if cls is InfoExtractor:
                        raise ValueError("Export a concrete extractor, not InfoExtractor itself")
                    result.append(cls)
            except Exception as exc:
                _LOG.exception("Could not load site plugin %s", path.name)
                raise ValueError(
                    f"A site plugin could not be loaded: {path.name}. "
                    "Correct that file or remove it from the plugins folder and retry."
                ) from exc
    return result
