"""Include installed dependency licenses and versions in the executable."""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import re
import sys


def main() -> None:
    """Collect license documents from the exact installed build environment."""
    root = Path(__file__).resolve().parents[1]
    output = root / "assets" / "licenses" / "python"
    output.mkdir(parents=True, exist_ok=True)
    inventory = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        if name.lower() in {"pip", "setuptools"}:
            continue
        folder = output / re.sub(r"[^A-Za-z0-9._-]", "_", name)
        folder.mkdir(exist_ok=True)
        files = []
        for entry in distribution.files or []:
            if not any(value in Path(str(entry)).name.lower() for value in ("license", "copying", "copyright", "notice")):
                continue
            source = Path(distribution.locate_file(entry))
            if source.is_file() and source.stat().st_size < 5 * 1024 * 1024:
                destination = folder / re.sub(r"[^A-Za-z0-9._-]", "_", str(entry))
                destination.write_bytes(source.read_bytes())
                files.append(destination.name)
        metadata = {
            "name": name, "version": distribution.version,
            "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "See license documents"),
            "home": distribution.metadata.get("Home-page", ""),
            "project_urls": distribution.metadata.get_all("Project-URL") or [], "files": files,
        }
        (folder / "package.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        inventory.append(metadata)
    for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if candidate.is_file():
            (output / "Python-LICENSE.txt").write_bytes(candidate.read_bytes())
            break
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"Collected notices for {len(inventory)} installed distributions.")


if __name__ == "__main__":
    main()
