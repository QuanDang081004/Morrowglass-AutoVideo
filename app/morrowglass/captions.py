from __future__ import annotations

import re
from pathlib import Path

from .timeline import Cue, parse_srt


def _format_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    h, rem = divmod(milliseconds, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _join_words(parts: list[str]) -> str:
    text = " ".join(part.strip() for part in parts if part.strip())
    text = re.sub(r"\s+([,.;:!?%\)\]\}])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    return text.strip()


def group_word_cues(
    cues: list[Cue],
    *,
    max_words: int = 8,
    max_duration: float = 3.2,
) -> list[Cue]:
    """Turn word-level Whisper cues into readable caption chunks."""
    if max_words < 1:
        raise ValueError("max_words must be at least 1")
    if max_duration <= 0:
        raise ValueError("max_duration must be positive")

    groups: list[Cue] = []
    words: list[str] = []
    start: float | None = None
    end = 0.0

    def flush() -> None:
        nonlocal words, start, end
        if words and start is not None:
            groups.append(Cue(start=start, end=end, text=_join_words(words)))
        words = []
        start = None
        end = 0.0

    for cue in cues:
        token = cue.text.strip()
        if not token:
            continue
        if start is None:
            start = cue.start
        words.append(token)
        end = cue.end
        elapsed = end - start
        punctuation_break = bool(re.search(r"[.!?][\"')\]]*$", token))
        if len(words) >= max_words or elapsed >= max_duration or punctuation_break:
            flush()

    flush()
    return groups


def write_srt(cues: list[Cue], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for index, cue in enumerate(cues, 1):
        blocks.append(
            f"{index}\n{_format_timestamp(cue.start)} --> {_format_timestamp(cue.end)}\n{cue.text}"
        )
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    return path


def build_readable_captions(
    word_srt: str | Path,
    output_srt: str | Path,
    *,
    max_words: int = 8,
    max_duration: float = 3.2,
) -> Path:
    cues = parse_srt(word_srt)
    if not cues:
        raise ValueError("word-level subtitle file has no cues")
    return write_srt(
        group_word_cues(cues, max_words=max_words, max_duration=max_duration),
        output_srt,
    )
