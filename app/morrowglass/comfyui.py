from __future__ import annotations

import copy
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


class ComfyUIError(RuntimeError):
    pass


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".gif"}


@dataclass(slots=True)
class ComfyUIOutput:
    filename: str
    subfolder: str = ""
    output_type: str = "output"

    @property
    def suffix(self) -> str:
        return Path(self.filename).suffix.lower()


def default_base_url() -> str:
    return os.getenv(
        "MORROWGLASS_COMFYUI_URL",
        "http://127.0.0.1:8188",
    ).strip().rstrip("/")


def default_image_workflow(
    project_dir: str | Path | None = None,
) -> Path | None:
    configured = os.getenv(
        "MORROWGLASS_COMFYUI_IMAGE_WORKFLOW",
        "",
    ).strip()
    if configured:
        return Path(configured).expanduser()
    if project_dir is not None:
        candidate = Path(project_dir) / "workflows" / "image.json"
        if candidate.is_file():
            return candidate
    return None


def default_video_workflow(
    project_dir: str | Path | None = None,
) -> Path | None:
    configured = os.getenv(
        "MORROWGLASS_COMFYUI_VIDEO_WORKFLOW",
        "",
    ).strip()
    if configured:
        return Path(configured).expanduser()
    if project_dir is not None:
        candidate = Path(project_dir) / "workflows" / "video.json"
        if candidate.is_file():
            return candidate
    return None


def load_api_workflow(path: str | Path) -> dict[str, Any]:
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"ComfyUI workflow not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("ComfyUI workflow must be a non-empty JSON object")

    if "nodes" in raw and isinstance(raw.get("nodes"), list):
        raise ValueError(
            "ComfyUI workflow is UI/save format. "
            "Export it with File -> Export Workflow (API)."
        )

    valid_nodes = 0
    for node in raw.values():
        if (
            isinstance(node, dict)
            and isinstance(node.get("class_type"), str)
            and isinstance(node.get("inputs"), dict)
        ):
            valid_nodes += 1

    if valid_nodes == 0:
        raise ValueError(
            "ComfyUI workflow does not look like API format"
        )
    return raw


