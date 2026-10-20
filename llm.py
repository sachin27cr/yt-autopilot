"""Claude API helper that returns parsed JSON."""
import json
import re

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def parse_json(text: str):
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    start = min(starts) if starts else 0
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def ask_json(system: str, user: str, max_tokens: int = 12000):
    """Ask Claude for JSON. Retries once with a stricter reminder if parsing fails."""
    messages = [{"role": "user", "content": user}]
    for attempt in range(2):
        resp = client().messages.create(
            model=CLAUDE_MODEL, max_tokens=max_tokens, system=system, messages=messages,
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            return parse_json(text)
        except (json.JSONDecodeError, ValueError):
            if attempt == 1:
                raise
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": "That was not valid JSON. Reply again with ONLY the JSON, nothing else."},
            ]
