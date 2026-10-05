# Build and extend Orvilo

[← Back to Orvilo](../README.md) · [User guide](GUIDE.md)

Orvilo uses Python 3.11+, PySide6, yt-dlp as a Python library, FFmpeg, SQLite for
history, and JSON for preferences. The supported build target is 64-bit Windows
10/11. PyInstaller builds for its host platform; this is not a cross-compilation
recipe.

## One-command setup

Install [64-bit Python 3.11 or later](https://www.python.org/downloads/windows/)
with the Python launcher. Clone or extract the source into a writable folder,
open PowerShell in that folder, and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup creates `.venv`, installs `requirements.txt`, renders the logo as PNG and
a six-size Windows ICO, and downloads checksum-verified FFmpeg/FFprobe and Deno
into `assets/runtime`. No system PATH change or administrator access is needed.
Deno and yt-dlp-ejs provide YouTube JavaScript challenge support.

Launch the application:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1
```

To install Python packages without fetching video tools:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -SkipRuntime
```

For manual FFmpeg setup, choose an x64 Windows build linked from
[ffmpeg.org](https://ffmpeg.org/download.html#build-windows). Copy both
`ffmpeg.exe` and `ffprobe.exe` from its `bin` folder to `assets/runtime`, or
select that folder in Settings. Install Deno from its
[official releases](https://github.com/denoland/deno/releases) and copy
`deno.exe` into `assets/runtime`, or select it in Settings.

## Build for Windows

Run setup, then build:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

The output is `dist/Orvilo.exe`. Python, Qt, the download engine, Deno, icons,
and dependency notices are embedded. The public build obtains FFmpeg and
FFprobe separately through the application's verified first-run download.
The PyInstaller spec includes yt-dlp's dynamically imported extractors and
postprocessors.

For an installer, install [Inno Setup 6](https://jrsoftware.org/isinfo.php), then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -Installer
```

This also produces `dist/Orvilo-Setup-1.0.2.exe`. Installation is per user, with a
Start menu entry and an optional desktop shortcut. The public portable download
is named `Orvilo-1.0.2-Windows-x64.exe`.

For a diagnostic build with a console, set `$env:ORVILO_DEBUG = '1'` before
building; remove it for normal builds. Signing a Windows executable requires
your own code-signing certificate.

Redistribution must preserve the exact dependencies' licenses and applicable
source/rebuild information. Original Orvilo code is MIT licensed; the combined
public Windows distribution is GPL-3.0-or-later. See
[third-party notices](../assets/THIRD_PARTY_NOTICES.md) and
[dependency sources](../DEPENDENCY_SOURCES.md).

## Architecture

| Location | Responsibility |
| --- | --- |
| `main.py` | Startup, single-instance lock, logging, engine activation, diagnostics. |
| `ui/` | Frameless shell, reusable controls, theme tokens, and four app pages. |
| `core/downloader.py` | yt-dlp integration, media selection, and FFmpeg operations. |
| `core/site_adapters.py` | Bilibili's own backup URLs and transfer recovery. |
| `core/queue.py` | Qt workers, download controls, concurrency, and queue persistence. |
| `core/history.py`, `settings.py`, `models.py` | SQLite history, JSON preferences, and typed values. |
| `core/engine.py`, `plugins.py` | Verified engine updates and local extractors. |
| `utils/` | File paths, display formatting, logging, and friendly error messages. |
| `assets/`, `scripts/` | SVGs, icon exports, runtime setup, and dependency notices. |

Worker results return through Qt signals. The UI thread owns SQLite writes and
queue state. Engine operations run on a bounded thread pool and never mutate
widgets directly. Output locks prevent jobs from writing the same media path
concurrently.

## Local data and updates

`%LOCALAPPDATA%/Orvilo` contains:

- `settings.json`: preferences, browser/profile paths, and optional proxy address.
- `history.sqlite3`: completed download metadata and file paths.
- `queue.json`: resumable queue snapshots, without copied proxy credentials.
- `thumbnails/`: cached preview images.
- `logs/orvilo.log`: rotating diagnostics with URLs and credentials redacted.
- `runtime/`: separately installed video tools.
- `engine/`: verified engine updates.
- `plugins/`: user-installed extractors.
- `engine-cache/`: yt-dlp's local cache.

An engine update fetches official yt-dlp and matching yt-dlp-ejs wheels from
PyPI, checks SHA-256 hashes and Python/dependency compatibility, and atomically
stages the release. It activates after restart. Corrupt or invalid updates do
not replace the active engine. A future engine requiring new compiled
dependencies may need an application rebuild.

## Add a site extractor

See [the plugin guide](../plugins/README.md) for a runnable example. Place a
Python module exporting `EXTRACTORS = [YourInfoExtractorClass]` into
`%LOCALAPPDATA%/Orvilo/plugins`. Use yt-dlp's `InfoExtractor` helpers and a narrow
URL pattern.

Local plugins are registered before built-ins and the generic fallback. They
are ordinary trusted Python code installed by the user, not downloaded
automatically. An extractor should respect the site's access controls and only
return media that the current session is permitted to access.

## Add a theme

Add a palette with the existing keys to `PALETTES` in `ui/theme.py`, add its
identifier to `SettingsStore._validate` in `core/settings.py`, and add its
label/value pair to the theme selector in `ui/settings_page.py`. Shared QSS
styles every page; accent color remains a separate preference.

## Change the logo

Edit `assets/logo.svg`, then run:

```powershell
.\.venv\Scripts\python.exe scripts\export_icons.py
```

The exporter creates a transparent PNG and an ICO containing 16, 32, 48, 64,
128, and 256 px images. Rebuild the executable to embed the new icon.

## Verify changes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe main.py --smoke-test .\preview
.\.venv\Scripts\python.exe main.py --verify-runtime .\runtime-check --ffmpeg-path .\assets\runtime
```

The media tests generate permission-owned color/sine fixtures served over a
local HTTP server. They cover five audio conversions, video remuxing, clip
duration, embedded metadata/subtitles/artwork, generic extraction, multi-video
selection, storage, queue controls, updater integrity, and the Qt workflow.
HTTP recovery tests check resumption, fallback, preserved headers, and exact
output bytes. FFmpeg integration checks skip when the tools are unavailable.

Both diagnostic switches also work on the packaged executable:

```powershell
.\dist\Orvilo.exe --smoke-test .\packaged-preview
.\dist\Orvilo.exe --verify-runtime .\packaged-runtime-check --ffmpeg-path .\assets\runtime
```

Screenshots and media diagnostics use isolated data folders. The public build
does not bundle FFmpeg, and isolated checks do not inherit your normal Settings
folder, so pass the video-tool folder explicitly with `--ffmpeg-path`. It must
contain both FFmpeg and FFprobe. The runtime check writes `runtime-report.json`
after exercising the real libraries and executables with seven generated
video/audio/clip variants. These checks do not assert live compatibility with
every third-party website.
