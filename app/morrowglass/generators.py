from __future__ import annotations

import math
import shutil
from pathlib import Path

from app.models.schema import VideoAspect
from app.services import material

from .models import MorrowglassProject
from .qc import evaluate_scene_image


class ImageGenerationUnavailable(RuntimeError):
    pass


def mpt_openai_image_ready() -> bool:
    return bool(material.is_openai_image_enabled())


def generate_missing_scene_images(
    project: MorrowglassProject,
    project_dir: str | Path,
    *,
    overwrite: bool = False,
    semantic_qc: bool = True,
    min_qc_score: float = 75.0,
    max_attempts: int = 2,
) -> list[str]:
    """Generate scene images and optionally reject/regenerate bad candidates."""
    if not mpt_openai_image_ready():
        raise ImageGenerationUnavailable(
            "OpenAI-compatible image generation is not configured. "
            "Set openai_image_base_url and openai_image_model in config.toml, "
            "or keep HYBRID mode and create the prompt-pack images manually."
        )
    max_attempts = max(1, int(max_attempts))
    project_dir = Path(project_dir)
    images_dir = project_dir / "images"
    rejected_dir = project_dir / "cache" / "rejected_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for scene in project.scenes:
        existing = Path(scene.asset_path) if scene.asset_path else None
        if existing and existing.is_file() and not overwrite:
            continue

        target = images_dir / f"{scene.scene_id}.png"
        if target.is_file() and not overwrite:
            scene.asset_path = str(target.resolve())
            continue

        accepted = False
        scene.qc_notes = []
        for attempt in range(1, max_attempts + 1):
            duration = scene.duration if scene.duration is not None else 5.0
            results = material.generate_images_openai(
                search_term=scene.image_prompt,
                minimum_duration=max(1, int(math.ceil(duration))),
                video_aspect=VideoAspect.landscape,
                save_dir=str(images_dir),
            )
            if not results:
                scene.qc_notes.append(f"attempt {attempt}: provider returned no image")
                continue

            source = Path(results[0].url)
            if not source.is_file():
                scene.qc_notes.append(f"attempt {attempt}: provider returned missing file")
                continue

            qc = evaluate_scene_image(
                scene,
                source,
                semantic=semantic_qc,
                min_score=min_qc_score,
            )
            scene.qc_score = qc.score
            scene.qc_notes.extend(f"attempt {attempt}: {note}" for note in qc.notes)
            if qc.passed:
                if target.exists():
                    target.unlink()
                if source.resolve() != target.resolve():
                    shutil.move(str(source), str(target))
                scene.asset_path = str(target.resolve())
                accepted = True
                break

            rejected = rejected_dir / f"{scene.scene_id}_attempt_{attempt}.png"
            if rejected.exists():
                rejected.unlink()
            if source.resolve() != rejected.resolve():
                shutil.move(str(source), str(rejected))

        if not accepted:
            failures.append(scene.scene_id)

    project.metadata["image_provider"] = "mpt_openai"
    project.metadata["image_generation_failures"] = failures
    project.metadata["semantic_qc_requested"] = bool(semantic_qc)
    project.save(project_dir / "project.json")
    return failures
