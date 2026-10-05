# Orvilo dependency notices

Orvilo runs everything locally. Its original source is MIT-licensed. The public
executable is distributed under GPL-3.0-or-later, with the independent component
licenses retained. The build copies installed notices into `assets/licenses`
and embeds them together with `LICENSES` and `DEPENDENCY_SOURCES.md`.

| Component | Project | License family |
| --- | --- | --- |
| Python | https://www.python.org/ | PSF |
| PySide6 / Qt | https://www.qt.io/qt-for-python | LGPLv3 / GPLv3 / commercial; see installed module licenses |
| yt-dlp | https://github.com/yt-dlp/yt-dlp | Unlicense, with notices for included code |
| yt-dlp-ejs | https://github.com/yt-dlp/ejs | Unlicense, with notices for included JavaScript dependencies |
| FFmpeg | https://ffmpeg.org/ | Separate, user-installed GPLv3 tool; not included in the public executable or installer |
| Mutagen | https://mutagen.readthedocs.io/ | GPLv2-or-later; distributed here under GPLv3-or-later |
| Deno | https://github.com/denoland/deno | MIT, with third-party dependency notices |
| Lucide icons | https://lucide.dev/ | ISC (included as assets/licenses/Lucide.txt) |
| Pillow | https://python-pillow.org/ | HPND |
| PyInstaller | https://pyinstaller.org/ | GPL with exception for generated bundles |

Other installed package notices and exact versions are collected automatically
by `scripts/collect_licenses.py`. The Orvilo geometric logo is original vector
art supplied with this project.

## Runtime provenance

`scripts/bootstrap_runtime.py` downloads FFmpeg from Gyan's Windows build service
(linked from https://ffmpeg.org/download.html) and Deno from the official Deno
GitHub releases. It verifies each archive against the publisher's SHA-256 file,
stores executable hashes and release URLs in `assets/runtime/versions.json`,
and saves FFmpeg's build configuration and Deno's dependency licenses.

The public app's first-run setup downloads FFmpeg directly from its publisher,
checks its pinned SHA-256, and installs its executable and notices in the user's
local data directory. It can use an existing FFmpeg folder instead.

## Corresponding source and rebuilding

See [DEPENDENCY_SOURCES.md](../DEPENDENCY_SOURCES.md) for exact matching source
locations and the right to modify, replace Qt/PySide, and rebuild the executable.
The source archive is available beside each Windows release. Mutagen's matching
source archive is included in `third_party/sources`. The GPLv3 and LGPLv3 texts
are supplied in `LICENSES`. No signing or activation check prevents running a
modified build. These rights also apply to the installer-distributed app.