def _replace_placeholders(
    value: Any,
    replacements: dict[str, Any],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _replace_placeholders(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _replace_placeholders(item, replacements)
            for item in value
        ]
    if not isinstance(value, str):
        return value

    if value in replacements:
        return replacements[value]

    replaced = value
    for marker, replacement in replacements.items():
        if marker in replaced:
            replaced = replaced.replace(marker, str(replacement))
    return replaced


def prepare_workflow(
    workflow: dict[str, Any],
    *,
    prompt: str,
    negative_prompt: str = "",
    seed: int = 1,
    width: int = 1920,
    height: int = 1080,
    input_image: str = "",
    output_prefix: str = "Morrowglass",
    motion_prompt: str = "",
) -> dict[str, Any]:
    replacements: dict[str, Any] = {
        "{{PROMPT}}": prompt,
        "{{NEGATIVE_PROMPT}}": negative_prompt,
        "{{SEED}}": int(seed),
        "{{WIDTH}}": int(width),
        "{{HEIGHT}}": int(height),
        "{{INPUT_IMAGE}}": input_image,
        "{{OUTPUT_PREFIX}}": output_prefix,
        "{{MOTION_PROMPT}}": motion_prompt or prompt,
    }
    return _replace_placeholders(
        copy.deepcopy(workflow),
        replacements,
    )


def _extract_outputs(history_entry: dict[str, Any]) -> list[ComfyUIOutput]:
    outputs: list[ComfyUIOutput] = []
    raw_outputs = history_entry.get("outputs") or {}
    if not isinstance(raw_outputs, dict):
        return outputs

    for node_output in raw_outputs.values():
        if not isinstance(node_output, dict):
            continue
        for key in ("images", "gifs", "videos", "audio"):
            items = node_output.get(key) or []
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = str(item.get("filename") or "").strip()
                if not filename:
                    continue
                outputs.append(
                    ComfyUIOutput(
                        filename=filename,
                        subfolder=str(
                            item.get("subfolder") or ""
                        ).strip(),
                        output_type=str(
                            item.get("type") or "output"
                        ).strip(),
                    )
                )
    return outputs


class ComfyUIClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        request_timeout: float = 30.0,
        poll_interval: float = 1.0,
    ):
        self.base_url = (
            base_url or default_base_url()
        ).strip().rstrip("/")
        self.request_timeout = float(request_timeout)
        self.poll_interval = float(poll_interval)
        self.client_id = str(uuid.uuid4())

    def ping(self) -> bool:
        for endpoint in ("/system_stats", "/queue"):
            try:
                response = requests.get(
                    f"{self.base_url}{endpoint}",
                    timeout=min(self.request_timeout, 5.0),
                )
                if response.status_code < 400:
                    return True
            except requests.RequestException:
                continue
        return False

    def queue_prompt(
        self,
        workflow: dict[str, Any],
    ) -> str:
        response = requests.post(
            f"{self.base_url}/prompt",
            json={
                "prompt": workflow,
                "client_id": self.client_id,
            },
            timeout=self.request_timeout,
        )
        if response.status_code >= 400:
            raise ComfyUIError(
                "ComfyUI rejected workflow: "
                f"HTTP {response.status_code} "
                f"{response.text[-1200:]}"
            )
        payload = response.json()
        prompt_id = str(payload.get("prompt_id") or "").strip()
        if not prompt_id:
            raise ComfyUIError(
                f"ComfyUI response missing prompt_id: {payload}"
            )
        node_errors = payload.get("node_errors") or {}
        if node_errors:
            raise ComfyUIError(
                f"ComfyUI workflow validation errors: {node_errors}"
            )
        return prompt_id

    def wait_for_history(
        self,
        prompt_id: str,
        *,
        timeout: float = 900.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + float(timeout)
        last_status: Any = None

        while time.monotonic() < deadline:
            try:
                response = requests.get(
                    f"{self.base_url}/history/{prompt_id}",
                    timeout=self.request_timeout,
                )
                if response.status_code >= 400:
                    raise ComfyUIError(
                        "ComfyUI history request failed: "
                        f"HTTP {response.status_code}"
                    )
                payload = response.json()
            except requests.RequestException as exc:
                raise ComfyUIError(
                    f"ComfyUI history request failed: {exc}"
                ) from exc

            if isinstance(payload, dict):
                entry = payload.get(prompt_id)
                if isinstance(entry, dict):
                    last_status = entry.get("status")
                    outputs = _extract_outputs(entry)
                    if outputs:
                        return entry

                    status = entry.get("status") or {}
                    if isinstance(status, dict):
                        status_str = str(
                            status.get("status_str") or ""
                        ).lower()
                        completed = bool(
                            status.get("completed")
                        )
                        if (
                            completed
                            or status_str
                            in {
                                "error",
                                "failed",
                                "cancelled",
                                "canceled",
                            }
                        ):
                            messages = status.get("messages") or []
                            raise ComfyUIError(
                                "ComfyUI completed without usable output. "
                                f"status={status_str!r}, messages={messages}"
                            )

            time.sleep(self.poll_interval)

        raise TimeoutError(
            "Timed out waiting for ComfyUI workflow "
            f"{prompt_id}; last_status={last_status!r}"
        )

    def upload_image(self, image_path: str | Path) -> str:
        image_path = Path(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(
                f"ComfyUI input image not found: {image_path}"
            )

        with image_path.open("rb") as handle:
            response = requests.post(
                f"{self.base_url}/upload/image",
                files={
                    "image": (
                        image_path.name,
                        handle,
                        "application/octet-stream",
                    )
                },
                data={
                    "type": "input",
                    "overwrite": "true",
                },
                timeout=max(self.request_timeout, 120.0),
            )
        if response.status_code >= 400:
            raise ComfyUIError(
                "ComfyUI image upload failed: "
                f"HTTP {response.status_code} "
                f"{response.text[-1200:]}"
            )

        payload = response.json()
        name = str(payload.get("name") or "").strip()
        subfolder = str(payload.get("subfolder") or "").strip()
        if not name:
            raise ComfyUIError(
                f"ComfyUI upload response missing name: {payload}"
            )
        return (
            f"{subfolder}/{name}"
            if subfolder
            else name
        )

    def download_output(
        self,
        output: ComfyUIOutput,
        target: str | Path,
    ) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)

        response = requests.get(
            f"{self.base_url}/view",
            params={
                "filename": output.filename,
                "subfolder": output.subfolder,
                "type": output.output_type,
            },
            timeout=max(self.request_timeout, 180.0),
        )
        if response.status_code >= 400:
            raise ComfyUIError(
                "ComfyUI output download failed: "
                f"HTTP {response.status_code}"
            )
        target.write_bytes(response.content)
        if not target.is_file() or target.stat().st_size == 0:
            raise ComfyUIError(
                f"ComfyUI output is empty: {target}"
            )
        return target

    def run(
        self,
        workflow: dict[str, Any],
        *,
        target_dir: str | Path,
        preferred_kind: str = "image",
        timeout: float = 900.0,
        prefix: str = "comfyui",
    ) -> Path:
        prompt_id = self.queue_prompt(workflow)
        history = self.wait_for_history(
            prompt_id,
            timeout=timeout,
        )
        outputs = _extract_outputs(history)
        if not outputs:
            raise ComfyUIError(
                "ComfyUI workflow produced no downloadable output"
            )

        if preferred_kind == "video":
            preferred = [
                item
                for item in outputs
                if item.suffix in VIDEO_SUFFIXES
            ]
        else:
            preferred = [
                item
                for item in outputs
                if item.suffix in IMAGE_SUFFIXES
            ]
        selected = preferred[0] if preferred else outputs[0]

        suffix = selected.suffix or (
            ".mp4" if preferred_kind == "video" else ".png"
        )
        target = (
            Path(target_dir)
            / f"{prefix}_{prompt_id[:8]}{suffix}"
        )
        return self.download_output(selected, target)
