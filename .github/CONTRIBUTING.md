# Contributing to Orvilo

Small, focused contributions are welcome: a reproducible site failure, a clearer error message, an accessibility improvement, or a regression test.

## Run the app

Use 64-bit Windows 10/11 and Python 3.11 or newer. Python 3.12 is used in CI.

```powershell
./setup.ps1
./run.ps1
```

Setup creates a local virtual environment, installs Python dependencies, and downloads checksum-verified FFmpeg, FFprobe, and Deno releases. Nothing needs to be installed globally beyond Python.

## Test a change

```powershell
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe main.py --smoke-test ./build/interface-check
./.venv/Scripts/python.exe main.py --verify-runtime ./build/runtime-check
```

Tests use isolated data directories. Media integration tests generate their own footage and serve it on localhost; they do not depend on third-party video availability or anyone's browser session. Run setup first so the FFmpeg tests run rather than skip.

For an interface change, inspect the dark and light screenshots in `build/interface-check`. Exercise the changed interaction in the running app too. Keep blocking extraction, download, and conversion work off the UI thread.

## Send a pull request

1. Fork the repository and create a branch with a descriptive name.
2. Keep changes focused and add a regression test for a bug with meaningful observable behavior.
3. Run the relevant tests. For a downloader change, include the local media integration tests.
4. Explain the problem, the resulting behavior, and what you verified. Include screenshots for visual changes.

Do not commit settings, browser profiles, cookies, download history, media downloads, executable build products, or personal logs. Plugins execute Python locally and should only be installed from a source the user trusts. DRM circumvention is outside the project scope.

## Build a Windows package

```powershell
./build.ps1
```

The portable app is written to `dist/Orvilo.exe`. With Inno Setup 6 installed, `./build.ps1 -Installer` also produces a per-user installer. Public packages obtain FFmpeg and FFprobe from their publisher during first-run setup; these two executables are not redistributed inside the app.

Repository maintainers can run **Actions → Build Windows packages → Run workflow**. The workflow tests the source, builds the executable, runs the packaged app's interface and media checks, and uploads packages, checksums, dependency versions, and license notices as artifacts. Media verification supplies the runner's locally downloaded FFmpeg through `--ffmpeg-path`; it does not add FFmpeg to the executable. The workflow builds the optional installer only when the runner has Inno Setup available. It does not publish a GitHub release automatically.

Before publishing a release, inspect the artifacts, update version metadata and release notes together, and include the license notices and corresponding source required by bundled dependencies. Review any dependency license change before redistribution. GitHub Actions artifacts require authentication; public downloads belong on the repository's Releases page.

The Windows workflows use official actions pinned to verified commit hashes. Review the upstream release when updating a pin, then test the workflow before using it for a release.
