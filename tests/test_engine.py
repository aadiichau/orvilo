"""Updater tests verify hashes, archive boundaries and atomic activation."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from core import engine
from utils.paths import data_dir


def wheel(module="yt_dlp", unsafe=False):
    """Create a minimal, deterministic pure-Python wheel in memory."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr(f"{module}/__init__.py", "")
        bundle.writestr(f"{module}/version.py", "__version__ = '99.0'\n")
        bundle.writestr(f"{module}-99.0.data/data/share/man/man1/engine.1", "Manual data unused by the library")
        if unsafe:
            bundle.writestr("../escaped.py", "")
    return stream.getvalue()


def metadata(module="yt_dlp", payload=None):
    """Describe a release using the same fields as the PyPI API."""
    data = payload or wheel(module)
    return {"info": {"version": "99.0", "requires_python": ">=3.11", "requires_dist": []},
            "urls": [{"packagetype": "bdist_wheel", "filename": f"{module}-99.0-py3-none-any.whl",
                      "url": f"https://files.pythonhosted.org/{module}.whl", "digests": {"sha256": hashlib.sha256(data).hexdigest()}}]}


def test_update_rejects_bad_hash_and_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_fetch", lambda _url: b"tampered")
    with pytest.raises(ValueError, match="verification"):
        engine._extract_wheel(metadata(), tmp_path / "stage", "yt_dlp")
    payload = wheel(unsafe=True)
    monkeypatch.setattr(engine, "_fetch", lambda _url: payload)
    with pytest.raises(ValueError, match="unsafe path"):
        engine._extract_wheel(metadata(payload=payload), tmp_path / "stage", "yt_dlp")
    assert not (tmp_path / "escaped.py").exists()


def test_staged_update_activates_only_on_next_process(monkeypatch):
    monkeypatch.setattr(engine, "engine_version", lambda: "1.0")
    monkeypatch.setattr(engine, "_metadata", lambda _name: metadata())
    monkeypatch.setattr(engine, "_select_ejs", lambda _info: metadata("yt_dlp_ejs"))
    monkeypatch.setattr(engine, "_fetch", lambda url: wheel("yt_dlp_ejs" if "yt_dlp_ejs" in url else "yt_dlp"))
    result = engine.update_engine()
    assert "Restart" in result
    pointer = data_dir() / "engine" / "current.json"
    record = json.loads(pointer.read_text())
    assert record["version"] == "99.0"
    script = "from core.engine import activate_engine; print(activate_engine())"
    process = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                             capture_output=True, text=True, check=True, timeout=30)
    assert process.stdout.strip() == "99.0"
    saved = pointer.read_bytes()
    monkeypatch.setattr(engine, "_fetch", lambda _url: b"bad signature")
    with pytest.raises(ValueError):
        engine.update_engine()
    assert pointer.read_bytes() == saved
