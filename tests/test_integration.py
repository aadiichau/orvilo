"""Real local HTTP, yt-dlp and FFmpeg tests; no third-party website required."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading

from PIL import Image
import pytest

from core.downloader import Control, _runtime, download, probe
from core.downloader import Cancelled
from core.models import DownloadOptions
from core.video_formats import VideoOutputPP
from yt_dlp import YoutubeDL
from utils.paths import data_dir


def _run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, check=True, timeout=60,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


@pytest.fixture(scope="module")
def local_media(tmp_path_factory):
    """Serve a generated color/sine video, captions and cover entirely locally."""
    ffmpeg = _runtime("ffmpeg")
    ffprobe = _runtime("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("Run setup.ps1 to install FFmpeg before media integration tests")
    root = tmp_path_factory.mktemp("local-media")
    _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
          "color=c=0x7C5CFF:s=320x180:r=25:d=4", "-f", "lavfi", "-i",
          "sine=frequency=440:sample_rate=44100:duration=4", "-c:v", "libx264", "-preset", "ultrafast",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(root / "sample.mp4")])
    Image.new("RGB", (64, 64), "#7C5CFF").save(root / "cover.jpg")
    (root / "captions.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\nLocal test caption\n", encoding="utf-8")

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format, *_args):
            """Suppress the local fixture server's routine request log."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        yield {"base": base, "ffmpeg": ffmpeg, "ffprobe": ffprobe, "root": root}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


@pytest.fixture
def fixture_plugin(local_media):
    """Install a real extractor that also exposes an ambiguous multi-video post."""
    path = data_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    source = '''"""Deterministic local media extractor used by integration tests."""
from yt_dlp.extractor.common import InfoExtractor

class OrviloFixtureIE(InfoExtractor):
    IE_NAME = "orvilo:fixture"
    _VALID_URL = r"http://127\\.0\\.0\\.1:[0-9]+/(?P<id>fixture|collection)"

    def _real_extract(self, url):
        video_id = self._match_id(url)
        base = url.rsplit("/", 1)[0]
        info = {
            "id": "sample", "title": "Local permission-owned fixture", "duration": 4,
            "uploader": "Orvilo test", "thumbnail": base + "/cover.jpg",
            "webpage_url": url,
            "formats": [{"format_id": "local", "url": base + "/sample.mp4", "ext": "mp4",
                         "vcodec": "h264", "acodec": "aac", "width": 320, "height": 180}],
            "subtitles": {"en": [{"url": base + "/captions.srt", "ext": "srt"}]},
        }
        if video_id == "collection":
            second = {**info, "id": "second", "title": "Second attachment"}
            return self.playlist_result([info, second], "collection", "Local collection")
        return info

EXTRACTORS = [OrviloFixtureIE]
'''
    (path / "fixture.py").write_text(source, encoding="utf-8")
    return local_media["base"] + "/fixture"


