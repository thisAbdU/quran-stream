from pathlib import Path
from typing import Dict, List
from functools import lru_cache
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from streaming import (
    DEFAULT_QUALITY, PLAYBACK_MODES, SOURCE_TYPES, StreamError, manager,
)
from youtube import YouTubeError

BASE_DIR = Path(__file__).parent
M3U_PATH = BASE_DIR / "mp3quran_radios.m3u"
TEMPLATES_DIR = BASE_DIR / "templates"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("quranstream")

app = FastAPI(title="QuranStream Local Controller")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ------------------------------------------------------------------ stations

def slug_to_name(slug: str) -> str:
    s = slug.strip().replace("-", " ").replace("_", " ")
    return " ".join(part for part in s.split() if part).title()


def parse_m3u(content: str) -> List[Dict[str, str]]:
    stations: List[Dict[str, str]] = []
    seen = set()
    for line in content.splitlines():
        url = line.strip()
        if not url or url.startswith("#") or url in seen:
            continue
        seen.add(url)
        slug = url.rstrip("/").split("/")[-1]
        stations.append({"id": len(stations) + 1, "name": slug_to_name(slug) or url, "url": url})
    return stations


@lru_cache(maxsize=1)
def _parse_cached(_mtime: float) -> List[Dict[str, str]]:
    return parse_m3u(M3U_PATH.read_text(encoding="utf-8"))


def load_stations() -> List[Dict[str, str]]:
    """Parsed once and re-parsed only when the M3U file changes on disk."""
    return _parse_cached(M3U_PATH.stat().st_mtime)


# ---------------------------------------------------------------------- API

class StartRequest(BaseModel):
    url: str
    rtmp_server: str
    key: str
    source_type: str = "quran"
    quality: str = DEFAULT_QUALITY
    playback: str = "once"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/stations")
async def get_stations():
    try:
        return load_stations()
    except Exception as exc:
        logger.error("Failed to read M3U file: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Failed to read the station list."})


@app.post("/api/start")
def api_start(payload: StartRequest):
    source_type = payload.source_type or "quran"
    if source_type not in SOURCE_TYPES:
        return JSONResponse(status_code=400, content={"error": "Unknown source type."})
    if payload.playback not in PLAYBACK_MODES:
        return JSONResponse(status_code=400, content={"error": "Unknown playback mode."})

    try:
        if source_type == "quran":
            name = next((s["name"] for s in load_stations() if s["url"] == payload.url), None)
            result = manager.start_quran_stream(payload.url, payload.rtmp_server, payload.key, name)
        elif source_type == "youtube_live":
            result = manager.start_youtube_live(payload.url, payload.rtmp_server, payload.key, payload.quality)
        else:
            result = manager.start_youtube_video(
                payload.url, payload.rtmp_server, payload.key, payload.quality, payload.playback
            )
    except (StreamError, YouTubeError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        logger.exception("Unexpected error while starting the stream")
        return JSONResponse(status_code=500, content={"error": "Failed to start the stream. Check the server logs."})
    return result


@app.post("/api/stop")
def api_stop():
    return manager.stop_stream()


@app.get("/api/status")
async def api_status():
    return manager.get_status()



@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down, stopping stream...")
    manager.stop_stream()
