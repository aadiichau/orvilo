# -*- mode: python ; coding: utf-8 -*-
"""Build the public Windows executable; FFmpeg installs from its publisher."""
from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH)
runtime = root / "assets" / "runtime"
required = [runtime / "deno.exe"]
missing = [str(path) for path in required if not path.is_file()]
if missing:
    raise SystemExit("Run scripts/bootstrap_runtime.py before building. Missing: " + ", ".join(missing))

datas = [
    (str(path), str(path.parent.relative_to(root)))
    for path in (root / "assets").rglob("*")
    if path.is_file() and path.name.lower() not in {"ffmpeg.exe", "ffprobe.exe"}
    and not path.name.lower().startswith("ffmpeg-")
]
datas.extend([(str(root / "plugins"), "plugins"), (str(root / "LICENSES"), "LICENSES"),
              (str(root / "DEPENDENCY_SOURCES.md"), "."), (str(root / "LICENSE"), ".")])
binaries = []
hiddenimports = ["PySide6.QtSvg", "PySide6.QtNetwork", "packaging.requirements", "packaging.version"]
for package in ("yt_dlp", "yt_dlp_ejs", "curl_cffi", "mutagen", "Cryptodome", "websockets", "requests", "certifi", "brotli"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas.extend(package_data)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_imports)
for distribution in ("yt-dlp", "yt-dlp-ejs", "curl-cffi", "mutagen", "pycryptodomex", "websockets", "requests", "certifi", "brotli", "packaging", "urllib3"):
    datas.extend(copy_metadata(distribution))

a = Analysis(
    [str(root / "main.py")], pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "tkinter"],
    noarchive=False,
)
# Recent Qt uses the ICU API supplied by Windows 10/11. An unrelated ICU with
# the same filename on a developer's PATH (for example Poppler/Conda) exports
# different symbols and must never shadow the operating-system DLL in a bundle.
a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in {"icuuc.dll", "icuin.dll"}]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="Orvilo", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False, console=bool(os.environ.get("ORVILO_DEBUG")),
    disable_windowed_traceback=not bool(os.environ.get("ORVILO_DEBUG")), icon=str(root / "assets" / "logo.ico"),
    version=str(root / "assets" / "version_info.txt"),
)
