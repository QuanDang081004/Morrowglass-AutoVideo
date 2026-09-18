from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import requests

from app.config import config
from app.services import material, subtitle
from app.utils import utils


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _check_kokoro(timeout: float = 3.0) -> Check:
    base_url = str(
        config.kokoro.get("base_url", "http://127.0.0.1:8880/v1")
    ).strip().rstrip("/")
    api_key = str(config.kokoro.get("api_key", "") or "").strip()
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = requests.get(
            f"{base_url}/models",
            headers=headers,
            timeout=timeout,
        )
        if response.status_code < 400:
            return Check(
                "Kokoro",
                True,
                f"reachable at {base_url}",
            )
        return Check(
            "Kokoro",
            False,
            f"{base_url} returned HTTP {response.status_code}",
        )
    except Exception as exc:
        return Check(
            "Kokoro",
            False,
            f"not reachable at {base_url}: {type(exc).__name__}",
        )


def run_doctor() -> list[Check]:
    python_ok = sys.version_info >= (3, 11)
    checks = [
        Check(
            "Python",
            python_ok,
            sys.version.split()[0],
        ),
        Check(
            "FFmpeg",
            bool(utils.check_ffmpeg_ready()),
            (
                str(utils.get_ffmpeg_binary())
                if utils.check_ffmpeg_ready()
                else "not available"
            ),
        ),
        Check(
            "Whisper",
            subtitle.WhisperModel is not None,
            (
                f"faster-whisper available; model={subtitle.model_size}"
                if subtitle.WhisperModel is not None
                else "faster-whisper is not installed"
            ),
        ),
        _check_kokoro(),
        Check(
            "Auto image",
            bool(material.is_openai_image_enabled()),
            (
                "OpenAI-compatible image backend configured"
                if material.is_openai_image_enabled()
                else (
                    "not configured; HYBRID/manual prompts still work"
                )
            ),
            required=False,
        ),
        Check(
            "Vision QC",
            bool(
                os.getenv("MORROWGLASS_VISION_BASE_URL", "").strip()
                and os.getenv("MORROWGLASS_VISION_MODEL", "").strip()
            ),
            (
                "semantic QC configured"
                if (
                    os.getenv("MORROWGLASS_VISION_BASE_URL", "").strip()
                    and os.getenv("MORROWGLASS_VISION_MODEL", "").strip()
                )
                else "optional; technical image QC only"
            ),
            required=False,
        ),
    ]
    return checks


def required_checks_pass(checks: list[Check]) -> bool:
    return all(check.ok for check in checks if check.required)
