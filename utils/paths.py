"""Resolve resources and per-user local application data."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def asset_path(relative: str) -> Path:
    """Resolve a bundled asset in development and PyInstaller builds."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / "assets" / relative


def data_dir() -> Path:
    """Return the writable local data directory, creating it as needed."""
    override = os.environ.get("ORVILO_DATA_DIR")
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    result = Path(override) if override else base / "Orvilo"
    result.mkdir(parents=True, exist_ok=True)
    return result


def app_root() -> Path:
    """Return the unpacked application root for bundled helper executables."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
