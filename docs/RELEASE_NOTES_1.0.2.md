# Orvilo 1.0.2

**Video, saved beautifully.**

[Download for Windows](https://github.com/aadiichau/orvilo/releases/latest) ·
[Back to Orvilo](../README.md)

## Downloads

| File | Choose this if… |
| --- | --- |
| `Orvilo-Setup-1.0.2.exe` | You want the installer, a Start menu entry, and optional desktop shortcut. |
| `Orvilo-1.0.2-Windows-x64.exe` | You want a portable application without installation. |
| `Orvilo-1.0.2-source.zip` | You want to inspect, modify, or build the project. |
| `SHA256SUMS.txt` | You want to check downloaded file integrity. |

The Windows executables target 64-bit Windows 10/11 and include Python, Qt, and
the download engine. On first launch, the app offers a verified download of its
video tools directly from their publisher. The executables are unsigned.

## What changed

- A Windows installer and portable build are now available for the first public
  release, with a one-time verified video-tools download on first launch.
- Bilibili transfers now retain the signed backup URLs supplied for each DASH
  stream. After a recoverable transfer failure, Orvilo resumes the same stream
  on an available backup server.
- Bilibili full downloads use bounded HTTP ranges and cancellable retry delays
  to recover from truncated responses without discarding existing partial files.
- Retried jobs use current cookie, proxy, and runtime settings.
- Transfer failures remain separate from disk errors and user cancellation.

To update, quit the old app from its tray menu and run the new installer or
portable executable. Settings, history, and the queue remain in the same local
data folder. Keep partial downloads in place and use **Queue → Retry**.

## Validation

The download implementation was checked on Windows 11 x64 with **51 passing
automated tests**. Coverage includes settings, history, queue controls and
recovery, real media conversion, extraction, updates, the Qt workflow, and HTTP
recovery with byte-for-byte integrity checks.

The packaged application rendered all four pages in dark and light themes and
completed seven local media checks: video, five audio formats, and a short clip.
The Bilibili fix also completed a live 1080p transfer with audio; decoded samples
at the beginning, middle, and end passed. These checks do not establish
compatibility with every third-party URL or browser session. Windows 10 was not
independently tested.

## Known limits

Site support follows yt-dlp and can change. Private or age-restricted material
requires a session that already has access. DRM-protected services are out of
scope. Kuaishou currently uses the generic extractor fallback. Clips and FFmpeg
processing have pause, cancellation, proxy, and rate-limit constraints described
in the [quick guide](GUIDE.md#transfer-and-format-details).

Original Orvilo code uses the MIT license. The bundled Windows app is distributed
under GPL-3.0-or-later, and dependencies retain their own licenses. See
[third-party notices](../assets/THIRD_PARTY_NOTICES.md) and
[dependency source and rebuild information](../DEPENDENCY_SOURCES.md).
