"""YouTube Data API upload with scheduling, synthetic-media disclosure and custom thumbnail."""
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from channels import Channel
from config import YT_CLIENT_ID, YT_CLIENT_SECRET
from utils import log

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def service(ch: Channel):
    if not ch.refresh_token:
        raise RuntimeError(f"Missing YT_REFRESH_TOKEN_{ch.key}. Run get_youtube_token.py for this channel.")
    creds = Credentials(
        token=None, refresh_token=ch.refresh_token, token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET, scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _trim_tags(tags: list[str], limit: int = 480) -> list[str]:
    out, total = [], 0
    for t in tags:
        t = t.replace("<", "").replace(">", "").strip()
        cost = len(t) + (2 if " " in t else 0) + 1
        if not t or total + cost > limit:
            continue
        out.append(t)
        total += cost
    return out


def upload(ch: Channel, path: str, title: str, description: str, tags: list[str],
           publish_at: datetime | None, thumbnail: str | None = None) -> str:
    yt = service(ch)
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    if publish_at:
        status["publishAt"] = publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "snippet": {
            "title": title[:100], "description": description[:4900], "tags": _trim_tags(tags),
            "categoryId": ch.category_id, "defaultLanguage": "en", "defaultAudioLanguage": "en",
        },
        "status": status,
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk(num_retries=3)
    video_id = response["id"]
    if thumbnail:
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail, mimetype="image/jpeg")).execute()
        except HttpError as e:
            # Custom thumbnails need a phone-verified channel.
            log.warning("Thumbnail upload failed for %s: %s", video_id, e)
    return video_id
