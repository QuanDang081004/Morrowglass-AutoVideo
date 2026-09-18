from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass

import requests

from app.config import config
from app.services import material, subtitle
from app.utils import utils

from .comfyui import (
    ComfyUIClient,
    default_image_workflow,
    default_video_workflow,
)


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _check_kokoro_api(
    timeout: float = 3.0,
) -> Check:
    base_url = str(
        config.kokoro.get(
            "base_url",
            "http://127.0.0.1:8880/v1",
        )
    ).strip().rstrip("/")
    api_key = str(
        config.kokoro.get(
            "api_key",
            "",
        )
        or ""
    ).strip()
    headers = {}
    if api_key:
        headers[
            "Authorization"
        ] = f"Bearer {api_key}"

    try:
        response = requests.get(
            f"{base_url}/audio/voices",
            headers=headers,
            timeout=timeout,
        )
        if response.status_code < 400:
            return Check(
                "Kokoro API",
                True,
                f"reachable at {base_url}",
                required=False,
            )
        return Check(
            "Kokoro API",
            False,
            (
                f"{base_url}/audio/voices "
                f"returned HTTP "
                f"{response.status_code}"
            ),
            required=False,
        )
    except Exception as exc:
        return Check(
            "Kokoro API",
            False,
            (
                f"not reachable at "
                f"{base_url}: "
                f"{type(exc).__name__}"
            ),
            required=False,
        )


def _check_local_kokoro(
    kokoro_python: str | Path | None,
) -> Check:
    configured = str(
        kokoro_python
        or os.getenv(
            "MORROWGLASS_KOKORO_PYTHON",
            "",
        )
    ).strip()
    if not configured:
        return Check(
            "Kokoro local",
            False,
            (
                "optional; no external "
                "Kokoro Python configured"
            ),
            required=False,
        )

    python_path = Path(
        configured
    ).expanduser()
    if not python_path.is_file():
        return Check(
            "Kokoro local",
            False,
            (
                "configured Python "
                f"does not exist: "
                f"{python_path}"
            ),
            required=False,
        )

    try:
        result = subprocess.run(
            [
                str(python_path),
                "-c",
                (
                    "from kokoro import "
                    "KPipeline; "
                    "print('kokoro-ok')"
                ),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=20,
        )
    except Exception as exc:
        return Check(
            "Kokoro local",
            False,
            (
                f"could not run "
                f"{python_path}: "
                f"{type(exc).__name__}"
            ),
            required=False,
        )

    if result.returncode == 0:
        return Check(
            "Kokoro local",
            True,
            (
                "KPipeline import works "
                f"via {python_path}"
            ),
            required=False,
        )

    details = (
        result.stderr
        or result.stdout
        or ""
    ).strip()
    return Check(
        "Kokoro local",
        False,
        (
            "KPipeline import failed: "
            f"{details[-500:]}"
        ),
        required=False,
    )


def _check_comfyui(
    project_dir: str | Path | None = None,
) -> Check:
    image_workflow = (
        default_image_workflow(
            project_dir
        )
    )
    video_workflow = (
        default_video_workflow(
            project_dir
        )
    )
    configured = bool(
        (
            image_workflow
            and image_workflow.is_file()
        )
        or (
            video_workflow
            and video_workflow.is_file()
        )
        or os.getenv(
            "MORROWGLASS_COMFYUI_URL",
            "",
        ).strip()
    )
    if not configured:
        return Check(
            "ComfyUI",
            False,
            (
                "optional; no ComfyUI "
                "workflow configured"
            ),
            required=False,
        )

    client = ComfyUIClient()
    ready = client.ping()
    workflow_bits = []
    if (
        image_workflow
        and image_workflow.is_file()
    ):
        workflow_bits.append(
            "image workflow"
        )
    if (
        video_workflow
        and video_workflow.is_file()
    ):
        workflow_bits.append(
            "video workflow"
        )
    workflow_text = (
        ", ".join(workflow_bits)
        if workflow_bits
        else "no workflow file"
    )
    return Check(
        "ComfyUI",
        ready,
        (
            f"reachable at "
            f"{client.base_url}; "
            f"{workflow_text}"
            if ready
            else (
                f"not reachable at "
                f"{client.base_url}; "
                f"{workflow_text}"
            )
        ),
        required=False,
    )


def run_doctor(
    project_dir: str | Path | None = None,
    *,
    kokoro_python: str | Path | None = None,
) -> list[Check]:
    python_ok = (
        sys.version_info
        >= (3, 11)
    )
    ffmpeg_ok = bool(
        utils.check_ffmpeg_ready()
    )
    mpt_image_ready = bool(
        material.is_openai_image_enabled()
    )
    vision_ready = bool(
        os.getenv(
            "MORROWGLASS_VISION_BASE_URL",
            "",
        ).strip()
        and os.getenv(
            "MORROWGLASS_VISION_MODEL",
            "",
        ).strip()
    )

    checks = [
        Check(
            "Python",
            python_ok,
            sys.version.split()[0],
        ),
        Check(
            "FFmpeg",
            ffmpeg_ok,
            (
                str(
                    utils.get_ffmpeg_binary()
                )
                if ffmpeg_ok
                else "not available"
            ),
        ),
        Check(
            "Whisper",
            subtitle.WhisperModel
            is not None,
            (
                "faster-whisper "
                f"available; "
                f"model="
                f"{subtitle.model_size}"
                if (
                    subtitle.WhisperModel
                    is not None
                )
                else (
                    "faster-whisper "
                    "is not installed"
                )
            ),
        ),
        _check_kokoro_api(),
        _check_local_kokoro(
            kokoro_python
        ),
        _check_comfyui(
            project_dir
        ),
        Check(
            "MPT image",
            mpt_image_ready,
            (
                "OpenAI-compatible "
                "image backend configured"
                if mpt_image_ready
                else (
                    "optional; "
                    "ComfyUI/HYBRID "
                    "can be used instead"
                )
            ),
            required=False,
        ),
        Check(
            "Vision QC",
            vision_ready,
            (
                "semantic QC configured"
                if vision_ready
                else (
                    "optional; technical "
                    "image QC only"
                )
            ),
            required=False,
        ),
    ]
    return checks


def required_checks_pass(
    checks: list[Check],
) -> bool:
    return all(
        check.ok
        for check in checks
        if check.required
    )
