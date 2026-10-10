# Your first download

[← Back to Orvilo](../README.md)

On first launch, Orvilo offers to download the video tools used for merging and
conversion. Choose **Install FFmpeg** for that one-time setup, or select a folder
containing an existing FFmpeg and FFprobe installation. The tools are downloaded
directly from Gyan, an FFmpeg Windows build publisher, and their checksums are
verified. Python does not need to be installed separately.

Paste a link on **Download**, choose a format and quality, and select
**Download**. Orvilo loads the title, thumbnail, uploader, duration, and reported
qualities in the background. You can also drag a link into the window or paste
several links on separate lines.

For playlists, channels, profiles, and multi-video posts, select the items you
want using the checkboxes. Very large collections can take longer to load.
Only items your current session can access are available.

## Choose what to keep

| Choice | What it does |
| --- | --- |
| Video | Saves video up to the selected resolution, with audio, in your chosen video format. MP4 is the default. |
| Audio only | Converts the available audio to MP3, M4A, FLAC, WAV, or Opus. |
| Clip | Saves a start–end range. Enter seconds, `MM:SS`, or `HH:MM:SS`. |
| Subtitles | Saves available subtitles as SRT or embeds them in video. Enter language codes such as `en`, `hi`, `en,hi`, or `all`. |
| Thumbnail and metadata | Saves artwork and includes supported title, artist, and other metadata. |

Open **More options** for clip, subtitle, and artwork controls. Subtitle tracks
must exist in the language you select; automatic captions depend on the site.

### Pick a video format

| Video format | Best for |
| --- | --- |
| MP4 · Premiere | H.264 video, AAC audio, 8-bit 4:2:0 pixels, and constant frame rate for broad editing compatibility. |
| MOV · H.264 | The same editing codecs in a QuickTime container. |
| MOV · ProRes 422 | ProRes 422 video with PCM audio for editing; expect much larger files. |
| MKV · original | Retains the downloaded codecs without an extra video encode. |
| WebM · VP9 | VP9/Opus for browsers and playback; not the recommended Premiere option. |

Choose **MP4 · Premiere** when you plan to import the video into Premiere.
The app performs a real conversion, so changing the extension is not enough.
The detected frame rate becomes constant; the selected resolution is retained
with at most one pixel of padding where even dimensions are required. HDR is
tone-mapped to SDR for MP4, MOV/H.264, and WebM; ProRes retains source HDR tags.
Conversion takes extra time and may slightly change the picture. A ProRes
conversion does not restore quality that was lost in the source.

These codecs and containers are listed in [Adobe's supported format guide](https://helpx.adobe.com/premiere/desktop/organize-media/import-files/supported-file-formats.html).
Choose **Save .srt file** to import captions separately into your editor.
Embedded captions use MOV text for MP4/MOV and WebVTT for WebM. ProRes and WebM
cover artwork is saved alongside the video.

Your video-format choice is remembered. Queue retries and history re-downloads
keep the format of that job. Downloads queued by an older app version keep MKV
so their partial files can still be resumed.

## Manage the queue

The queue shows transfer progress, speed, and estimated time. Pause, resume,
cancel, or retry a job from its card. In **Settings**, choose between one and six
parallel downloads.

If you restart Orvilo, unfinished jobs return **paused**. Resume them when you
are ready. Keep the original partial files and download folder to allow
resumption where supported. After changing cookies, proxy, or runtime settings,
use **Retry** to apply those settings to a failed job.

Closing the window can keep Orvilo in the Windows system tray. To stop it
completely, choose **Quit** from the tray menu. Tray notifications follow your
Windows notification settings.

## Find something again

**History** records completed downloads, including their original links, chosen
quality, size, date, and saved location. Search or filter by site, date, and
media type. Open a file, reveal its folder, copy its link, or download it again.

Deleting a history record keeps the file unless you also select **Also delete
the saved media file**. Clearing history always keeps files. Optional deletion
removes only the main media file; subtitle, artwork, and partial files remain.
Files moved or removed outside Orvilo are marked as missing.

## Make it yours

Settings includes dark and light themes, accent color, clipboard detection,
download folder, filenames, site subfolders, parallel downloads, a per-download
speed limit, cookies, and a proxy. Select **Save changes** when you are finished.

For login-only content, sign in normally in a supported browser, then choose
that browser under cookies. Orvilo uses that existing session; it does not ask
for your account password. You can also select a Netscape-format cookies file.

## Troubleshooting

| Message or symptom | What to try |
| --- | --- |
| Login required / age restricted | Enable cookies for a browser session that can already play the video. |
| Browser cookies cannot be read | Windows or browser encryption may prevent Chrome/Edge access. Try Firefox or a Netscape cookies file. |
| Private or unavailable video | Confirm the link opens in your browser with the same account. A private video still requires permission. |
| An interrupted Bilibili transfer | Update to the latest release. Keep the partial files, then choose Retry. The app can use backup servers supplied by Bilibili. |
| A site that used to work stops working | Use the engine update in Settings, restart Orvilo, and retry. Site changes can still require an upstream fix. |
| Not supported yet | The installed engine and generic fallback could not extract the link. A custom extractor may be needed. |
| No notification | Check Windows notification settings and the Orvilo tray icon. |
| App appears to be closed | Check the system tray. Closing the window can leave it running there. |

When reporting a problem, include your Windows version, Orvilo version, the
message shown, and the steps that caused it. A public example URL is helpful
only if you have permission to share it. Do not include cookies, private URLs,
browser profiles, account credentials, or unreviewed settings files.

## Transfer and format details

Pause is cooperative at progress checkpoints. A blocked request must return or
time out before the action takes effect. Paused live workers retain their
parallel slot; cancel/retry frees a slot. HTTP and native HLS partial downloads
can resume where the server supports it.

FFmpeg merging, conversion, and range downloads finish their current subprocess
before cancellation is observed. The queue shows an indeterminate processing
bar while an accurate percentage or ETA is unavailable. Clips cannot pause,
resume by byte offset, use a SOCKS proxy, or honor the byte-rate limit. Orvilo
rejects conflicting clip settings with an explanation. Precise cuts may
re-encode the video.

Full-video remuxing retains the original video codec. Resolution choices are
ceilings: Orvilo selects the best available stream at or below your selection.
FLAC and WAV cannot recover quality already lost in the original audio. WAV
cover art and audio-only subtitles are saved as separate files.

Live, expired, region-limited, and protected streams may be unavailable. DRM
circumvention is not supported.

## Privacy and local storage

There is no Orvilo account, telemetry, or cloud backend. Network requests go to
the links you submit, their media and thumbnail servers, a proxy you configure,
and dependency providers when you request installation or an update. Clipboard
detection is optional and offers links in the app rather than sending clipboard
contents to an Orvilo service.

Preferences, history, queue state, caches, video tools, and rotating logs are
stored under `%LOCALAPPDATA%\Orvilo`. Logging redacts URLs and credentials, but
review any diagnostic material before sharing it. Your download folder is separate.

Engine updates come from the official yt-dlp and matching EJS packages on PyPI,
are checked for hash integrity and compatibility, and activate after restart.
Local site plugins are trusted Python code that you install yourself.
