"""Offscreen fixtures keep tests independent of the user's desktop and data."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    """Share one Qt event loop across tests."""
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    """Keep settings, queue and history separate in every test."""
    monkeypatch.setenv("ORVILO_DATA_DIR", str(tmp_path / "data"))
