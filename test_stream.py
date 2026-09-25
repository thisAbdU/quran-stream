"""Self-checks: python3 test_stream.py (no test framework needed)."""

import main
import streaming
import youtube
from streaming import QUALITY_PROFILES, build_audio_cmd, build_video_cmd, build_rtmp_url, safe_rtmp
from youtube import Input, ResolvedStream, YouTubeError

KEY = "SUPERSECRETKEY"
RTMP = build_rtmp_url("rtmps://dc.rtmp.t.me/s", KEY)


def test_m3u():
    stations = main.load_stations()
    assert len(stations) > 100, len(stations)
    assert all(s["url"].startswith("http") for s in stations)
    assert main.parse_m3u("http://a/x\nhttp://a/x\n#c\n\n") == [{"id": 1, "name": "X", "url": "http://a/x"}]
    assert main.slug_to_name("ahmed_al-ajmi") == "Ahmed Al Ajmi"


def test_url_validation():
    good = {
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "youtu.be/dQw4w9WgXcQ": "dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30": "dQw4w9WgXcQ",
        "https://www.youtube.com/live/jNQXAC9IVRw": "jNQXAC9IVRw",
        "https://youtube.com/shorts/jNQXAC9IVRw": "jNQXAC9IVRw",
    }
    for url, vid in good.items():
        assert youtube.validate_youtube_url(url) == f"https://www.youtube.com/watch?v={vid}", url
    for bad in ["", "https://evil.com/watch?v=dQw4w9WgXcQ", "file:///etc/passwd", "https://youtube.com/",
                "https://www.youtube.com/watch?v=; rm -rf /", "javascript:alert(1)",
                "https://youtube.evil.com/watch?v=dQw4w9WgXcQ"]:
        try:
            youtube.validate_youtube_url(bad)
            raise AssertionError(f"accepted bad url: {bad!r}")
        except YouTubeError as e:
            assert e.permanent


def test_audio_pipeline():
    cmd, codecs = build_audio_cmd("https://Qurango.net/radio/x", RTMP)
    assert cmd[0] == "ffmpeg" and cmd[-1] == RTMP and cmd[-2] == "flv"
    assert "-vn" in cmd and "aac" in cmd, cmd          # audio-only, not video
    assert "libx264" not in cmd
    assert cmd.index("-i") < cmd.index("-vn")
    assert codecs["video"] is None


def _resolved(vcodec="avc1.64001f", acodec="mp4a.40.2", height=720, split=True, hls=False, v_kbps=1200):
    inputs = [Input("https://v"), Input("https://a")] if split else [Input("https://both")]
    return ResolvedStream(title="T", is_live=hls, inputs=inputs, vcodec=vcodec,
                          acodec=acodec, height=height, v_kbps=v_kbps, is_hls=hls)


def test_video_copy_vs_transcode():
    med = QUALITY_PROFILES["medium"]

    # h264 720p + aac under a 720p profile -> copy both, no encoder at all
    cmd, d = build_video_cmd(_resolved(), RTMP, med, realtime=True)
    assert cmd.count("copy") == 2 and "libx264" not in cmd, cmd
    assert "-map" in cmd and cmd[cmd.index("-map") + 1] == "0:v:0"
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "1:a:0"  # audio from 2nd input
    assert "(copy)" in d["video"] and "(copy)" in d["audio"]

    # vp9 + opus -> transcode both
    cmd, d = build_video_cmd(_resolved(vcodec="vp9", acodec="opus"), RTMP, med, realtime=True)
    assert "libx264" in cmd and "-c:a" in cmd and "copy" not in cmd
    assert "yuv420p" in cmd and "veryfast" in cmd

    # h264 + opus -> copy video only
    cmd, _ = build_video_cmd(_resolved(acodec="opus"), RTMP, med, realtime=True)
    assert cmd[cmd.index("-c:v") + 1] == "copy" and cmd[cmd.index("-c:a") + 1] == "aac"

    # 1080p source on a 480p profile -> must downscale
    cmd, _ = build_video_cmd(_resolved(height=1080), RTMP, QUALITY_PROFILES["low"], realtime=True)
    assert "-vf" in cmd and cmd[cmd.index("-vf") + 1] == "scale=-2:480"
    assert "-b:v" in cmd and cmd[cmd.index("-b:v") + 1] == "800k"

    # HLS live: single input, aac copy needs the ADTS filter, no -re
    cmd, _ = build_video_cmd(_resolved(split=False, hls=True), RTMP, med, realtime=False)
    assert "-re" not in cmd and "aac_adtstoasc" in cmd
    assert cmd[cmd.index("-map", cmd.index("-map") + 1) + 1] == "0:a:0"

    # recorded video is paced with -re once per input
    cmd, _ = build_video_cmd(_resolved(), RTMP, med, realtime=True)
    assert cmd.count("-re") == 2


