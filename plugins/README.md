# Local site extractors

Orvilo uses yt-dlp's built-in extractors first after any explicitly installed
local plug-ins. Its generic extractor also discovers ordinary direct-media links
and embedded players. An unsupported URL gets a clear message after the generic
fallback; authentication failures are preserved so the app can suggest cookies.

Install your own extractor by putting a Python file in
`%LOCALAPPDATA%\Orvilo\plugins`. Each module must export an `EXTRACTORS` list of
concrete `yt_dlp.extractor.common.InfoExtractor` subclasses. Give every class a
unique name ending in `IE`, a narrow `_VALID_URL` regular expression, and an
implementation of `_real_extract(url)` returning yt-dlp's information dictionary.
Include `id`, `title`, and either a direct media `url` or a `formats` list.

The implementation below is a complete optional extractor for HTTPS links to
direct MP4, WebM, MOV, M4V, MKV, MP3, M4A, FLAC, WAV and Opus files. yt-dlp's
generic extractor already handles these; this small implementation demonstrates
the extension interface without needing an account or a made-up website.
Save it as `direct_media.py` in the directory above to install it.

```python
"""Optional direct-media extractor for Orvilo."""
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from yt_dlp.extractor.common import InfoExtractor


class OrviloDirectMediaIE(InfoExtractor):
    IE_NAME = "orvilo:direct"
    _VALID_URL = r"https://[^?#]+\.(?P<id>mp4|webm|mov|m4v|mkv|mp3|m4a|flac|wav|opus)(?:[?#].*)?$"

    def _real_extract(self, url: str) -> dict:
        """Return a downloadable direct URL and a readable filename title."""
        path = PurePosixPath(unquote(urlsplit(url).path))
        extension = path.suffix[1:].lower()
        info = {
            "id": path.stem,
            "title": path.stem.replace("_", " "),
            "url": url,
            "ext": extension,
        }
        if extension in {"mp3", "m4a", "flac", "wav", "opus"}:
            info["vcodec"] = "none"
        return info


EXTRACTORS = [OrviloDirectMediaIE]
```

Modules are loaded locally, in alphabetical order, before built-ins. They are
reloaded on the next preview or download after their file timestamp changes.
Restart after changing a helper module imported by your extractor. Do not reuse a
built-in extractor class name. An invalid plug-in produces a readable error that
identifies its file, and the full diagnostic stays in the local log.

Plug-ins execute Python with your Windows user's permissions. Install only code
you trust. Orvilo does not fetch, run or update third-party extractors remotely.
Extractors must not implement DRM bypass or send telemetry.

For a real website, use yt-dlp's extraction helpers such as `_download_webpage`,
`_download_json`, `_search_json`, `_extract_m3u8_formats_and_subtitles`, and
`playlist_result`. These reuse the user's proxy, cookie jar and request settings.
Use `raise_login_required` for login failures and `report_drm` for protected
streams. Collection extractors should yield `url_result` entries with stable
webpage URLs, titles and thumbnails so the playlist picker stays fast.

The [yt-dlp extractor development guide](https://github.com/yt-dlp/yt-dlp#adding-support-for-a-new-site)
and [InfoExtractor source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/common.py)
describe the supported metadata fields and helpers.
