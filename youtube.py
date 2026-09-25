"""YouTube URL validation and stream resolution through yt-dlp.

The rest of the app only knows about :class:`ResolvedStream`; swapping yt-dlp
for something else later means rewriting :func:`resolve` and nothing else.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com",
    "youtu.be", "www.youtu.be",
}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeError(Exception):
    """Failure with a message that is safe to show the operator."""

    def __init__(self, message: str, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


@dataclass
class Input:
    url: str
    headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ResolvedStream:
    """One or two media inputs plus what FFmpeg needs to know about them."""

    title: str
    is_live: bool
    inputs: List[Input]
    vcodec: str = ""
    acodec: str = ""
    height: Optional[int] = None
    v_kbps: Optional[float] = None
    duration: Optional[float] = None
    is_hls: bool = False

    @property
    def split(self) -> bool:
        return len(self.inputs) > 1


def validate_youtube_url(url: str) -> str:
    """Return the cleaned URL or raise :class:`YouTubeError`.

    Only real YouTube watch/live/shorts/youtu.be links get through; everything
    else is rejected before it can reach an external command.
    """
    url = (url or "").strip()
    if not url:
        raise YouTubeError("Please enter a YouTube URL.", permanent=True)
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise YouTubeError("Invalid YouTube URL.", permanent=True)
    host = (parsed.hostname or "").lower()
    if host not in _HOSTS:
        raise YouTubeError("Invalid YouTube URL - only youtube.com and youtu.be links are supported.", permanent=True)

    path = parsed.path.rstrip("/")
    if host.endswith("youtu.be"):
        vid = path.lstrip("/")
    elif path == "/watch":
        vid = (parse_qs(parsed.query).get("v") or [""])[0]
    elif path.startswith(("/live/", "/shorts/", "/embed/", "/v/")):
        vid = path.split("/")[2] if len(path.split("/")) > 2 else ""
    else:
        raise YouTubeError("Invalid YouTube URL - expected a watch, live or youtu.be link.", permanent=True)

    if not _VIDEO_ID.match(vid):
        raise YouTubeError("Invalid YouTube URL - no video id found.", permanent=True)
    return f"https://www.youtube.com/watch?v={vid}"


def _format_selector(max_height: int) -> str:
    """Prefer H.264 + AAC at or below max_height so FFmpeg can stream-copy."""
    h = max_height
    return (
        f"bv*[vcodec^=avc1][height<={h}]+ba[acodec^=mp4a]/"
        f"b[vcodec^=avc1][acodec^=mp4a][height<={h}]/"
        f"bv*[height<={h}]+ba/"
        f"b[height<={h}]/b"
    )


_FRIENDLY = (
    ("private", "This YouTube video is private."),
    ("members-only", "This YouTube video is members-only."),
    ("age", "This YouTube video is age-restricted and cannot be streamed."),
    ("removed", "This YouTube video is unavailable."),
    ("unavailable", "This YouTube video is unavailable."),
    ("not available", "This YouTube video is unavailable."),
    ("premieres in", "This YouTube premiere has not started yet."),
    ("live event will begin", "This YouTube live stream has not started yet."),
    ("is not a valid url", "Invalid YouTube URL."),
    ("sign in", "This YouTube video requires sign-in and cannot be streamed."),
)


def _translate(message: str) -> YouTubeError:
    low = message.lower()
    for needle, friendly in _FRIENDLY:
        if needle in low:
            return YouTubeError(friendly, permanent=True)
    return YouTubeError("Unable to resolve YouTube stream.")


def resolve(url: str, max_height: int = 720) -> ResolvedStream:
    """Resolve a YouTube URL to direct media URLs. Never downloads the video."""
    url = validate_youtube_url(url)
    try:
        import yt_dlp  # imported lazily: keeps app startup fast
    except ImportError:
        raise YouTubeError("yt-dlp is not installed on the server.", permanent=True)

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 15,
        "format": _format_selector(max_height),
    }
    logger.info("Resolving YouTube URL %s (cap %sp)", url, max_height)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # yt-dlp raises DownloadError and friends
        logger.error("YouTube resolution failed: %s", exc)
        raise _translate(str(exc))

    if not info:
        raise YouTubeError("Unable to resolve YouTube stream.")

    formats = info.get("requested_formats") or [info]
    inputs = [Input(url=f["url"], headers=dict(f.get("http_headers") or {})) for f in formats if f.get("url")]
    if not inputs:
        raise YouTubeError("Unable to resolve YouTube stream.")

    video = next((f for f in formats if f.get("vcodec") not in (None, "none")), formats[0])
    audio = next((f for f in formats if f.get("acodec") not in (None, "none")), formats[-1])
    resolved = ResolvedStream(
        title=info.get("title") or "YouTube",
        is_live=bool(info.get("is_live")),
        inputs=inputs,
        vcodec=(video.get("vcodec") or ""),
        acodec=(audio.get("acodec") or ""),
        height=video.get("height"),
        v_kbps=video.get("tbr"),
        duration=info.get("duration"),
        is_hls=any("m3u8" in (f.get("protocol") or "") for f in formats),
    )
    logger.info(
        "YouTube stream resolved: %r live=%s %sp %s/%s (%d input%s)",
        resolved.title, resolved.is_live, resolved.height, resolved.vcodec,
        resolved.acodec, len(inputs), "s" if resolved.split else "",
    )
    return resolved
