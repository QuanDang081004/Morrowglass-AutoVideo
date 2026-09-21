from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Callable

from .models import VisualBible

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def _parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("visual bible response must be a JSON object")
    return parsed


def enrich_visual_bible(
    script: str,
    bible: VisualBible,
    *,
    llm_call: Callable[[str], str] | None,
) -> VisualBible:
    """Fill missing continuity fields from the script without overriding user input."""
    if not llm_call or not script.strip():
        return bible

    prompt = f"""You are preparing a visual continuity bible for a serious historical documentary.

Read ONLY the supplied narration. Extract visual facts and continuity constraints that are explicitly stated or safely implied by the narration. Do not invent historical facts, dates, locations, identities, ethnicities, weapons, architecture, clothing, or appearances that the narration does not support.

Return ONLY JSON with this shape:
{{
  "period": "short period/era or empty string",
  "location": "short location/region or empty string",
  "characters": {{
    "stable character key": "consistent visual continuity description"
  }},
  "historical_constraints": [
    "concrete visual constraint"
  ]
}}

Rules:
- If the script does not establish a period or location, return an empty string for that field.
- For recurring people, describe only continuity-relevant visible traits that can be kept stable across scenes. If exact appearance is unknown, use a neutral design such as age range/role/clothing category supported by the script rather than pretending it is historically documented.
- Constraints should prevent obvious anachronisms and contradictions with the narration.
- Do not rewrite or summarize the narration.
- Do not include style instructions; style is managed separately.

EXISTING BIBLE (user-supplied values must not be contradicted):
{json.dumps(asdict(bible), ensure_ascii=False)}

NARRATION:
{script.strip()}""".strip()

    try:
        raw = llm_call(prompt)
        payload = _parse_json_object(raw)
    except Exception:
        return bible

    period = str(payload.get("period") or "").strip()
    location = str(payload.get("location") or "").strip()

    raw_characters = payload.get("characters") or {}
    generated_characters: dict[str, str] = {}
    if isinstance(raw_characters, dict):
        for key, value in raw_characters.items():
            key_text = str(key).strip()
            value_text = str(value).strip()
            if key_text and value_text:
                generated_characters[key_text] = value_text

    raw_constraints = payload.get("historical_constraints") or []
    if isinstance(raw_constraints, str):
        raw_constraints = [raw_constraints]
    generated_constraints = [
        str(item).strip()
        for item in raw_constraints
        if str(item).strip()
    ]

    merged_characters = dict(generated_characters)
    merged_characters.update(bible.characters)

    merged_constraints: list[str] = []
    for item in (
        list(bible.historical_constraints)
        + generated_constraints
    ):
        if item not in merged_constraints:
            merged_constraints.append(item)

    return VisualBible(
        style=bible.style,
        period=bible.period or period,
        location=bible.location or location,
        characters=merged_characters,
        historical_constraints=merged_constraints,
        negative_prompt=bible.negative_prompt,
    )
