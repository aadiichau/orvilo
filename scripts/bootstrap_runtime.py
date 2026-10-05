"""Download checksum-verified Windows FFmpeg and Deno into this project only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "assets" / "runtime"
LICENSES = ROOT / "assets" / "licenses" / "runtime"


def fetch(url: str, destination: Path, limit: int = 512 * 1024 * 1024) -> str:
    """Stream an HTTPS artifact to disk and return its SHA-256 digest."""
    if not url.startswith("https://"):
        raise ValueError("Runtime downloads require HTTPS")
    request = Request(url, headers={"User-Agent": "Orvilo/1.0 runtime-setup"})
    digest = hashlib.sha256()
    count = 0
    with urlopen(request, timeout=120) as response, destination.open("wb") as output:
        if not response.url.startswith("https://"):
            raise ValueError("Runtime download redirected to an insecure source")
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > limit:
                raise ValueError("The runtime download is unexpectedly large")
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def verified_zip(url: str, checksum_url: str, folder: Path, name: str) -> Path:
    """Download one release archive and check its publisher-provided checksum."""
    checksum = folder / f"{name}.sha256"
    fetch(checksum_url, checksum, 16384)
    match = re.search(r"\b[0-9a-fA-F]{64}\b", checksum.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError(f"The {name} checksum could not be read")
    archive = folder / f"{name}.zip"
    print(f"Downloading {name} from {url}", flush=True)
    actual = fetch(url, archive)
    if actual.lower() != match.group(0).lower():
        raise RuntimeError(f"{name} checksum mismatch. No executable was installed; run setup again.")
    return archive


def install_archive(archive: Path, names: set[str], prefix: str) -> dict[str, str]:
    """Extract only selected executables and accompanying license documents."""
    result = {}
    with zipfile.ZipFile(archive) as bundle:
        for name in names:
            matches = [entry for entry in bundle.infolist() if Path(entry.filename).name.lower() == name]
            if len(matches) != 1:
                raise RuntimeError(f"The {prefix} archive has no unique {name}")
            entry = matches[0]
            if entry.file_size > 400 * 1024 * 1024:
                raise RuntimeError(f"The {name} executable is unexpectedly large")
            temporary = RUNTIME / (name + ".new")
            with bundle.open(entry) as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output)
            if temporary.read_bytes()[:2] != b"MZ":
                raise RuntimeError(f"The {name} file is not a Windows executable")
            os.replace(temporary, RUNTIME / name)
            result[name] = hashlib.sha256((RUNTIME / name).read_bytes()).hexdigest()
        for entry in bundle.infolist():
            leaf = Path(entry.filename).name
            if not entry.is_dir() and entry.file_size < 4 * 1024 * 1024 and any(token in leaf.lower() for token in ("license", "copying", "readme")):
                safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", leaf)
                (LICENSES / f"{prefix}-{safe_name}").write_bytes(bundle.read(entry))
    return result


def describe(executable: str, *arguments: str) -> str:
    """Capture a runtime's version or license information without a console."""
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run([str(RUNTIME / executable), *arguments], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30, creationflags=flags, check=True)
    return result.stdout + result.stderr


def main() -> None:
    """Install local runtimes, or keep previously provisioned copies."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Replace existing runtimes with the latest releases")
    args = parser.parse_args()
    if os.name != "nt" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("This bundle targets 64-bit Windows 10/11. Use x64 Python on Windows.")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    LICENSES.mkdir(parents=True, exist_ok=True)
    records_path = RUNTIME / "versions.json"
    records = json.loads(records_path.read_text(encoding="utf-8")) if records_path.exists() else {}
    scratch = ROOT / ".runtime-downloads"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="setup-", dir=scratch) as temporary:
        stage = Path(temporary)
        if args.force or not all((RUNTIME / name).is_file() for name in ("ffmpeg.exe", "ffprobe.exe")):
            ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            archive = verified_zip(ffmpeg_url, ffmpeg_url + ".sha256", stage, "FFmpeg")
            records["ffmpeg"] = {"url": ffmpeg_url, "sha256": install_archive(archive, {"ffmpeg.exe", "ffprobe.exe"}, "FFmpeg")}
        if args.force or not (RUNTIME / "deno.exe").is_file():
            metadata_path = stage / "deno-release.json"
            fetch("https://api.github.com/repos/denoland/deno/releases/latest", metadata_path, 4 * 1024 * 1024)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            asset = next(item for item in metadata["assets"] if item["name"] == "deno-x86_64-pc-windows-msvc.zip")
            url = asset["browser_download_url"]
            archive = verified_zip(url, url + ".sha256sum", stage, "Deno")
            records["deno"] = {"version": metadata["tag_name"], "url": url, "sha256": install_archive(archive, {"deno.exe"}, "Deno")}
        ffmpeg_version = describe("ffmpeg.exe", "-version")
        deno_version = describe("deno.exe", "--version")
        (LICENSES / "FFmpeg-build-configuration.txt").write_text(ffmpeg_version, encoding="utf-8")
        deno_tag = records.get("deno", {}).get("version") or ("v" + deno_version.splitlines()[0].split()[1])
        license_path = LICENSES / "Deno-LICENSE.md"
        if not license_path.is_file():
            fetch(f"https://raw.githubusercontent.com/denoland/deno/{deno_tag}/LICENSE.md", license_path, 4 * 1024 * 1024)
        (LICENSES / "Deno-source.txt").write_text(f"Corresponding source and third-party notices: https://github.com/denoland/deno/tree/{deno_tag}\n", encoding="utf-8")
        records.setdefault("ffmpeg", {})["version_output"] = ffmpeg_version
        records.setdefault("deno", {})["version_output"] = deno_version
        records["ffmpeg"].setdefault("url", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
        records["deno"].setdefault("version", deno_tag)
        records["deno"].setdefault("url", f"https://github.com/denoland/deno/releases/download/{deno_tag}/deno-x86_64-pc-windows-msvc.zip")
        for package, names in (("ffmpeg", ("ffmpeg.exe", "ffprobe.exe")), ("deno", ("deno.exe",))):
            records[package]["sha256"] = {name: hashlib.sha256((RUNTIME / name).read_bytes()).hexdigest() for name in names}
        records_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("FFmpeg, FFprobe, and Deno are ready in assets/runtime.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"Runtime setup failed: {error}") from None
