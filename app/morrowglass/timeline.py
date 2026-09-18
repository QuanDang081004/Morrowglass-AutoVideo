from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
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
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2: continue
        time_i = 1 if "-->" not in lines[0] else 0
        if time_i >= len(lines) or "-->" not in lines[time_i]: continue
        left, right = [x.strip() for x in lines[time_i].split("-->", 1)]
        cues.append(Cue(_ts(left), _ts(right), " ".join(lines[time_i + 1 :])))
    return cues

def _tokens(text: str) -> list[str]: return re.findall(r"[a-z0-9']+", (text or "").lower())

def assign_by_duration(scenes: list[Scene], audio_duration: float) -> list[Scene]:
    weights = [max(1, len(_tokens(scene.narration))) for scene in scenes]
    total = sum(weights) or 1
    cursor = 0.0
    for scene, weight in zip(scenes, weights):
        scene.start = cursor
        cursor += audio_duration * weight / total
        scene.end = cursor
    if scenes: scenes[-1].end = audio_duration
    return scenes

def _make_contiguous(scenes: list[Scene], audio_duration: float | None) -> None:
    if not scenes:
        return
    scenes[0].start = 0.0
    for i in range(len(scenes) - 1):
        left = scenes[i]
        right = scenes[i + 1]
        left_end = float(left.end or 0)
        right_start = float(right.start or left_end)
        boundary = max(float(left.start or 0), (left_end + right_start) / 2)
        left.end = boundary
        right.start = boundary
    if audio_duration is not None and audio_duration > 0:
        scenes[-1].end = float(audio_duration)

def assign_from_srt(scenes: list[Scene], cues: list[Cue], audio_duration: float | None = None) -> list[Scene]:
    if not scenes: return scenes
    if not cues or len(cues) < len(scenes):
        if audio_duration is None:
            if cues:
                audio_duration = cues[-1].end
            else:
                raise ValueError("audio_duration is required when subtitle cues are unavailable")
        return assign_by_duration(scenes, float(audio_duration))

    cue_counts = [max(1, len(_tokens(c.text))) for c in cues]
    scene_counts = [max(1, len(_tokens(s.narration))) for s in scenes]
    cue_i = 0
    for scene_i, scene in enumerate(scenes):
        if cue_i >= len(cues):
            if audio_duration is None:
                audio_duration = cues[-1].end
            return assign_by_duration(scenes, float(audio_duration))
        start_i = cue_i
        target = scene_counts[scene_i]
        consumed = 0
        remaining_scenes = len(scenes) - scene_i - 1
        max_end_exclusive = max(start_i + 1, len(cues) - remaining_scenes)
        while cue_i < max_end_exclusive:
            consumed += cue_counts[cue_i]; cue_i += 1
            if consumed >= target * 0.86: break
        scene.start = cues[start_i].start
        scene.end = cues[cue_i - 1].end
    if cue_i < len(cues): scenes[-1].end = cues[-1].end
    _make_contiguous(scenes, audio_duration)
    return scenes
