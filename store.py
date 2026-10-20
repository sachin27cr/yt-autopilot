"""Tiny JSON state store (jobs, ideas, history, booked publish slots). Lives on the Railway volume."""
import json
import threading
import uuid
from datetime import datetime, timezone

from config import WORK_DIR

PATH = WORK_DIR / "state.json"
_LOCK = threading.RLock()
_DEFAULT = {"jobs": {}, "ideas": {}, "history": {}, "taken_slots": [], "awaiting": None, "last_hook": {}}


def _load() -> dict:
    if PATH.exists():
        data = json.loads(PATH.read_text())
        for k, v in _DEFAULT.items():
            data.setdefault(k, json.loads(json.dumps(v)))
        return data
    return json.loads(json.dumps(_DEFAULT))


def _save(data: dict) -> None:
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(PATH)


def read() -> dict:
    with _LOCK:
        return _load()


def update(fn):
    """Apply fn(state) atomically and return its result."""
    with _LOCK:
        data = _load()
        result = fn(data)
        _save(data)
        return result


def new_id() -> str:
    return datetime.now(timezone.utc).strftime("%m%d") + uuid.uuid4().hex[:5]


def set_ideas(ch: str, ideas: list) -> None:
    update(lambda s: s["ideas"].__setitem__(ch, ideas))


def get_ideas(ch: str) -> list:
    return read()["ideas"].get(ch, [])


def set_awaiting(value) -> None:
    update(lambda s: s.__setitem__("awaiting", value))


def get_awaiting():
    return read()["awaiting"]


def recent_titles(ch: str) -> list:
    return read()["history"].get(ch, [])[-50:]


def get_job(job_id: str) -> dict:
    job = read()["jobs"].get(job_id)
    if not job:
        raise KeyError(f"Unknown job {job_id}")
    return job


def save_job(job: dict) -> None:
    update(lambda s: s["jobs"].__setitem__(job["id"], job))
