from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Callable

from .models import AssetType, MorrowglassProject, Scene, VisualBible

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


def _extract_json(text: str):
    text = (text or "").strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()

    positions = [p for p in (text.find("["), text.find("{")) if p >= 0]
    first_obj = min(positions, default=0)
    text = text[first_obj:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for open_char, close_char in (("[", "]"), ("{", "}")):
            start = text.find(open_char)
            end = text.rfind(close_char)
            if 0 <= start < end:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
        raise


def split_script(script: str, target_words: int = 24) -> list[str]:
    normalized = re.sub(r"\s+", " ", script or "").strip()
    if not normalized:
        return []

    sentences = _SENTENCE_BOUNDARY.split(normalized)
    scenes: list[str] = []
    buf: list[str] = []
    words = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        count = len(sentence.split())
        if buf and words + count > max(target_words * 1.45, target_words + 10):
            scenes.append(" ".join(buf))
            buf = []
            words = 0

        buf.append(sentence)
        words += count
        if words >= target_words:
            scenes.append(" ".join(buf))
            buf = []
            words = 0

    if buf:
        scenes.append(" ".join(buf))
    return scenes


_SEARCH_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but",
    "by", "for", "from", "had", "has", "have", "he", "her",
    "his", "in", "into", "is", "it", "its", "of", "on", "or",
    "she", "that", "the", "their", "them", "they", "this", "to",
    "was", "were", "with", "would", "according", "story", "said",
    "và", "là", "của", "có", "đã", "được", "trong", "một", "những",
    "người", "này", "đó", "với", "cho", "từ", "khi", "theo", "rằng",
}


def _fallback_search_query(
    narration: str,
    bible: VisualBible,
) -> str:
    tokens = re.findall(
        r"[^\W_][\w'-]*",
        narration or "",
        flags=re.UNICODE,
    )
    content: list[str] = []
    for token in tokens:
        lower = token.lower()
        if (
            lower in _SEARCH_STOPWORDS
            or len(lower) < 3
        ):
            continue
        if lower not in {
            value.lower()
            for value in content
        }:
            content.append(token)
        if len(content) >= 7:
            break

    prefix = [
        value
        for value in (
            bible.location.strip(),
            bible.period.strip(),
        )
        if value
    ]
    return " ".join(prefix + content).strip()


def _fallback_visual_description(
    narration: str,
    bible: VisualBible,
) -> str:
    visible = re.sub(
        r"^(according to (the )?story,?\s*|"
        r"it was said that\s*|"
        r"legend says that\s*)",
        "",
        narration.strip(),
        flags=re.IGNORECASE,
    )
    context = ", ".join(
        value
        for value in (
            bible.period.strip(),
            bible.location.strip(),
        )
        if value
    )
    if context:
        return (
            f"Literal historical documentary reconstruction in {context}: "
            f"{visible}"
        )
    return (
        "Literal historical documentary reconstruction showing: "
        f"{visible}"
    )


def _prompt_for_scene(
    narration: str,
    bible: VisualBible,
    scene_visual: str = "",
) -> str:
    constraints = "; ".join(bible.historical_constraints)
    chars = "; ".join(
        f"{name}: {desc}" for name, desc in bible.characters.items()
    )
    visual = scene_visual or narration
    parts = [
        visual,
        bible.style,
        f"historical period: {bible.period}" if bible.period else "",
        f"location: {bible.location}" if bible.location else "",
        f"character continuity: {chars}" if chars else "",
        f"historical constraints: {constraints}" if constraints else "",
        f"avoid: {bible.negative_prompt}" if bible.negative_prompt else "",
    ]
    return ", ".join(part for part in parts if part)