def _inspect(local_media, path):
    return json.loads(_run([local_media["ffprobe"], "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(path)]).stdout)


def _color_tags(local_media, path):
    """Read decoded tags; FFprobe may omit HDR primaries from stream summaries."""
    metadata = json.loads(_run([local_media["ffprobe"], "-v", "error", "-select_streams", "V:0",
                               "-read_intervals", "%+#8", "-show_frames", "-show_entries",
                               "frame=color_space,color_transfer,color_primaries", "-of", "json", str(path)]).stdout)
    return metadata["frames"][0]


def test_real_video_metadata_subtitles_and_cover(local_media, fixture_plugin, tmp_path):
    events = []
    options = DownloadOptions(folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"],
                              video_format="mkv", subtitles="embed", embed_cover=True, save_thumbnail=True)
    preview = probe(fixture_plugin, options)
    assert preview.title == "Local permission-owned fixture"
    assert preview.qualities == [180]
    result = download(fixture_plugin, options, Control(), events.append)
    media = _inspect(local_media, result.file_path)
    assert Path(result.file_path).suffix == ".mkv"
    assert result.quality == "180p"
    assert result.file_size == Path(result.file_path).stat().st_size > 0
    assert any(stream["codec_type"] == "subtitle" for stream in media["streams"])
    assert any(stream.get("disposition", {}).get("attached_pic") for stream in media["streams"])
    assert media["format"]["tags"].get("title") == preview.title
    assert list(Path(result.file_path).parent.glob("*.jpg"))
    assert events[-1]["progress"] == 100


@pytest.mark.parametrize("codec", ["mp3", "m4a", "flac", "wav", "opus"])
def test_real_audio_conversion_final_extension(local_media, fixture_plugin, tmp_path, codec):
    options = DownloadOptions(kind="audio", audio_format=codec, folder=str(tmp_path),
                              ffmpeg_path=local_media["ffmpeg"], embed_cover=True)
    result = download(fixture_plugin, options, Control(), lambda _event: None)
    media = _inspect(local_media, result.file_path)
    assert Path(result.file_path).suffix == "." + codec
    assert any(stream["codec_type"] == "audio" for stream in media["streams"])
    assert not any(stream["codec_type"] == "video" and not stream.get("disposition", {}).get("attached_pic")
                   for stream in media["streams"])
    assert result.quality == codec.upper()
    if codec == "wav":
        assert list(Path(result.file_path).parent.glob("*.jpg"))


def test_real_clip_duration_and_unique_output(local_media, fixture_plugin, tmp_path):
    options = DownloadOptions(folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"], clip_start=1, clip_end=2.5)
    result = download(fixture_plugin, options, Control(), lambda _event: None)
    media = _inspect(local_media, result.file_path)
    assert 1.3 <= float(media["format"]["duration"]) <= 1.8
    assert "clip 1-2.5s" in result.file_path


def test_multi_video_selects_second_attachment(local_media, fixture_plugin, tmp_path):
    options = DownloadOptions(folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"])
    collection = local_media["base"] + "/collection"
    preview = probe(collection, options)
    assert preview.is_playlist
    assert len(preview.entries) == 2
    assert preview.entries[0].url != preview.entries[1].url
    assert preview.entries[1].url.endswith("#orvilo-item=2")
    limited = probe(collection, options, playlist_limit=1)
    assert limited.more_entries
    assert len(limited.entries) == 1
    result = download(preview.entries[1].url, options, Control(), lambda _event: None)
    assert result.title == "Second attachment"
    assert "second" in result.file_path


def test_generic_direct_video_download(local_media, tmp_path):
    options = DownloadOptions(folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"])
    result = download(local_media["base"] + "/sample.mp4", options, Control(), lambda _event: None)
    assert Path(result.file_path).is_file()
    assert result.file_size > 0


@pytest.mark.parametrize("profile,extension,video_codec,audio_codec,pixel_format", [
    ("mp4", ".mp4", "h264", "aac", "yuv420p"),
    ("mov", ".mov", "h264", "aac", "yuv420p"),
    ("prores", ".mov", "prores", "pcm_s16le", "yuv422p10le"),
    ("webm", ".webm", "vp9", "opus", "yuv420p"),
])
def test_real_video_profiles(local_media, fixture_plugin, tmp_path, profile, extension, video_codec, audio_codec, pixel_format):
    options = DownloadOptions(video_format=profile, folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"])
    result = download(fixture_plugin, options, Control(), lambda _event: None)
    media = _inspect(local_media, result.file_path)
    video = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in media["streams"] if stream["codec_type"] == "audio")
    assert Path(result.file_path).suffix == extension
    assert video["codec_name"] == video_codec
    assert video["pix_fmt"] == pixel_format
    assert video["r_frame_rate"] == video["avg_frame_rate"] == "25/1"
    assert audio["codec_name"] == audio_codec
    assert (video["width"], video["height"]) == (320, 180)
    assert 3.8 <= float(media["format"]["duration"]) <= 4.2
    _run([local_media["ffmpeg"], "-v", "error", "-i", result.file_path, "-f", "null", "-"])


def test_mp4_keeps_metadata_subtitles_and_cover(local_media, fixture_plugin, tmp_path):
    options = DownloadOptions(folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"],
                              video_format="mp4", subtitles="embed", embed_cover=True)
    result = download(fixture_plugin, options, Control(), lambda _event: None)
    media = _inspect(local_media, result.file_path)
    assert media["format"]["tags"]["title"] == "Local permission-owned fixture"
    assert any(stream["codec_name"] == "mov_text" for stream in media["streams"])
    assert any(stream.get("disposition", {}).get("attached_pic") for stream in media["streams"])


def test_webm_embeds_captions_and_saves_artwork(local_media, fixture_plugin, tmp_path):
    options = DownloadOptions(folder=str(tmp_path), ffmpeg_path=local_media["ffmpeg"],
                              video_format="webm", subtitles="embed", embed_cover=True)
    result = download(fixture_plugin, options, Control(), lambda _event: None)
    media = _inspect(local_media, result.file_path)
    assert any(stream["codec_name"] == "webvtt" for stream in media["streams"])
    assert list(Path(result.file_path).parent.glob("*.jpg"))


def test_vp9_opus_source_becomes_real_h264_aac(local_media, tmp_path):
    source = local_media["root"] / "vp9.webm"
    _run([local_media["ffmpeg"], "-v", "error", "-y", "-i", str(local_media["root"] / "sample.mp4"),
          "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus", str(source)])
    result = download(local_media["base"] + "/vp9.webm", DownloadOptions(folder=str(tmp_path),
                      ffmpeg_path=local_media["ffmpeg"], video_format="mp4"), Control(), lambda _event: None)
    media = _inspect(local_media, result.file_path)
    assert {stream["codec_name"] for stream in media["streams"]} == {"h264", "aac"}
    assert Path(result.file_path).suffix == ".mp4"


def test_silent_odd_dimensions_convert_without_missing_audio_errors(local_media, tmp_path):
    source = local_media["root"] / "odd.mkv"
    _run([local_media["ffmpeg"], "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=321x181:rate=25:duration=1",
          "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv444p", str(source)])
    result = download(local_media["base"] + "/odd.mkv", DownloadOptions(folder=str(tmp_path),
                      ffmpeg_path=local_media["ffmpeg"]), Control(), lambda _event: None)
    video = _inspect(local_media, result.file_path)["streams"][0]
    assert video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
    assert (video["width"], video["height"]) == (322, 182)


@pytest.mark.parametrize("profile", ["mp4", "mov", "prores", "webm"])
def test_hdr_profiles_keep_or_tone_map_color_tags(local_media, tmp_path, profile):
    source = local_media["root"] / "hdr.mkv"
    _run([local_media["ffmpeg"], "-v", "error", "-y", "-i", str(local_media["root"] / "sample.mp4"),
          "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020",
          "-color_trc", "smpte2084", "-colorspace", "bt2020nc", "-x265-params", "colorprim=9:transfer=16:colormatrix=9",
          "-t", "1", "-c:a", "copy", str(source)])
    assert _color_tags(local_media, source)["color_transfer"] == "smpte2084"
    result = download(local_media["base"] + "/hdr.mkv", DownloadOptions(folder=str(tmp_path),
                      ffmpeg_path=local_media["ffmpeg"], video_format=profile), Control(), lambda _event: None)
    video = _inspect(local_media, result.file_path)["streams"][0]
    assert video["pix_fmt"] == ("yuv422p10le" if profile == "prores" else "yuv420p")
    assert _color_tags(local_media, result.file_path)["color_transfer"] == ("smpte2084" if profile == "prores" else "bt709")


@pytest.mark.parametrize("cancel", [False, True])
def test_interrupted_conversion_preserves_source_and_existing_output(local_media, tmp_path, monkeypatch, cancel):
    source = tmp_path / "source.mkv"
    source.write_bytes((local_media["root"] / "sample.mp4").read_bytes())
    original = source.read_bytes()
    destination = source.with_suffix(".mp4")
    destination.write_bytes(b"existing file must survive")
    control = Control()
    with YoutubeDL({"quiet": True, "ffmpeg_location": local_media["ffmpeg"]}) as engine:
        processor = VideoOutputPP(engine, "mp4", control)
        encode = processor.run_ffmpeg

        def interrupted(*args):
            encode(*args)
            if cancel:
                control.cancel()
            else:
                raise OSError("Simulated conversion publication failure")

        monkeypatch.setattr(processor, "run_ffmpeg", interrupted)
        with pytest.raises(Cancelled if cancel else OSError):
            processor.run({"filepath": str(source), "ext": "mkv"})
    assert source.read_bytes() == original
    assert destination.read_bytes() == b"existing file must survive"
    assert not list(tmp_path.glob("*.orvilo-convert.*"))