def test_fat_source_is_capped_not_copied():
    """Picking Low must cap the uplink even if the source is H.264 at 480p."""
    low = QUALITY_PROFILES["low"]
    cmd, d = build_video_cmd(_resolved(height=480, v_kbps=400), RTMP, low, realtime=True)
    assert cmd[cmd.index("-c:v") + 1] == "copy"            # cheap source -> copy
    cmd, d = build_video_cmd(_resolved(height=480, v_kbps=4000), RTMP, low, realtime=True)
    assert "libx264" in cmd and cmd[cmd.index("-b:v") + 1] == "800k", cmd
    assert "-vf" not in cmd                                 # already 480p, no rescale


def test_quality_profiles_actually_differ():
    low, med, high = (QUALITY_PROFILES[k] for k in ("low", "medium", "high"))
    assert low.v_kbps < med.v_kbps < high.v_kbps
    assert low.height < med.height < high.height
    assert low.v_kbps * 2 < med.v_kbps  # "Low" must be a real saving, not a nudge
    for name, p in QUALITY_PROFILES.items():
        cmd, _ = build_video_cmd(_resolved(vcodec="vp9", height=1080, v_kbps=9000), RTMP, p, realtime=True)
        assert cmd[cmd.index("-b:v") + 1] == f"{p.v_kbps}k"
        assert cmd[cmd.index("-maxrate") + 1] == f"{p.v_kbps}k"


def test_secrets_never_leak():
    assert build_rtmp_url("rtmp://h/app/", KEY) == f"rtmp://h/app/{KEY}"
    assert KEY not in safe_rtmp("rtmps://dc.rtmp.t.me/s")
    s = streaming._Session(source_type="quran", url="u", name="n", quality="low",
                           playback="once", rtmp_url=RTMP, key=KEY)
    assert KEY not in s.scrub(f"Failed to open {RTMP}: broken pipe")
    assert KEY not in s.scrub(f"key was {KEY}")
    # status payload must never carry the key or the assembled rtmp url
    streaming.manager._session = s
    body = repr(streaming.manager.get_status())
    streaming.manager._session = None
    assert KEY not in body and RTMP not in body and "rtmp" not in body.lower()


def test_start_rejects_bad_input():
    m = streaming.StreamManager()
    for args in [("http://s", "", KEY), ("http://s", "rtmp://h/a", ""), ("http://s", "http://h/a", KEY)]:
        try:
            m.start_quran_stream(*args)
            raise AssertionError(f"accepted {args}")
        except streaming.StreamError as e:
            assert e.permanent
    try:
        m.start_quran_stream("ftp://x/y", "rtmp://h/a", KEY)
        raise AssertionError("accepted non-http station url")
    except streaming.StreamError:
        pass
    try:
        m.start_youtube_video("https://youtu.be/dQw4w9WgXcQ", "rtmp://h/a", KEY, "medium", "rewind")
        raise AssertionError("accepted bad playback mode")
    except streaming.StreamError:
        pass
    assert m.get_status()["running"] is False


def test_backoff_schedule():
    assert streaming.BACKOFF == (2, 5, 10, 30)
    s = streaming._Session(source_type="quran", url="u", name="n", quality="low",
                           playback="once", rtmp_url=RTMP, key=KEY)
    s.stop.set()  # makes _backoff return immediately
    delays = []
    for _ in range(6):
        streaming.manager._backoff(s, "x")
        delays.append(streaming.BACKOFF[min(s.reconnect_attempt - 1, len(streaming.BACKOFF) - 1)])
    assert delays == [2, 5, 10, 30, 30, 30], delays
    assert s.state == streaming.RECONNECTING


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall checks passed")
