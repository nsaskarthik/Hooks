"""Shared transcript reader.

Both the Stop hook (TDD validation of the final response) and the SubagentStop
hook (optional one-line summary) need the most recent assistant message from a
``.jsonl`` transcript. Keeping the parser here means one tested implementation.
"""

import json
from pathlib import Path


def last_assistant_text(transcript_path: str) -> str:
    """Return the text of the most recent assistant message in the transcript.

    Returns "" when the path is missing/unreadable or holds no assistant text.
    Never raises.
    """
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
                if entry.get("type") != "assistant":
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
