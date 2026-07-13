"""yt-helper: metadata + transcript extraction sidecar for the yt-pipeline stack.

Endpoints:
  GET  /health          -> {"status": "ok"}
  POST /video           -> full metadata, description links, thumbnail, transcript

Only n8n talks to this service (internal stack network, no published ports).
"""

import logging
import re

import requests
import yt_dlp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yt-helper")

app = FastAPI(title="yt-helper", version="1.0.0")

URL_RE = re.compile(r"https?://[^\s<>()\[\]\"']+", re.IGNORECASE)

# Tracking params worth stripping from description links
STRIP_PARAMS_RE = re.compile(r"[?&](utm_[a-z]+|si|feature|ref|ref_)=[^&\s]*", re.IGNORECASE)


class VideoRequest(BaseModel):
    video_id: str


def format_duration(seconds) -> str:
    if not seconds:
        return ""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_upload_date(raw) -> str:
    # yt-dlp returns YYYYMMDD
    if raw and len(str(raw)) == 8:
        raw = str(raw)
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return ""


def extract_links(description: str) -> list[str]:
    seen, links = set(), []
    for match in URL_RE.findall(description or ""):
        url = match.rstrip(".,;:!?")
        # Strip common tracking params, then clean dangling ? or &
        url = STRIP_PARAMS_RE.sub("", url).rstrip("?&")
        # If the leading '?' param was stripped, promote the first '&' back to '?'
        if "?" not in url and "&" in url:
            url = url.replace("&", "?", 1)
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def best_thumbnail(video_id: str) -> str:
    maxres = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    fallback = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    try:
        r = requests.head(maxres, timeout=5)
        if r.status_code == 200:
            return maxres
    except requests.RequestException:
        pass
    return fallback


def get_transcript(video_id: str) -> tuple[str, str]:
    """Returns (transcript_text, source) where source is manual|auto-generated|none."""
    try:
        ytt = YouTubeTranscriptApi()
        transcript_list = ytt.list(video_id)

        transcript, source = None, "none"
        # Prefer manually created English captions, then any manual, then auto-generated
        try:
            transcript = transcript_list.find_manually_created_transcript(["en", "en-US", "en-GB"])
            source = "manual"
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(["en", "en-US", "en-GB"])
                source = "auto-generated"
            except Exception:
                # Last resort: first available transcript in any language
                for t in transcript_list:
                    transcript = t
                    source = "manual" if not t.is_generated else "auto-generated"
                    break

        if transcript is None:
            return "", "none"

        fetched = transcript.fetch()
        # v1.x returns FetchedTranscript (iterable of snippets); older returns list of dicts
        parts = []
        for snippet in fetched:
            text = snippet.text if hasattr(snippet, "text") else snippet.get("text", "")
            if text:
                parts.append(text.replace("\n", " ").strip())
        return " ".join(parts), source
    except Exception as e:
        log.warning("Transcript unavailable for %s: %s", video_id, e)
        return "", "none"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/video")
def video(req: VideoRequest):
    video_id = req.video_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{5,20}", video_id):
        raise HTTPException(status_code=400, detail="Invalid video_id")

    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        log.error("yt-dlp failed for %s: %s", video_id, e)
        raise HTTPException(status_code=502, detail=f"yt-dlp extraction failed: {e}")

    description = info.get("description") or ""
    transcript, transcript_source = get_transcript(video_id)

    return {
        "video_id": video_id,
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration_string": format_duration(info.get("duration")),
        "upload_date": format_upload_date(info.get("upload_date")),
        "description": description,
        "description_links": extract_links(description),
        "thumbnail_url": best_thumbnail(video_id),
        "transcript": transcript,
        "transcript_source": transcript_source,
    }
