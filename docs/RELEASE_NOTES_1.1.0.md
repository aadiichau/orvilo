# Orvilo 1.1.0

**Choose a video format. Bring it into your editor.**

[Download for Windows](https://github.com/aadiichau/orvilo/releases/latest) ·
[Back to Orvilo](../README.md)

## What changed

- A visible video-format picker: MP4, MOV/H.264, MOV/ProRes 422, MKV, and WebM.
- MP4 is the default for new downloads. MP4 and MOV/H.264 use H.264/AAC,
  8-bit 4:2:0 pixels, and a constant frame rate for editor compatibility.
- ProRes 422 MOV uses 10-bit 4:2:2 video with PCM audio for editing.
- MP4, MOV/H.264, and WebM tone-map HDR sources to SDR. MKV retains original
  codecs, while the ProRes profile retains HDR color tags.
- Every converted format uses its own filename, so different profiles can be
  queued together. Format choices survive restarts and are kept on retries.
- Older queue/history snapshots retain their original MKV behavior.
- Subtitle and artwork handling follows the selected container. WebM captions
  use WebVTT; ProRes and WebM artwork is saved beside the video.

## Install or update

Quit the old app from its tray menu, then run **Orvilo-Setup-1.1.0.exe**.
Alternatively, run **Orvilo-1.1.0-Windows-x64.exe** without installation.
Settings, history, and queue stay in the same local data folder. Existing FFmpeg
settings are reused; first-time users can choose **Install FFmpeg** in the app.

Windows 10/11 x64 is the supported target. The builds are unsigned. The release
includes complete source, dependency notices, corresponding-source information,
and SHA-256 checksums beside the Windows downloads.

## Validation

**67 automated tests passed on Windows 11 x64.** Tests check real video/audio codecs, pixel formats, constant frame
rates, duration, and decoding for the converted profiles. Coverage also includes
a VP9/Opus source converted to H.264/AAC, silent video with odd dimensions, HDR
tone mapping, embedded captions/artwork, queue collisions, and legacy settings.
Cancellation and conversion failures retain the downloaded source and any
previously saved output rather than publishing a partial conversion.

Packaged verification exercises all five video profiles, five audio formats,
and an MP4 clip, plus the four app pages in both themes. The installer is checked
for installation, launch, and removal in an isolated folder.

Adobe lists H.264, MP4, MOV, and ProRes in its
[supported format guide](https://helpx.adobe.com/premiere/desktop/organize-media/import-files/supported-file-formats.html).
The files are verified with FFprobe and FFmpeg decoding; importing them in an
installed copy of Premiere has not been independently tested. Windows 10 has
not been independently tested.

## Format tradeoffs

MP4, MOV, ProRes, and WebM perform a real encode, which takes additional time.
ProRes can produce very large files. A conversion cannot restore lost source
quality. The recommended profile for general Premiere imports is **MP4 · Premiere**.
Choose **Save .srt file** if you want editable captions in your editor.

MKV preserves the downloaded codecs and remains available for archival use.
Site access still depends on yt-dlp and your browser session. DRM-protected
streams are outside the app's scope. See the [quick guide](GUIDE.md) for details.

Original code is MIT licensed; the bundled application is distributed under
GPL-3.0-or-later. See [dependency sources](../DEPENDENCY_SOURCES.md) and
[third-party notices](../assets/THIRD_PARTY_NOTICES.md).
