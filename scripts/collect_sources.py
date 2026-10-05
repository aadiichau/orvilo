"""Record exact upstream source locations for the installed release dependencies."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def read_url(url: str, limit: int = 8 * 1024 * 1024) -> bytes:
    """Read a bounded HTTPS source document or package index response."""
    if not url.startswith("https://"):
        raise ValueError("Source records require HTTPS")
    with urlopen(Request(url, headers={"User-Agent": "Orvilo-source-inventory"}), timeout=60) as response:
        if not response.url.startswith("https://"):
            raise ValueError("Insecure source redirect")
        payload = response.read(limit + 1)
        if len(payload) > limit:
            raise ValueError("Source document exceeds its size limit")
        return payload


def main() -> None:
    """Generate reproducible source references and the applicable license texts."""
    licenses = ROOT / "LICENSES"
    licenses.mkdir(exist_ok=True)
    for filename, url in {
        "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
        "LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
    }.items():
        (licenses / filename).write_bytes(read_url(url))
    rows = []
    qt_version = importlib.metadata.version("PySide6")
    qt_series = ".".join(qt_version.split(".")[:2])
    qt_source = f"https://download.qt.io/official_releases/qt/{qt_series}/{qt_version}/single/qt-everywhere-src-{qt_version}.tar.xz"
    pyside_folder = f"https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-{qt_version}-src/"
    listing = read_url(pyside_folder).decode("utf-8")
    names = re.findall(r'href="([^"/]+\.tar\.xz)"', listing)
    if not names:
        raise ValueError("The exact Qt for Python source release was not found")
    pyside_source = pyside_folder + names[0]
    for distribution in sorted(importlib.metadata.distributions(), key=lambda item: item.metadata.get("Name", "")):
        name = distribution.metadata.get("Name", "unknown")
        if name.lower() in {"pip", "setuptools"}:
            continue
        version = distribution.version
        if name.lower().startswith(("pyside6", "shiboken6")):
            rows.append({"name": name, "version": version, "source": pyside_source, "sha256": None})
            continue
        metadata = json.loads(read_url(f"https://pypi.org/pypi/{name}/{version}/json"))
        sources = [entry for entry in metadata["urls"] if entry["packagetype"] == "sdist"]
        if not sources:
            raise ValueError(f"No source distribution is available for {name} {version}")
        source = sources[0]
        rows.append({"name": name, "version": version, "source": source["url"], "sha256": source["digests"]["sha256"]})
        if name.lower() == "mutagen":
            destination = ROOT / "third_party" / "sources" / source["filename"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            payload = read_url(source["url"], 16 * 1024 * 1024)
            if hashlib.sha256(payload).hexdigest() != source["digests"]["sha256"]:
                raise ValueError("Mutagen source checksum mismatch")
            destination.write_bytes(payload)
    python = platform.python_version()
    runtime_record = json.loads((ROOT / "assets" / "runtime" / "versions.json").read_text(encoding="utf-8"))
    deno_tag = runtime_record["deno"]["version"]
    rows.extend([
        {"name": "Qt", "version": qt_version, "source": qt_source, "sha256": None},
        {"name": "Python", "version": python, "source": f"https://www.python.org/ftp/python/{python}/Python-{python}.tar.xz", "sha256": None},
        {"name": "Deno", "version": deno_tag.lstrip("v"), "source": f"https://github.com/denoland/deno/tree/{deno_tag}", "sha256": None},
        {"name": "Lucide", "version": "0.468.0", "source": "https://github.com/lucide-icons/lucide/tree/0.468.0", "sha256": None},
    ])
    (ROOT / "assets" / "source-manifest.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = [
        "# Dependency sources and your rights", "",
        "Orvilo's original source is MIT-licensed. The public executable combines it with",
        "GPL-compatible dependencies, including Mutagen, and is distributed under",
        "GPL-3.0-or-later. This does not remove the individual components' licenses.",
        "The complete GPLv3 and LGPLv3 texts are in `LICENSES/`; installed dependency",
        "notices are in `assets/licenses/` and embedded in the executable.", "",
        "Qt and Qt for Python are used under their open-source license terms. You may",
        "modify, debug, reverse-engineer for debugging your modifications, replace the",
        "libraries, and rebuild the application. There is no signature or activation",
        "check preventing a modified build. Follow `docs/DEVELOPMENT.md`: install your",
        "replacement Qt/PySide wheels into `.venv`, then run `build.ps1`. The full",
        "application source and packaging scripts are supplied in this repository",
        "and the source ZIP beside each executable release.", "",
        "The following upstream locations provide the matching dependency source.",
        "Mutagen's complete matching source archive is additionally included in",
        "`third_party/sources`. The machine-readable manifest records PyPI SHA-256",
        "digests. Build-tool and test dependencies are listed as well for reproducibility.", "",
        "| Component | Exact version | Corresponding source |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {row['name']} | {row['version']} | [Source]({row['source']}) |" for row in rows)
    lines.extend(["", "## FFmpeg", "", "Public Orvilo installers and portable executables do not contain FFmpeg or",
                  "FFprobe. First-run setup downloads the publisher's checksum-verified",
                  "archive directly to the user's computer. These tools remain independent",
                  "programs invoked as subprocesses. Their source, configuration, licenses",
                  "and release information are supplied by [Gyan](https://www.gyan.dev/ffmpeg/builds/).",
                  "Users can instead select their own compatible FFmpeg build in Settings.", ""])
    (ROOT / "DEPENDENCY_SOURCES.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Recorded {len(rows)} exact dependency source locations.")


if __name__ == "__main__":
    main()
