"""Bounded local diagnostics with URL and credential redaction."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from utils.paths import data_dir


class RedactingFormatter(logging.Formatter):
    """Keep sensitive links and cookie header values out of persistent logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format and redact the final message, including exception text."""
        output = super().format(record)
        output = re.sub(r"https?://[^\s\"'<>]+", "[URL]", output)
        return re.sub(r"(?i)(cookie|authorization|password)(\s*[:=]\s*).*", r"\1\2[redacted]", output)


def configure_logging() -> None:
    """Enable a rotating, local-only application log."""
    log_folder = data_dir() / "logs"
    log_folder.mkdir(exist_ok=True)
    handler = RotatingFileHandler(log_folder / "orvilo.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
