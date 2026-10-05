"""Transactional SQLite history with parameterized filtering and sorting."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.models import DownloadOptions, DownloadResult
from utils.paths import data_dir


class HistoryStore:
    """UI-thread history storage. Download workers never access SQLite."""

    def __init__(self, path: Path | None = None) -> None:
        target = path or data_dir() / "history.sqlite3"
        target.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(target, timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, thumbnail TEXT NOT NULL,
            site TEXT NOT NULL, url TEXT NOT NULL, quality TEXT NOT NULL,
            kind TEXT NOT NULL, file_path TEXT NOT NULL, file_size INTEGER NOT NULL,
            downloaded_at TEXT NOT NULL, options TEXT NOT NULL
        )""")
        self.connection.execute("CREATE INDEX IF NOT EXISTS downloads_date ON downloads(downloaded_at)")
        self.connection.commit()

    def add(self, result: DownloadResult, options: DownloadOptions) -> int:
        """Record one finalized download, excluding browser and proxy secrets."""
        snapshot = options.to_dict()
        for key in ("proxy", "cookie_file", "browser_profile"):
            snapshot[key] = ""
        values = (result.title, result.thumbnail, result.site, result.url, result.quality,
                  result.kind, result.file_path, result.file_size,
                  datetime.now(timezone.utc).isoformat(), json.dumps(snapshot))
        with self.connection:
            cursor = self.connection.execute("""INSERT INTO downloads
                (title, thumbnail, site, url, quality, kind, file_path, file_size, downloaded_at, options)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)
        return int(cursor.lastrowid or 0)

    def search(self, query: str = "", site: str = "", since: str = "", kind: str = "", sort: str = "newest") -> list[dict[str, Any]]:
        """Search text and optional site/date/type filters using safe SQL."""
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(title LIKE ? ESCAPE '\\' OR url LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%"] * 2)
        for key, value, operator in (("site", site, "="), ("downloaded_at", since, ">="), ("kind", kind, "=")):
            if value:
                clauses.append(f"{key} {operator} ?")
                params.append(value)
        orders = {"newest": "downloaded_at DESC, id DESC", "oldest": "downloaded_at ASC, id ASC",
                  "title": "title COLLATE NOCASE ASC", "size": "file_size DESC"}
        statement = "SELECT * FROM downloads"
        if clauses:
            statement += " WHERE " + " AND ".join(clauses)
        statement += " ORDER BY " + orders.get(sort, orders["newest"])
        result: list[dict[str, Any]] = []
        for row in self.connection.execute(statement, params):
            record = dict(row)
            record["missing"] = not Path(record["file_path"]).is_file()
            record["options"] = json.loads(record["options"])
            result.append(record)
        return result

    def sites(self) -> list[str]:
        """Return distinct sites for the history filter."""
        return [row[0] for row in self.connection.execute("SELECT DISTINCT site FROM downloads ORDER BY site")]

    def delete(self, item_id: int, delete_file: bool = False) -> None:
        """Delete a record and, only when requested, its single media file."""
        row = self.connection.execute("SELECT file_path FROM downloads WHERE id=?", (item_id,)).fetchone()
        if row and delete_file:
            Path(row["file_path"]).unlink(missing_ok=True)
        with self.connection:
            self.connection.execute("DELETE FROM downloads WHERE id=?", (item_id,))

    def clear(self, delete_files: bool = False) -> None:
        """Clear all records, optionally removing explicitly requested files."""
        if delete_files:
            for row in self.connection.execute("SELECT DISTINCT file_path FROM downloads"):
                Path(row[0]).unlink(missing_ok=True)
        with self.connection:
            self.connection.execute("DELETE FROM downloads")

    def close(self) -> None:
        """Close SQLite cleanly when the application has stopped its workers."""
        self.connection.close()
