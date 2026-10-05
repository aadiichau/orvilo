# Dependency sources and your rights

Orvilo's original source is MIT-licensed. The public executable combines it with
GPL-compatible dependencies, including Mutagen, and is distributed under
GPL-3.0-or-later. This does not remove the individual components' licenses.
The complete GPLv3 and LGPLv3 texts are in `LICENSES/`; installed dependency
notices are in `assets/licenses/` and embedded in the executable.

Qt and Qt for Python are used under their open-source license terms. You may
modify, debug, reverse-engineer for debugging your modifications, replace the
libraries, and rebuild the application. There is no signature or activation
check preventing a modified build. Follow `docs/DEVELOPMENT.md`: install your
replacement Qt/PySide wheels into `.venv`, then run `build.ps1`. The full
application source and packaging scripts are supplied in this repository
and the source ZIP beside each executable release.

The following upstream locations provide the matching dependency source.
Mutagen's complete matching source archive is additionally included in
`third_party/sources`. The machine-readable manifest records PyPI SHA-256
digests. Build-tool and test dependencies are listed as well for reproducibility.

| Component | Exact version | Corresponding source |
| --- | --- | --- |
| PySide6 | 6.11.2 | [Source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz) |
| PySide6_Addons | 6.11.2 | [Source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz) |
| PySide6_Essentials | 6.11.2 | [Source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz) |
| Pygments | 2.21.0 | [Source](https://files.pythonhosted.org/packages/49/2e/ced460408999b33da6b31b0021b0f37d329e202d4169aeb164493778f25b/pygments-2.21.0.tar.gz) |
| altgraph | 0.17.5 | [Source](https://files.pythonhosted.org/packages/7e/f8/97fdf103f38fed6792a1601dbc16cc8aac56e7459a9fff08c812d8ae177a/altgraph-0.17.5.tar.gz) |
| brotli | 1.2.0 | [Source](https://files.pythonhosted.org/packages/f7/16/c92ca344d646e71a43b8bb353f0a6490d7f6e06210f8554c8f874e454285/brotli-1.2.0.tar.gz) |
| certifi | 2026.7.22 | [Source](https://files.pythonhosted.org/packages/a3/c2/24167ea9858356b47a87a50d39908bfdb72ceeefe0041586e704e5376b3a/certifi-2026.7.22.tar.gz) |
| cffi | 2.1.1 | [Source](https://files.pythonhosted.org/packages/9e/ef/008a1939e372c06329a3fce4279c02f328488f3526744906eeec3da7ad5f/cffi-2.1.1.tar.gz) |
| charset-normalizer | 3.5.2 | [Source](https://files.pythonhosted.org/packages/33/1c/f41d4e74c28ab327ff3acd36053f7ea506c55872d7a90b0fa71aa3ab0c89/charset_normalizer-3.5.2.tar.gz) |
| colorama | 0.4.6 | [Source](https://files.pythonhosted.org/packages/d8/53/6f443c9a4a8358a93a6792e2acffb9d9d5cb0a5cfd8802644b7b1c9a02e4/colorama-0.4.6.tar.gz) |
| curl_cffi | 0.16.3 | [Source](https://files.pythonhosted.org/packages/82/e1/730125c43e3e331d98e17af3cb310ba526b3f1101b7635ca23d976ebfcf5/curl_cffi-0.16.3.tar.gz) |
| idna | 3.20 | [Source](https://files.pythonhosted.org/packages/f5/08/8eea9d4b8302028f3abb2c0813953f7aec26d33b7a8960ed760e65ff29fa/idna-3.20.tar.gz) |
| iniconfig | 2.3.0 | [Source](https://files.pythonhosted.org/packages/72/34/14ca021ce8e5dfedc35312d08ba8bf51fdd999c576889fc2c24cb97f4f10/iniconfig-2.3.0.tar.gz) |
| mutagen | 1.48.1 | [Source](https://files.pythonhosted.org/packages/df/70/1675da133ea92227da41bf5b24e1c66be597ff736a1533ade41da986852f/mutagen-1.48.1.tar.gz) |
| packaging | 26.3 | [Source](https://files.pythonhosted.org/packages/7d/fa/3944b40b07da9ce895c0e6303a5ab7d53da063554f534556b134a54d6093/packaging-26.3.tar.gz) |
| pefile | 2024.8.26 | [Source](https://files.pythonhosted.org/packages/03/4f/2750f7f6f025a1507cd3b7218691671eecfd0bbebebe8b39aa0fe1d360b8/pefile-2024.8.26.tar.gz) |
| pillow | 12.3.0 | [Source](https://files.pythonhosted.org/packages/1c/3d/bb7fca845737cf9d7dbde16ed1843984665ff2e0a518f5db43e77ec540b9/pillow-12.3.0.tar.gz) |
| pluggy | 1.6.0 | [Source](https://files.pythonhosted.org/packages/f9/e2/3e91f31a7d2b083fe6ef3fa267035b518369d9511ffab804f839851d2779/pluggy-1.6.0.tar.gz) |
| psutil | 7.2.2 | [Source](https://files.pythonhosted.org/packages/aa/c6/d1ddf4abb55e93cebc4f2ed8b5d6dbad109ecb8d63748dd2b20ab5e57ebe/psutil-7.2.2.tar.gz) |
| pycparser | 3.0 | [Source](https://files.pythonhosted.org/packages/1b/7d/92392ff7815c21062bea51aa7b87d45576f649f16458d78b7cf94b9ab2e6/pycparser-3.0.tar.gz) |
| pycryptodomex | 3.23.0 | [Source](https://files.pythonhosted.org/packages/c9/85/e24bf90972a30b0fcd16c73009add1d7d7cd9140c2498a68252028899e41/pycryptodomex-3.23.0.tar.gz) |
| pyinstaller | 6.22.3 | [Source](https://files.pythonhosted.org/packages/63/41/f90302845945abd4ed647933ff5ee7c6ac93983187be67f897b6cb613331/pyinstaller-6.22.3.tar.gz) |
| pyinstaller-hooks-contrib | 2026.8 | [Source](https://files.pythonhosted.org/packages/c9/3b/fab1a12a21bf9223af012e5dd002b7d4265683d21d9fabbd0ccb347316e4/pyinstaller_hooks_contrib-2026.8.tar.gz) |
| pytest | 9.1.1 | [Source](https://files.pythonhosted.org/packages/e4/47/b9efed96c114afcfa3c9d3fe98a76a1d14c74a9e266d397cf6eb64be5e01/pytest-9.1.1.tar.gz) |
| pywin32-ctypes | 0.2.3 | [Source](https://files.pythonhosted.org/packages/85/9f/01a1a99704853cb63f253eea009390c88e7131c67e66a0a02099a8c917cb/pywin32-ctypes-0.2.3.tar.gz) |
| requests | 2.34.2 | [Source](https://files.pythonhosted.org/packages/ac/c3/e2a2b89f2d3e2179abd6d00ebd70bff6273f37fb3e0cc209f48b39d00cbf/requests-2.34.2.tar.gz) |
| shiboken6 | 6.11.2 | [Source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz) |
| urllib3 | 2.8.0 | [Source](https://files.pythonhosted.org/packages/e3/05/b17359e1cefb4f909b5e40b1b90a496d987258916dbbf88e842c729f510e/urllib3-2.8.0.tar.gz) |
| websockets | 17.2 | [Source](https://files.pythonhosted.org/packages/01/89/3f825ab71c242fffb62ea8fe638741c290f62f8d7aadf8125ff897747af3/websockets-17.2.tar.gz) |
| yt-dlp | 2026.8.19 | [Source](https://files.pythonhosted.org/packages/1e/e0/832fa4ca334b766a06933a196066edc3dba37cdb6f14cd98d59bcc69a4b4/yt_dlp-2026.8.19.tar.gz) |
| yt-dlp-ejs | 0.8.0 | [Source](https://files.pythonhosted.org/packages/d3/e6/cceb9530e8f4e5940f6f7822d90e9d94f1b85343329a16baaf47bbbb3de1/yt_dlp_ejs-0.8.0.tar.gz) |
| Qt | 6.11.2 | [Source](https://download.qt.io/official_releases/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz) |
| Python | 3.12.14 | [Source](https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz) |
| Deno | 2.9.7 | [Source](https://github.com/denoland/deno/tree/v2.9.7) |
| Lucide | 0.468.0 | [Source](https://github.com/lucide-icons/lucide/tree/0.468.0) |

## FFmpeg

Public Orvilo installers and portable executables do not contain FFmpeg or
FFprobe. First-run setup downloads the publisher's checksum-verified
archive directly to the user's computer. These tools remain independent
programs invoked as subprocesses. Their source, configuration, licenses
and release information are supplied by [Gyan](https://www.gyan.dev/ffmpeg/builds/).
Users can instead select their own compatible FFmpeg build in Settings.
