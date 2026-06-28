"""Shared transcript reader.

Hooks that need the most recent assistant or user message from a ``.jsonl``
transcript use these helpers, so there's one tested parser. Never raises.
"""

import json
from pathlib import Path


def _last_text(transcript_path: str, role: str) -> str:
    """Return the text of the most recent ``role`` message in the transcript."""
    if not transcript_path or not Path(transcript_path).exists():
        return ""
    last = ""
    try:
        with open(transcript_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") != role:
                    continue
                content = entry.get("message", {}).get("content", entry.get("content", ""))
                if isinstance(content, str):
                    last = content or last
                elif isinstance(content, list):
                    texts = [b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text"]
                    if any(texts):
                        last = "\n".join(t for t in texts if t)
    except OSError:
        return last
    return last


def last_assistant_text(transcript_path: str) -> str:
    """Return the text of the most recent assistant message ("" if none). Never raises."""
    return _last_text(transcript_path, "assistant")


def last_user_text(transcript_path: str) -> str:
    """Return the text of the most recent user message ("" if none). Never raises."""
    return _last_text(transcript_path, "user")
