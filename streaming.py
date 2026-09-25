"""FFmpeg pipelines and the single-active-stream manager.

One FFmpeg process per stream, supervised by one thread that restarts it with
backoff. Audio sources (Quran radio) stay audio-only; YouTube sources get a
real H.264/AAC video pipeline that stream-copies whatever it can.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import youtube
from youtube import ResolvedStream, YouTubeError

logger = logging.getLogger(__name__)

SOURCE_TYPES = ("quran", "youtube_live", "youtube_video")
PLAYBACK_MODES = ("once", "loop")

# OFFLINE -> STARTING -> LIVE -> (RECONNECTING -> STARTING)* -> STOPPING -> OFFLINE
OFFLINE, STARTING, LIVE, RECONNECTING, STOPPING, ERROR = (
    "OFFLINE", "STARTING", "LIVE", "RECONNECTING", "STOPPING", "ERROR",
)

BACKOFF = (2, 5, 10, 30)  # seconds; last value repeats


@dataclass(frozen=True)
class Quality:
    label: str
    height: int
    v_kbps: int
    a_kbps: int


QUALITY_PROFILES: Dict[str, Quality] = {
    "low": Quality("480p", 480, 800, 64),
    "medium": Quality("720p", 720, 1800, 128),
    "high": Quality("1080p", 1080, 3500, 128),
}
DEFAULT_QUALITY = "medium"


class StreamError(Exception):
    """Operator-facing failure."""

    def __init__(self, message: str, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


def build_rtmp_url(server: str, key: str) -> str:
    server, key = server.strip(), key.strip()
    if not server:
        return key
    return f"{server.rstrip('/')}/{key}"


def safe_rtmp(server: str) -> str:
    """Loggable form of the destination - host and app only, never the key."""
    try:
        p = urlparse(server.strip())
        return f"{p.scheme}://{p.hostname}{p.path.rstrip('/')}/***"
    except Exception:
        return "***"


def _http_opts(headers: Dict[str, str], realtime: bool, at_eof: bool = False) -> List[str]:
    opts = [
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
        "-rw_timeout", "20000000",  # abort a stalled read instead of hanging forever
    ]
    if at_eof:
        opts += ["-reconnect_at_eof", "1"]
    headers = dict(headers or {})
    ua = headers.pop("User-Agent", None)
    headers.pop("Accept-Encoding", None)  # FFmpeg cannot decode compressed bodies
    if ua:
        opts += ["-user_agent", ua]
    if headers:
        opts += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
    if realtime:
        opts += ["-re"]
    return opts


def build_audio_cmd(source_url: str, rtmp_url: str) -> Tuple[List[str], Dict[str, str]]:
    """Quran radio: audio-only AAC to RTMP, one process, FFmpeg's own reconnect."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    cmd += _http_opts({}, realtime=True, at_eof=True)
    cmd += [
        "-i", source_url,
        "-vn",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-flags", "+low_delay", "-fflags", "nobuffer",
        "-f", "flv", rtmp_url,
    ]
    return cmd, {"video": None, "audio": "AAC 128 kbps"}


