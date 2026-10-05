"""Translate engine and system failures into actionable user messages."""
from __future__ import annotations


def friendly_error(error: BaseException | str) -> str:
    """Map technical failures to short messages without exposing tracebacks."""
    raw = str(error)
    message = raw.lower()
    mappings = (
        (("drm", "protected content", "unplayable"), "This stream is protected by DRM and cannot be downloaded."),
        (("private video", "video is private", "private content"), "This video is private. If you have access, enable cookies in Settings."),
        (("cookies database", "could not copy", "decrypt", "dpapi"), "Browser cookies could not be read. Close the browser or use Firefox or a Netscape cookies file in Settings."),
        (("sign in", "login", "log in", "age-restricted", "age restricted", "authentication", "cookies"), "Login required: enable cookies in Settings, then try again."),
        (("unsupported url", "no suitable extractor", "not supported yet", "no video formats", "unable to extract"), "This link is not supported yet, or the site changed. Update yt-dlp in Settings and try again."),
        (("geo", "not available in your country", "not available in your region"), "This video is not available in your region."),
        (("404", "has been removed", "video unavailable", "not found"), "This video is unavailable or has been removed."),
        (("429", "too many requests"), "The site is limiting requests. Wait a little, then retry with fewer parallel downloads."),
        (("403", "forbidden"), "The site refused access. Refresh the link, enable cookies, or update yt-dlp in Settings."),
        (("ffmpeg", "ffprobe"), "FFmpeg is needed for this format. Run setup or choose its folder in Settings."),
        (("javascript runtime", "js runtime", "challenge", "ejs"), "The site's JavaScript check could not finish. Update yt-dlp and check the Deno path in Settings."),
        (("requested format", "format is not available"), "That quality is unavailable. Choose Best or a lower quality."),
        (("no space", "disk full", "errno 28"), "There is not enough free space in the download folder."),
        (("permission denied", "access is denied", "winerror 5"), "Orvilo cannot write to that folder. Choose another download folder in Settings."),
        (("bytes read", "more expected", "content too short", "incomplete read", "incompleteread"), "The video server interrupted the transfer. Your partial download is saved; retry to continue."),
        (("timed out", "timeout", "connection", "network", "resolve", "ssl", "certificate", "proxy"), "Could not reach the site. Check your connection and proxy settings, then retry."),
    )
    for needles, text in mappings:
        if any(needle in message for needle in needles):
            return text
    if isinstance(error, ValueError) and raw and len(raw) < 220 and "\n" not in raw:
        return raw
    return "The download could not finish. Try again or update yt-dlp in Settings. More details are in the local log."
