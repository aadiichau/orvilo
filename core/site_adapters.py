"""Small upstream extensions that preserve a site's own recovery information."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.extractor.bilibili import BiliBiliIE as UpstreamBiliBiliIE
from yt_dlp.networking.exceptions import RequestError
from yt_dlp.utils import DownloadError

_LOG = logging.getLogger(__name__)


def _http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"https", "http"} and bool(parsed.hostname) and not parsed.username


class BiliBiliIE(UpstreamBiliBiliIE):
    """Keep Bilibili's signed backup URLs for the exact same DASH stream."""

    def extract_formats(self, play_info: dict[str, Any]) -> list[dict[str, Any]]:
        """Extend upstream formats without changing quality, codecs or URL signing."""
        formats = super().extract_formats(play_info)
        mirrors: dict[str, list[str]] = {}

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                primary = value.get("baseUrl") or value.get("base_url")
                backups = value.get("backupUrl") or value.get("backup_url") or []
                if _http_url(primary) and isinstance(backups, list):
                    mirrors[primary] = list(dict.fromkeys(
                        backup for backup in backups if _http_url(backup) and backup != primary
                    ))
                for child in value.values():
                    if isinstance(child, (dict, list)):
                        visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit((play_info or {}).get("dash", {}))
        for fmt in formats:
            if backups := mirrors.get(fmt.get("url", "")):
                fmt["_orvilo_backup_urls"] = backups
        return formats


def _retryable(error: BaseException) -> bool:
    message = str(error).lower()
    if any(word in message for word in ("no space", "disk full", "permission denied", "access is denied", "winerror 5")):
        return False
    return any(word in message for word in (
        "bytes read", "more expected", "content too short", "incomplete", "timed out",
        "timeout", "connection reset", "connection aborted", "remote end closed",
        "http error 403", "http error 404", "http error 429", "http error 5",
        "unable to download video data", "name resolution", "getaddrinfo failed",
    ))


class ResilientYoutubeDL(YoutubeDL):
    """Resume failed native HTTP transfers on a site-provided identical mirror."""

    def dl(self, name: str, info: dict[str, Any], subtitle: bool = False,
           test: bool = False) -> tuple[bool, bool]:
        """Try signed backup endpoints only after a recoverable transport failure."""
        backups = info.get("_orvilo_backup_urls") or []
        native_http = info.get("protocol") in {None, "http", "https"}
        if (subtitle or test or not native_http or info.get("requested_formats")
                or info.get("section_start") is not None or info.get("section_end") is not None
                or not backups):
            return super().dl(name, info, subtitle=subtitle, test=test)
        urls = list(dict.fromkeys([info["url"], *(url for url in backups if _http_url(url))]))
        original_retries = self.params.get("retries", 10)
        # A consistently broken endpoint should not delay trying its backup.
        self.params["retries"] = min(original_retries, 3)
        try:
            for position, url in enumerate(urls):
                if position:
                    self.to_screen("[download] Resuming from an alternate video server…")
                    _LOG.info("Resuming the same media stream on site-provided backup %d", position)
                try:
                    return super().dl(name, {**info, "url": url}, subtitle=subtitle, test=test)
                except (DownloadError, RequestError) as error:
                    if position == len(urls) - 1 or not _retryable(error):
                        raise
        finally:
            self.params["retries"] = original_retries
        raise DownloadError("The video servers could not complete the transfer.")
