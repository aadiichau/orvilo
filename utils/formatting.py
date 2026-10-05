"""Human-readable byte counts, time ranges and safe URL parsing."""
from __future__ import annotations

import math
import re
from urllib.parse import urlsplit


def human_bytes(value: float | int | None) -> str:
    """Format a byte count without implying precision for unknown sizes."""
    if value is None:
        return "—"
    number = max(0.0, float(value))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return "—"


def duration_text(value: float | int | None) -> str:
    """Format a duration or ETA, allowing unknown values."""
    if value is None or not math.isfinite(float(value)):
        return "—"
    total = max(0, int(value))
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def parse_time(value: str) -> float | None:
    """Parse seconds, MM:SS or HH:MM:SS. Empty text means no bound."""
    value = value.strip()
    if not value:
        return None
    try:
        parts = value.split(":")
        if not 1 <= len(parts) <= 3:
            raise ValueError
        numbers = [float(p) for p in parts]
        if any(not math.isfinite(n) or n < 0 for n in numbers):
            raise ValueError
        if len(parts) > 1 and any(n >= 60 for n in numbers[1:]):
            raise ValueError
        if any(not n.is_integer() for n in numbers[:-1]):
            raise ValueError
        return sum(n * 60 ** i for i, n in enumerate(reversed(numbers)))
    except ValueError as error:
        raise ValueError("Use seconds, MM:SS or HH:MM:SS for the clip time.") from error


def extract_urls(text: str) -> list[str]:
    """Extract distinct HTTP(S) links from pasted text, keeping input order."""
    result: list[str] = []
    for match in re.finditer(r"https?://[^\s<>\"']+", text, re.IGNORECASE):
        candidate = match.group().rstrip(".,;!)]}")
        try:
            parsed = urlsplit(candidate)
            valid = parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
            if valid and candidate not in result:
                result.append(candidate)
        except ValueError:
            continue
    return result
