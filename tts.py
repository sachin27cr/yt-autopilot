"""ElevenLabs text-to-speech, one MP3 per scene."""
import time
from pathlib import Path

import requests

from config import ELEVENLABS_API_KEY, ELEVENLABS_MODEL

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synth(text: str, voice_id: str, out_path: Path) -> Path:
    if not voice_id:
        raise RuntimeError("Missing voice id for this channel (set VOICE_ID_A / VOICE_ID_B).")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15, "use_speaker_boost": True},
    }
    headers = {"xi-api-key": ELEVENLABS_API_KEY or "", "Content-Type": "application/json", "Accept": "audio/mpeg"}
    for attempt in range(4):
        r = requests.post(
            API.format(voice_id=voice_id), params={"output_format": "mp3_44100_128"},
            json=payload, headers=headers, timeout=180,
        )
        if r.ok:
            out_path.write_bytes(r.content)
            return out_path
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 3:
            time.sleep(5 * (attempt + 1))
            continue
        raise RuntimeError(f"ElevenLabs error {r.status_code}: {r.text[:300]}")
    return out_path
