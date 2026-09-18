from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re

from .models import Scene


@dataclass(slots=True)
class Cue:
    start: float
    end: float
    text: str


def _ts(value: str) -> float:
    h, m, rest = value.replace(".", ",").split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path: str | Path) -> list[Cue]:
    text = Path(path).read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues: list[Cue] = []

    for block in blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]
        if len(lines) < 2:
            continue

        time_i = 1 if "-->" not in lines[0] else 0
        if time_i >= len(lines) or "-->" not in lines[time_i]:
            continue

        left, right = [
            value.strip()
            for value in lines[time_i].split("-->", 1)
        ]
        cues.append(
            Cue(
                _ts(left),
                _ts(right),
                " ".join(lines[time_i + 1 :]),
            )
        )

    return cues


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def assign_by_duration(
    scenes: list[Scene],
    audio_duration: float,
) -> list[Scene]:
    weights = [
        max(1, len(_tokens(scene.narration)))
        for scene in scenes
    ]
    total = sum(weights) or 1
    cursor = 0.0

    for scene, weight in zip(scenes, weights):
        scene.start = cursor
        cursor += audio_duration * weight / total
        scene.end = cursor

    if scenes:
        scenes[-1].end = audio_duration
    return scenes


def _flatten_cue_tokens(
    cues: list[Cue],
) -> tuple[list[str], list[int]]:
    words: list[str] = []
    word_to_cue: list[int] = []
    for cue_index, cue in enumerate(cues):
        cue_words = _tokens(cue.text)
        for word in cue_words:
            words.append(word)
            word_to_cue.append(cue_index)
    return words, word_to_cue


def _alignment_map(
    script_tokens: list[str],
    whisper_tokens: list[str],
) -> dict[int, int]:
    matcher = SequenceMatcher(
        None,
        script_tokens,
        whisper_tokens,
        autojunk=False,
    )
    mapping: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[
                block.a + offset
            ] = block.b + offset
    return mapping


def _estimate_word_index(
    script_index: int,
    *,
    script_length: int,
    whisper_length: int,
    mapping: dict[int, int],
) -> int:
    if whisper_length <= 0:
        raise ValueError("whisper token list is empty")

    exact = mapping.get(script_index)
    if exact is not None:
        return exact

    previous = [
        (source, target)
        for source, target in mapping.items()
        if source < script_index
    ]
    following = [
        (source, target)
        for source, target in mapping.items()
        if source > script_index
    ]

    prev_anchor = max(
        previous,
        default=None,
        key=lambda item: item[0],
    )
    next_anchor = min(
        following,
        default=None,
        key=lambda item: item[0],
    )

    if prev_anchor and next_anchor:
        src_span = (
            next_anchor[0] - prev_anchor[0]
        )
        dst_span = (
            next_anchor[1] - prev_anchor[1]
        )
        ratio = (
            (script_index - prev_anchor[0])
            / src_span
        )
        estimate = round(
            prev_anchor[1]
            + ratio * dst_span
        )
    elif prev_anchor:
        estimate = (
            prev_anchor[1]
            + script_index
            - prev_anchor[0]
        )
    elif next_anchor:
        estimate = (
            next_anchor[1]
            - (
                next_anchor[0]
                - script_index
            )
        )
    else:
        ratio = (
            script_index
            / max(1, script_length - 1)
        )
        estimate = round(
            ratio
            * max(0, whisper_length - 1)
        )

    return max(
        0,
        min(
            whisper_length - 1,
            int(estimate),
        ),
    )


def _aligned_scene_boundaries(
    scenes: list[Scene],
    cues: list[Cue],
) -> list[float] | None:
    scene_tokens = [
        _tokens(scene.narration)
        for scene in scenes
    ]
    script_tokens = [
        word
        for words in scene_tokens
        for word in words
    ]
    whisper_tokens, word_to_cue = (
        _flatten_cue_tokens(cues)
    )

    if (
        not script_tokens
        or not whisper_tokens
        or not word_to_cue
    ):
        return None

    mapping = _alignment_map(
        script_tokens,
        whisper_tokens,
    )

    # Require enough exact anchors to trust text alignment. Whisper is
    # normally very close to the supplied narration, but if it diverges
    # badly we fall back to duration weighting rather than invent timings.
    match_ratio = (
        len(mapping)
        / max(1, len(script_tokens))
    )
    if match_ratio < 0.55:
        return None

    boundaries: list[float] = []
    cumulative = 0

    for scene_index in range(
        len(scenes) - 1
    ):
        cumulative += len(
            scene_tokens[scene_index]
        )
        last_script_index = max(
            0,
            cumulative - 1,
        )
        next_script_index = min(
            len(script_tokens) - 1,
            cumulative,
        )

        last_word_index = (
            _estimate_word_index(
                last_script_index,
                script_length=len(
                    script_tokens
                ),
                whisper_length=len(
                    whisper_tokens
                ),
                mapping=mapping,
            )
        )
        next_word_index = (
            _estimate_word_index(
                next_script_index,
                script_length=len(
                    script_tokens
                ),
                whisper_length=len(
                    whisper_tokens
                ),
                mapping=mapping,
            )
        )

        if next_word_index <= last_word_index:
            next_word_index = min(
                len(whisper_tokens) - 1,
                last_word_index + 1,
            )

        last_cue = cues[
            word_to_cue[last_word_index]
        ]
        next_cue = cues[
            word_to_cue[next_word_index]
        ]

        # Keep the current visual through its final spoken word. If there
        # is a pause before the next scene starts, cut halfway through the
        # pause so neither visual intrudes on the other's narration.
        boundary = max(
            last_cue.end,
            (
                last_cue.end
                + next_cue.start
            )
            / 2,
        )
        boundaries.append(boundary)

    return boundaries


def assign_from_srt(
    scenes: list[Scene],
    cues: list[Cue],
    audio_duration: float | None = None,
) -> list[Scene]:
    if not scenes:
        return scenes

    if not cues:
        if audio_duration is None:
            raise ValueError(
                "audio_duration is required when subtitle cues are unavailable"
            )
        return assign_by_duration(
            scenes,
            float(audio_duration),
        )

    boundaries = _aligned_scene_boundaries(
        scenes,
        cues,
    )
    if boundaries is None:
        if audio_duration is None:
            audio_duration = cues[-1].end
        return assign_by_duration(
            scenes,
            float(audio_duration),
        )

    cursor = 0.0
    for scene_index, scene in enumerate(
        scenes
    ):
        scene.start = cursor
        if scene_index < len(boundaries):
            scene.end = max(
                cursor,
                boundaries[scene_index],
            )
            cursor = scene.end
        else:
            final_end = (
                float(audio_duration)
                if (
                    audio_duration is not None
                    and audio_duration > 0
                )
                else cues[-1].end
            )
            scene.end = max(
                cursor,
                final_end,
            )

    return scenes
