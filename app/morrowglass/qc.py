from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

from .models import Scene


@dataclass(slots=True)
class QCResult:
    passed: bool
    score: float | None = None
    notes: list[str] = field(default_factory=list)


def technical_image_qc(
    image_path: str | Path,
    *,
    min_width: int = 768,
    min_height: int = 432,
) -> QCResult:
    image_path = Path(image_path)
    if not image_path.is_file():
        return QCResult(False, notes=["image file is missing"])
    try:
        with Image.open(image_path) as image:
            image.load()
            width, height = image.size
    except Exception as exc:
        return QCResult(False, notes=[f"image cannot be decoded: {type(exc).__name__}"])
    notes = [f"decoded image {width}x{height}"]
    if width < min_width or height < min_height:
        notes.append(
            f"image is below preferred minimum {min_width}x{min_height}"
        )
        return QCResult(False, notes=notes)
    return QCResult(True, notes=notes)


def _vision_settings() -> tuple[str, str, str]:
    base_url = os.getenv("MORROWGLASS_VISION_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("MORROWGLASS_VISION_MODEL", "").strip()
    api_key = os.getenv("MORROWGLASS_VISION_API_KEY", "").strip()
    return base_url, model, api_key


def _external_ai_enabled() -> bool:
    return os.getenv(
        "MORROWGLASS_ALLOW_PAID_PROVIDERS",
        "",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_local_endpoint(
    base_url: str,
) -> bool:
    try:
        host = (
            urlparse(base_url).hostname
            or ""
        ).lower()
    except Exception:
        return False
    return host in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def semantic_qc_available() -> bool:
    base_url, model, _ = _vision_settings()
    return bool(
        base_url
        and model
        and (
            _is_local_endpoint(
                base_url
            )
            or _external_ai_enabled()
        )
    )


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("vision QC did not return a JSON object")
    return parsed


def semantic_scene_qc(
    scene: Scene,
    image_path: str | Path,
    *,
    min_score: float = 75.0,
    timeout: int = 120,
) -> QCResult:
    base_url, model, api_key = _vision_settings()
    if not base_url or not model:
        return QCResult(
            True,
            score=None,
            notes=[
                "semantic QC skipped: no vision model configured"
            ],
        )
    if (
        not _is_local_endpoint(
            base_url
        )
        and not _external_ai_enabled()
    ):
        return QCResult(
            True,
            score=None,
            notes=[
                "semantic QC skipped: remote vision endpoints "
                "are blocked in FREE-ONLY mode"
            ],
        )

    image_path = Path(image_path)
    mime = mimetypes.guess_type(image_path.name)[0] or "image/png"
    data_uri = (
        f"data:{mime};base64,"
        + base64.b64encode(image_path.read_bytes()).decode("ascii")
    )
    constraints = "; ".join(scene.historical_constraints) or "none supplied"
    rubric = f"""Evaluate whether this image is suitable for this exact historical documentary scene.

NARRATION:
{scene.narration}

EXPECTED VISUAL:
{scene.visual_description}

HISTORICAL CONSTRAINTS:
{constraints}

Check:
1. semantic match to the narration and expected visible action/place/people
2. obvious anachronisms or modern objects
3. obvious anatomy/image-generation failures
4. whether the image is usable as a serious historical documentary visual

Return ONLY JSON:
{{"score": 0-100, "pass": true/false, "notes": ["short reason", "..."]}}

Use a strict score. A materially wrong subject, era, or action should score below {min_score:.0f}."""

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "temperature": 0,
            "max_tokens": 400,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": rubric},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        },
        timeout=timeout,
    )
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    try:
        score = float(parsed.get("score"))
    except (TypeError, ValueError):
        score = 0.0
    raw_notes = parsed.get("notes") or []
    if isinstance(raw_notes, str):
        raw_notes = [raw_notes]
    notes = [str(item) for item in raw_notes][:8]
    passed = bool(parsed.get("pass")) and score >= min_score
    return QCResult(passed=passed, score=score, notes=notes)


def evaluate_scene_image(
    scene: Scene,
    image_path: str | Path,
    *,
    semantic: bool = True,
    min_score: float = 75.0,
) -> QCResult:
    technical = technical_image_qc(image_path)
    if not technical.passed:
        return technical
    if not semantic:
        return QCResult(True, notes=technical.notes + ["semantic QC disabled"])
    semantic_result = semantic_scene_qc(scene, image_path, min_score=min_score)
    semantic_result.notes = technical.notes + semantic_result.notes
    return semantic_result
