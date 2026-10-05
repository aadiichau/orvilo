"""Refresh the small bundled Lucide icon subset from its published package."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

NAMES = {
    "download": "download", "list": "list-video", "history": "history", "settings": "settings-2",
    "link": "link", "arrow-down": "arrow-down-to-line", "check": "check", "x": "x",
    "minus": "minus", "square": "square", "folder": "folder-open", "copy": "copy",
    "play": "play", "pause": "pause", "refresh": "refresh-cw", "trash": "trash-2",
    "search": "search", "sun": "sun", "moon": "moon", "plus": "plus",
    "external-link": "external-link", "chevron-right": "chevron-right",
    "chevron-down": "chevron-down",
}


def main() -> None:
    """Download a fixed Lucide version and extract only SVGs and its license."""
    root = Path(__file__).resolve().parents[1] / "assets"
    with urlopen("https://registry.npmjs.org/lucide-static/0.468.0", timeout=40) as response:
        metadata = json.load(response)
    with urlopen(metadata["dist"]["tarball"], timeout=60) as response:
        archive = response.read(50 * 1024 * 1024)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        for target, source in NAMES.items():
            member = bundle.getmember(f"package/icons/{source}.svg")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing icon: {source}")
            content = stream.read()
            if target == "chevron-down":
                content = content.replace(b"currentColor", b"#9694A9")
            (root / "icons" / f"{target}.svg").write_bytes(content)
        license_file = bundle.extractfile("package/LICENSE")
        if license_file is None:
            raise ValueError("Lucide license is missing")
        (root / "licenses").mkdir(exist_ok=True)
        (root / "licenses" / "Lucide.txt").write_bytes(license_file.read())
    print(f"Saved {len(NAMES)} Lucide SVG icons.")


if __name__ == "__main__":
    main()