class SceneDirector:
    def __init__(self, llm_call: Callable[[str], str] | None = None):
        self.llm_call = llm_call

    def plan(
        self,
        script: str,
        *,
        title: str = "Morrowglass Video",
        bible: VisualBible | None = None,
        target_scene_seconds: float = 6.0,
        words_per_second: float = 2.45,
        use_llm: bool = True,
    ) -> MorrowglassProject:
        bible = bible or VisualBible()
        scenes = None

        if use_llm and self.llm_call:
            try:
                scenes = self._plan_with_llm(
                    script,
                    bible,
                    target_scene_seconds,
                )
            except Exception:
                scenes = None

        if not scenes:
            target_words = max(
                10,
                round(target_scene_seconds * words_per_second),
            )
            chunks = split_script(script, target_words=target_words)
            scenes = []
            for index, chunk in enumerate(chunks, 1):
                visual = _fallback_visual_description(
                    chunk,
                    bible,
                )
                search_query = _fallback_search_query(
                    chunk,
                    bible,
                )
                scenes.append(
                    Scene(
                        scene_id=f"scene_{index:03d}",
                        narration=chunk,
                        visual_description=visual,
                        image_prompt=_prompt_for_scene(
                            chunk,
                            bible,
                            visual,
                        ),
                        search_query=search_query,
                        motion_prompt=(
                            "subtle cinematic camera movement, "
                            "natural human motion, no morphing"
                        ),
                        asset_type=AssetType.IMAGE,
                        historical_constraints=list(
                            bible.historical_constraints
                        ),
                    )
                )

        return MorrowglassProject(
            title=title,
            script=script.strip(),
            scenes=scenes,
            visual_bible=bible,
        )

    def _plan_with_llm(
        self,
        script: str,
        bible: VisualBible,
        target_scene_seconds: float,
    ) -> list[Scene]:
        prompt = f"""You are the scene director for a serious historical YouTube documentary.
Turn the narration into chronological visual scenes. Every narration word must remain in order and be assigned exactly once. Do not rewrite facts.

TARGET: roughly {target_scene_seconds:.1f} seconds per scene. Shorter scenes are allowed when the visual meaning changes.
STYLE BIBLE:
{json.dumps(asdict(bible), ensure_ascii=False)}

Return ONLY a JSON array. Each object must contain:
- narration: exact contiguous excerpt from the supplied script
- visual_description: concrete visible action/place/people matching that narration
- image_prompt: detailed photorealistic generation prompt consistent with the style bible and its requested composition/aspect
- search_query: short concrete 3-8 word query for archive/stock search; visible nouns/actions only
- motion_prompt: short image-to-video motion prompt, no new story facts
- asset_type: one of image, image_to_video, video, stock, manual
- historical_constraints: string array

Prefer image for exposition and image_to_video/video only for scenes where motion materially helps. Avoid generic symbolic visuals if a literal historical visual is possible.

SCRIPT:
{script.strip()}""".strip()

        raw = self.llm_call(prompt)
        payload = _extract_json(raw)
        if isinstance(payload, dict):
            payload = payload.get("scenes")
        if not isinstance(payload, list) or not payload:
            raise ValueError("scene director did not return a scene array")

        scenes: list[Scene] = []
        concatenated = ""

        for index, item in enumerate(payload, 1):
            if not isinstance(item, dict):
                raise ValueError("invalid scene entry")

            narration = str(item.get("narration") or "").strip()
            visual = str(item.get("visual_description") or "").strip()
            if not narration or not visual:
                raise ValueError(
                    "scene requires narration and visual_description"
                )

            try:
                asset_type = AssetType(
                    str(item.get("asset_type") or "image")
                )
            except ValueError:
                asset_type = AssetType.IMAGE

            prompt_text = (
                str(item.get("image_prompt") or "").strip()
                or _prompt_for_scene(narration, bible, visual)
            )
            constraints = (
                item.get("historical_constraints")
                or bible.historical_constraints
            )
            if not isinstance(constraints, list):
                constraints = [str(constraints)]

            scenes.append(
                Scene(
                    scene_id=f"scene_{index:03d}",
                    narration=narration,
                    visual_description=visual,
                    image_prompt=prompt_text,
                    search_query=(
                        str(
                            item.get("search_query")
                            or ""
                        ).strip()
                        or _fallback_search_query(
                            narration,
                            bible,
                        )
                    ),
                    motion_prompt=str(
                        item.get("motion_prompt") or ""
                    ).strip(),
                    asset_type=asset_type,
                    historical_constraints=[
                        str(value) for value in constraints
                    ],
                )
            )
            if concatenated:
                concatenated += " "
            concatenated += narration

        def norm(value: str) -> str:
            return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

        src_tokens = norm(script).split()
        out_tokens = norm(concatenated).split()
        if src_tokens:
            overlap = (
                sum(
                    1
                    for source, output in zip(src_tokens, out_tokens)
                    if source == output
                )
                / len(src_tokens)
            )
            length_ratio = len(out_tokens) / len(src_tokens)
            if not (
                0.92 <= length_ratio <= 1.08
                and overlap >= 0.80
            ):
                raise ValueError(
                    "scene narration diverged from source script"
                )

        return scenes
