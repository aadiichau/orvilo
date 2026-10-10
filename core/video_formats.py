"""Explicit video containers and codecs for playback and editing workflows."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Protocol

from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
from yt_dlp.utils import PostProcessingError, replace_extension


@dataclass(frozen=True)
class VideoFormat:
    """A named output profile with an honest explanation of its tradeoff."""

    label: str
    extension: str
    hint: str
    filename_tag: str


VIDEO_FORMATS = {
    "mp4": VideoFormat("MP4 · Premiere", "mp4", "H.264 + AAC · constant frame rate for editing · high-quality conversion", "MP4"),
    "mov": VideoFormat("MOV · H.264", "mov", "QuickTime H.264 + AAC · constant frame rate · high-quality conversion", "MOV H264"),
    "prores": VideoFormat("MOV · ProRes 422", "mov", "ProRes 422 + PCM · smooth editing in Premiere · much larger files", "MOV ProRes422"),
    "mkv": VideoFormat("MKV · original", "mkv", "Original video and audio codecs · no extra video conversion", ""),
    "webm": VideoFormat("WebM · VP9", "webm", "VP9 + Opus · for browsers and playback · slower conversion", "WebM"),
}


class _Control(Protocol):
    def checkpoint(self) -> None:
        """Observe the worker's cancellation and pause controls."""


def _frame_rate(stream: dict[str, Any]) -> str:
    """Retain rational frame rates while rejecting corrupt or extreme values."""
    for key in ("avg_frame_rate", "r_frame_rate"):
        try:
            rate = Fraction(str(stream.get(key) or "0"))
            if Fraction(1, 10) <= rate <= 240:
                return f"{rate.numerator}/{rate.denominator}"
        except (ValueError, ZeroDivisionError):
            continue
    return "30/1"


class VideoOutputPP(FFmpegPostProcessor):
    """Encode a selected profile before subtitles, metadata, and final moves."""

    def __init__(self, engine: Any, profile: str, control: _Control) -> None:
        super().__init__(engine)
        self.profile = profile
        self.control = control

    def run(self, info: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        """Publish a complete converted file atomically and preserve the source on failure."""
        self.control.checkpoint()
        profile = VIDEO_FORMATS[self.profile]
        source = Path(info["filepath"])
        destination = Path(replace_extension(str(source), profile.extension, info["ext"]))
        temporary = destination.with_name(destination.stem + ".orvilo-convert." + profile.extension)
        try:
            # Recent FFprobe versions expose some HDR tags only after decoding.
            metadata = self.get_metadata_object(str(source), opts=["-select_streams", "V:0", "-show_frames", "-read_intervals", "%+#32"])
            video = next((stream for stream in metadata.get("streams", [])
                          if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")), None)
            if video is None:
                raise PostProcessingError("This link contains no video. Choose Audio only instead.")
            frame = next((item for item in metadata.get("frames", []) if item.get("media_type") == "video"), {})
            video = {**video, **{key: frame[key] for key in ("color_transfer", "color_primaries", "color_space") if key in frame}}
            args = ["-map", "0:V:0", "-map", "0:a:0?", "-map_metadata", "0", "-map_chapters", "0",
                    "-r", _frame_rate(video), "-fps_mode", "cfr"]
            pad = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
            if self.profile != "prores" and video.get("color_transfer") in {"smpte2084", "arib-std-b67"}:
                pad = ("zscale=t=linear:npl=100,format=gbrpf32le,tonemap=tonemap=hable:desat=0,"
                       "zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p," + pad)
                args += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
            args += ["-vf", pad]
            if self.profile == "prores":
                args += ["-c:v", "prores_ks", "-profile:v", "2", "-pix_fmt", "yuv422p10le",
                         "-c:a", "pcm_s16le", "-ar", "48000"]
            elif self.profile == "webm":
                args += ["-c:v", "libvpx-vp9", "-crf", "24", "-b:v", "0", "-deadline", "good",
                         "-cpu-used", "4", "-row-mt", "1", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", "160k"]
            else:
                args += ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart"]
            self.to_screen(f"Preparing {profile.label}; Destination: {destination}")
            self.run_ffmpeg(str(source), str(temporary), args)
            self.control.checkpoint()
            if not temporary.is_file() or not temporary.stat().st_size:
                raise PostProcessingError("Video conversion produced an empty file. Retry the download.")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        info.update(filepath=str(destination), ext=profile.extension, format=profile.extension)
        return ([str(source)] if source != destination else []), info