def build_video_cmd(
    resolved: ResolvedStream, rtmp_url: str, profile: Quality, realtime: bool
) -> Tuple[List[str], Dict[str, str]]:
    """YouTube: H.264 + AAC over FLV, copying whichever stream is already fine."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    for inp in resolved.inputs:
        cmd += _http_opts(inp.headers, realtime=realtime)
        cmd += ["-i", inp.url]

    if resolved.split:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]

    height = resolved.height or 0
    # Copy only if the source is already H.264, within the chosen resolution, and
    # not fat enough to blow past the bitrate the operator asked for.
    v_copy = (
        resolved.vcodec.startswith(("avc1", "h264"))
        and 0 < height <= profile.height
        and (resolved.v_kbps or 0) <= profile.v_kbps * 1.5
    )
    a_copy = resolved.acodec.startswith(("mp4a", "aac"))

    if v_copy:
        cmd += ["-c:v", "copy"]
        video_desc = f"H.264 {height}p (copy)"
    else:
        if height > profile.height or height == 0:
            cmd += ["-vf", f"scale=-2:{profile.height}"]
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-profile:v", "main",
            "-pix_fmt", "yuv420p",
            "-b:v", f"{profile.v_kbps}k",
            "-maxrate", f"{profile.v_kbps}k",
            "-bufsize", f"{profile.v_kbps * 2}k",
            "-g", "60", "-keyint_min", "60", "-sc_threshold", "0",
        ]
        video_desc = f"H.264 {min(height, profile.height) or profile.height}p {profile.v_kbps} kbps"

    if a_copy:
        cmd += ["-c:a", "copy"]
        if resolved.is_hls:
            cmd += ["-bsf:a", "aac_adtstoasc"]  # ADTS from HLS -> raw AAC for FLV
        audio_desc = "AAC (copy)"
    else:
        cmd += ["-c:a", "aac", "-b:a", f"{profile.a_kbps}k", "-ar", "44100", "-ac", "2"]
        audio_desc = f"AAC {profile.a_kbps} kbps"

    cmd += ["-max_muxing_queue_size", "1024", "-f", "flv", rtmp_url]
    return cmd, {"video": video_desc, "audio": audio_desc}


@dataclass
class _Session:
    source_type: str
    url: str
    name: str
    quality: str
    playback: str
    rtmp_url: str  # secret - never serialised
    key: str       # secret - kept only to scrub it back out of FFmpeg output
    state: str = STARTING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reconnect_attempt: int = 0
    error: Optional[str] = None
    message: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    speed: Optional[float] = None
    codecs: Dict[str, Optional[str]] = field(default_factory=dict)
    proc: Optional[subprocess.Popen] = None
    stop: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    tail: List[str] = field(default_factory=list)

    def scrub(self, text: str) -> str:
        out = text.replace(self.rtmp_url, "***")
        if self.key:
            out = out.replace(self.key, "***")
        return out


class StreamManager:
    """Owns the one active stream. All mutation goes through the lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._session: Optional[_Session] = None
        self._last: Dict[str, Optional[str]] = {"state": OFFLINE, "error": None, "message": None}

    # ---------------------------------------------------------------- public

    def start_quran_stream(self, url: str, rtmp_server: str, key: str, name: Optional[str] = None) -> Dict:
        if urlparse(url or "").scheme not in ("http", "https"):
            raise StreamError("Invalid station URL.", permanent=True)
        return self._start("quran", url, rtmp_server, key, name or url, DEFAULT_QUALITY, "loop")

    def start_youtube_live(self, url: str, rtmp_server: str, key: str, quality: str = DEFAULT_QUALITY) -> Dict:
        url = youtube.validate_youtube_url(url)
        return self._start("youtube_live", url, rtmp_server, key, "YouTube Live", quality, "loop")

    def start_youtube_video(
        self, url: str, rtmp_server: str, key: str, quality: str = DEFAULT_QUALITY, playback: str = "once"
    ) -> Dict:
        url = youtube.validate_youtube_url(url)
        if playback not in PLAYBACK_MODES:
            raise StreamError("Unknown playback mode.", permanent=True)
        return self._start("youtube_video", url, rtmp_server, key, "YouTube Video", quality, playback)

    def stop_stream(self) -> Dict[str, str]:
        with self._lock:
            session = self._session
            self._session = None
            if session:
                self._last = {"state": STOPPING, "error": None, "message": None}
        if session:
            session.state = STOPPING
            session.stop.set()
            self._kill(session)
            if session.thread and session.thread.is_alive():
                session.thread.join(timeout=6)
            logger.info("Stream stopped (%s)", session.source_type)
            self._last = {"state": OFFLINE, "error": None, "message": "Stream stopped"}
        return {"status": "stopped", "state": OFFLINE}

    def get_status(self) -> Dict:
        with self._lock:
            s = self._session
            if not s:
                return {"running": False, "state": self._last["state"], "error": self._last["error"],
                        "message": self._last["message"]}
            return {
                "running": s.state in (STARTING, LIVE, RECONNECTING),
                "state": s.state,
                "source_type": s.source_type,
                "name": s.name,
                "url": s.url,
                "started_at": s.started_at.isoformat(timespec="seconds"),
                "uptime_s": int((datetime.now(timezone.utc) - s.started_at).total_seconds()),
                "reconnect_attempt": s.reconnect_attempt,
                "quality": s.quality if s.source_type != "quran" else None,
                "playback": s.playback if s.source_type == "youtube_video" else None,
                "bitrate_kbps": s.bitrate_kbps,
                "connection": self._connection(s),
                "video": s.codecs.get("video"),
                "audio": s.codecs.get("audio"),
                "error": s.error,
                "message": s.message,
            }

    # --------------------------------------------------------------- internal

    @staticmethod
    def _connection(s: _Session) -> str:
        if s.state == RECONNECTING:
            return "Reconnecting"
        if s.state != LIVE:
            return "-"
        if s.speed is not None and s.speed < 0.95:
            return "Unstable"
        return "Stable"

    def _start(self, source_type: str, url: str, rtmp_server: str, key: str,
               name: str, quality: str, playback: str) -> Dict:
        if quality not in QUALITY_PROFILES:
            raise StreamError("Unknown quality profile.", permanent=True)
        rtmp_server = (rtmp_server or "").strip()
        key = (key or "").strip()
        if not rtmp_server or not key:
            raise StreamError("RTMP server and stream key are required.", permanent=True)
        if not rtmp_server.startswith(("rtmp://", "rtmps://")):
            raise StreamError("RTMP server must start with rtmp:// or rtmps://", permanent=True)

        self.stop_stream()  # never run two pipelines at once

        session = _Session(
            source_type=source_type, url=url, name=name, quality=quality, playback=playback,
            rtmp_url=build_rtmp_url(rtmp_server, key), key=key,
        )
        with self._lock:
            self._session = session
        logger.info("Starting %s stream -> %s | source=%s quality=%s playback=%s",
                    source_type, safe_rtmp(rtmp_server), url, quality, playback)
        session.thread = threading.Thread(target=self._supervise, args=(session,),
                                          name="stream-supervisor", daemon=True)
        session.thread.start()
        return {"status": "starting", "state": STARTING, "source_type": source_type, "name": name}

    def _build_cmd(self, s: _Session) -> Tuple[List[str], Dict[str, str], bool]:
        """Returns (argv, codec description, finite) - resolves YouTube URLs fresh."""
        if s.source_type == "quran":
            cmd, codecs = build_audio_cmd(s.url, s.rtmp_url)
            return cmd, codecs, False

        profile = QUALITY_PROFILES[s.quality]
        try:
            resolved = youtube.resolve(s.url, max_height=profile.height)
        except YouTubeError as exc:
            raise StreamError(str(exc), permanent=exc.permanent)

        if s.source_type == "youtube_live" and not resolved.is_live:
            logger.warning("URL is not a live broadcast; streaming it as a recorded video")
        s.name = resolved.title
        cmd, codecs = build_video_cmd(resolved, s.rtmp_url, profile, realtime=not resolved.is_live)
        return cmd, codecs, not resolved.is_live

    def _supervise(self, s: _Session) -> None:
        """Start FFmpeg, watch it, restart it with backoff until told to stop."""
        while not s.stop.is_set():
            try:
                cmd, codecs, finite = self._build_cmd(s)
            except StreamError as exc:
                if exc.permanent:
                    self._fail(s, str(exc))
                    return
                logger.error("Source resolution failed: %s", exc)
                if not self._backoff(s, str(exc)):
                    return
                continue

            s.codecs = codecs
            s.state = STARTING
            s.bitrate_kbps = s.speed = None
            logger.info("Starting FFmpeg (%s | %s)", codecs.get("video") or "audio only", codecs.get("audio"))

            try:
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    start_new_session=(os.name != "nt"),
                )
            except FileNotFoundError:
                self._fail(s, "FFmpeg is not installed on the server.")
                return
            except Exception as exc:
                logger.error("Failed to launch FFmpeg: %s", s.scrub(str(exc)))
                if not self._backoff(s, "Failed to start FFmpeg."):
                    return
                continue

            s.proc = proc
            threading.Thread(target=self._read_progress, args=(s, proc), daemon=True).start()
            threading.Thread(target=self._read_stderr, args=(s, proc), daemon=True).start()
            code = self._wait(s, proc)

            if s.stop.is_set():
                return
            if code == 0 and finite:
                if s.playback == "loop":
                    logger.info("Playback finished - looping")
                    s.reconnect_attempt = 0
                    s.state = STARTING
                    if s.stop.wait(1):
                        return
                    continue
                logger.info("Playback finished")
                s.state = OFFLINE
                s.message = "Playback finished"
                self._last = {"state": OFFLINE, "error": None, "message": "Playback finished"}
                with self._lock:
                    if self._session is s:
                        self._session = None
                return

            detail = s.tail[-1] if s.tail else f"exit code {code}"
            logger.error("FFmpeg exited with code %s: %s", code, detail)
            if not self._backoff(s, self._explain(detail)):
                return

    def _wait(self, s: _Session, proc: subprocess.Popen) -> int:
        while not s.stop.is_set():
            code = proc.poll()
            if code is not None:
                return code
            time.sleep(0.25)
        return -1

    def _backoff(self, s: _Session, reason: str) -> bool:
        """Sleep before the next attempt. False means we were told to stop."""
        s.reconnect_attempt += 1
        s.state = RECONNECTING
        s.error = reason
        delay = BACKOFF[min(s.reconnect_attempt - 1, len(BACKOFF) - 1)]
        logger.warning("Retrying stream in %ss (attempt %s)", delay, s.reconnect_attempt)
        return not s.stop.wait(delay)

    def _fail(self, s: _Session, message: str) -> None:
        logger.error("Stream failed: %s", message)
        s.state = ERROR
        s.error = message
        self._last = {"state": ERROR, "error": message, "message": None}
        with self._lock:
            if self._session is s:
                self._session = None

    @staticmethod
    def _explain(detail: str) -> str:
        low = detail.lower()
        if "connection refused" in low or "i/o error" in low or "broken pipe" in low:
            return "RTMP connection failed - check the server URL and stream key."
        if "403" in low or "forbidden" in low:
            return "Source rejected the connection (link expired). Reconnecting."
        if "timed out" in low or "timeout" in low:
            return "Stream disconnected (timeout)."
        return "Stream disconnected."

    def _read_progress(self, s: _Session, proc: subprocess.Popen) -> None:
        """FFmpeg -progress output: first block means we are actually LIVE."""
        try:
            for raw in proc.stdout:
                key, _, value = raw.decode("utf-8", "ignore").strip().partition("=")
                value = value.strip()  # FFmpeg right-aligns these values
                if key == "bitrate":
                    try:
                        s.bitrate_kbps = int(float(value.rstrip("kbits/s")))
                    except ValueError:
                        pass
                elif key == "speed":
                    try:
                        s.speed = float(value.rstrip("x"))
                    except ValueError:
                        pass
                elif key == "progress" and s.state in (STARTING, RECONNECTING) and not s.stop.is_set():
                    s.state = LIVE
                    s.error = None
                    s.reconnect_attempt = 0
                    logger.info("RTMP connection established - stream is LIVE")
        except Exception:
            pass

    def _read_stderr(self, s: _Session, proc: subprocess.Popen) -> None:
        try:
            for raw in proc.stderr:
                line = s.scrub(raw.decode("utf-8", "ignore").strip())
                if not line:
                    continue
                s.tail.append(line)
                del s.tail[:-20]
                logger.error("FFmpeg: %s", line)
        except Exception:
            pass

    def _kill(self, s: _Session) -> None:
        proc = s.proc
        if not proc or proc.poll() is not None:
            return
        logger.info("Terminating FFmpeg (PID %s)", proc.pid)
        try:
            if os.name != "nt":
                # process group: takes any child FFmpeg spawned with it
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                if os.name != "nt":
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass
        except (ProcessLookupError, PermissionError):
            pass
        except Exception as exc:
            logger.error("Error stopping FFmpeg: %s", exc)
        s.proc = None


manager = StreamManager()
