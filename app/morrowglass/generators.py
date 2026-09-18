from __future__ import annotations

import os
import hashlib
import math
import shutil
from pathlib import Path

from app.models.schema import VideoAspect
from app.services import material

from .archive import (
    attribution_record,
    download_archive_image,
    rank_archive_assets,
    search_wikimedia_images,
    write_attribution_file,
)
from .comfyui import (
    ComfyUIClient,
    default_image_workflow,
    default_video_workflow,
    load_api_workflow,
    prepare_workflow,
    VIDEO_SUFFIXES,
)
from .models import AssetType, MorrowglassProject
from .qc import evaluate_scene_image


class ImageGenerationUnavailable(RuntimeError):
    pass


class VideoGenerationUnavailable(RuntimeError):
    pass


def paid_providers_enabled() -> bool:
    return os.getenv(
        "MORROWGLASS_ALLOW_PAID_PROVIDERS",
        "",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def mpt_openai_image_ready() -> bool:
    return bool(material.is_openai_image_enabled())


def _scene_seed(scene_id: str, attempt: int = 1) -> int:
    digest = hashlib.sha256(
        f"{scene_id}:{attempt}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def _resolve_image_provider(
    provider: str,
    project_dir: Path,
    comfyui_workflow: str | Path | None,
) -> tuple[str, Path | None]:
    provider = str(provider or "auto").strip().lower()
    if provider not in {
        "auto",
        "wikimedia",
        "mpt_openai",
        "comfyui",
    }:
        raise ValueError(
            "image provider must be one of: "
            "auto, wikimedia, mpt_openai, comfyui"
        )

    workflow_path = (
        Path(comfyui_workflow).expanduser()
        if comfyui_workflow
        else default_image_workflow(project_dir)
    )

    if provider == "comfyui":
        if not workflow_path or not workflow_path.is_file():
            raise ImageGenerationUnavailable(
                "ComfyUI image provider selected but no API workflow "
                "was found. Put it at workflows/image.json or pass "
                "a workflow path."
            )
        return "comfyui", workflow_path

    if provider == "wikimedia":
        return "wikimedia", None

    if provider == "mpt_openai":
        if not paid_providers_enabled():
            raise ImageGenerationUnavailable(
                "Paid image providers are disabled in FREE-ONLY mode. "
                "Morrowglass will not call them unless "
                "MORROWGLASS_ALLOW_PAID_PROVIDERS=1 is set explicitly."
            )
        if not mpt_openai_image_ready():
            raise ImageGenerationUnavailable(
                "MoneyPrinterTurbo OpenAI-compatible image generation "
                "is not configured."
            )
        return "mpt_openai", None

    if workflow_path and workflow_path.is_file():
        return "comfyui", workflow_path

    # Zero-config, free-first fallback. Paid OpenAI-compatible image
    # generation is never selected implicitly; users must choose it
    # explicitly so AUTO cannot create surprise charges.
    return "wikimedia", None


def _generate_mpt_candidate(
    *,
    scene,
    images_dir: Path,
) -> Path | None:
    duration = (
        scene.duration
        if scene.duration is not None
        else 5.0
    )
    results = material.generate_images_openai(
        search_term=scene.image_prompt,
        minimum_duration=max(
            1,
            int(math.ceil(duration)),
        ),
        video_aspect=VideoAspect.landscape,
        save_dir=str(images_dir),
    )
    if not results:
        return None
    source = Path(results[0].url)
    return source if source.is_file() else None


def _generate_wikimedia_candidate(
    *,
    scene,
    candidate_dir: Path,
    attempt: int,
):
    query = (
        str(getattr(scene, "search_query", "") or "").strip()
        or scene.visual_description
        or scene.narration
    )
    assets = search_wikimedia_images(
        query,
        limit=max(12, attempt + 8),
        thumb_width=1920,
    )
    if not assets:
        return None, None

    assets = rank_archive_assets(
        assets,
        query=query,
        visual_description=(
            scene.visual_description
            or scene.narration
        ),
    )
    index = min(
        max(0, int(attempt) - 1),
        len(assets) - 1,
    )
    asset = assets[index]
    target = (
        candidate_dir
        / f"{scene.scene_id}_wikimedia_{attempt}.jpg"
    )
    downloaded = download_archive_image(
        asset,
        target,
    )
    return downloaded, asset


def _generate_comfyui_candidate(
    *,
    scene,
    project: MorrowglassProject,
    client: ComfyUIClient,
    workflow: dict,
    candidate_dir: Path,
    attempt: int,
) -> Path:
    width, height = project.resolution
    prepared = prepare_workflow(
        workflow,
        prompt=scene.image_prompt,
        negative_prompt=project.visual_bible.negative_prompt,
        seed=_scene_seed(scene.scene_id, attempt),
        width=width,
        height=height,
        output_prefix=f"Morrowglass_{scene.scene_id}_a{attempt}",
        motion_prompt=scene.motion_prompt,
    )
    return client.run(
        prepared,
        target_dir=candidate_dir,
        preferred_kind="image",
        timeout=1200.0,
        prefix=f"{scene.scene_id}_attempt_{attempt}",
    )


def _remove_scene_images(
    images_dir: Path,
    scene_id: str,
) -> None:
    for candidate in images_dir.glob(f"{scene_id}.*"):
        if candidate.is_file():
            candidate.unlink()


def generate_missing_scene_images(
    project: MorrowglassProject,
    project_dir: str | Path,
    *,
    overwrite: bool = False,
    semantic_qc: bool = True,
    min_qc_score: float = 75.0,
    max_attempts: int = 2,
    provider: str = "auto",
    comfyui_url: str | None = None,
    comfyui_workflow: str | Path | None = None,
) -> list[str]:
    """Generate scene images and reject/regenerate bad candidates."""
    max_attempts = max(1, int(max_attempts))
    project_dir = Path(project_dir)
    images_dir = project_dir / "images"
    rejected_dir = project_dir / "cache" / "rejected_images"
    candidate_dir = project_dir / "cache" / "generated_images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir.mkdir(parents=True, exist_ok=True)

    provider_name, workflow_path = _resolve_image_provider(
        provider,
        project_dir,
        comfyui_workflow,
    )
    comfy_client = None
    comfy_workflow_data = None
    if provider_name == "comfyui":
        comfy_client = ComfyUIClient(comfyui_url)
        if not comfy_client.ping():
            raise ImageGenerationUnavailable(
                f"ComfyUI is not reachable at {comfy_client.base_url}"
            )
        comfy_workflow_data = load_api_workflow(workflow_path)

    failures: list[str] = []
    asset_sources = dict(
        project.metadata.get("asset_sources")
        or {}
    )
    for scene in project.scenes:
        existing = (
            Path(scene.asset_path)
            if scene.asset_path
            else None
        )
        if (
            existing
            and existing.is_file()
            and not overwrite
        ):
            continue

        existing_images = [
            item
            for item in images_dir.glob(f"{scene.scene_id}.*")
            if item.is_file()
        ]
        if existing_images and not overwrite:
            scene.asset_path = str(existing_images[0].resolve())
            continue

        if overwrite:
            _remove_scene_images(images_dir, scene.scene_id)

        accepted = False
        scene.qc_notes = []
        for attempt in range(1, max_attempts + 1):
            archive_asset = None
            if provider_name == "comfyui":
                source = _generate_comfyui_candidate(
                    scene=scene,
                    project=project,
                    client=comfy_client,
                    workflow=comfy_workflow_data,
                    candidate_dir=candidate_dir,
                    attempt=attempt,
                )
            elif provider_name == "wikimedia":
                try:
                    (
                        source,
                        archive_asset,
                    ) = _generate_wikimedia_candidate(
                        scene=scene,
                        candidate_dir=candidate_dir,
                        attempt=attempt,
                    )
                except Exception as exc:
                    scene.qc_notes.append(
                        "archive search failed: "
                        f"{type(exc).__name__}: {exc}"
                    )
                    source = None
            else:
                source = _generate_mpt_candidate(
                    scene=scene,
                    images_dir=candidate_dir,
                )

            if not source or not source.is_file():
                scene.qc_notes.append(
                    f"attempt {attempt}: provider returned no image"
                )
                continue

            qc = evaluate_scene_image(
                scene,
                source,
                semantic=semantic_qc,
                min_score=min_qc_score,
            )
            scene.qc_score = qc.score
            scene.qc_notes.extend(
                f"attempt {attempt}: {note}"
                for note in qc.notes
            )

            suffix = source.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                suffix = ".png"
            target = images_dir / f"{scene.scene_id}{suffix}"

            if qc.passed:
                if target.exists():
                    target.unlink()
                if source.resolve() != target.resolve():
                    shutil.move(str(source), str(target))
                scene.asset_path = str(target.resolve())
                if archive_asset is not None:
                    asset_sources[
                        scene.scene_id
                    ] = attribution_record(
                        archive_asset
                    )
                accepted = True
                break

            rejected = (
                rejected_dir
                / f"{scene.scene_id}_attempt_{attempt}{suffix}"
            )
            if rejected.exists():
                rejected.unlink()
            if source.resolve() != rejected.resolve():
                shutil.move(str(source), str(rejected))

        if not accepted:
            failures.append(scene.scene_id)

    project.metadata["image_provider"] = provider_name
    project.metadata["asset_sources"] = asset_sources
    if asset_sources:
        attribution_path = write_attribution_file(
            asset_sources,
            project_dir / "ATTRIBUTION.md",
        )
        project.metadata[
            "attribution_file"
        ] = str(
            attribution_path.resolve()
        )
    if workflow_path:
        project.metadata["comfyui_image_workflow"] = str(
            workflow_path.resolve()
        )
    if comfy_client:
        project.metadata["comfyui_url"] = comfy_client.base_url
    project.metadata["image_generation_failures"] = failures
    project.metadata["semantic_qc_requested"] = bool(semantic_qc)
    project.save(project_dir / "project.json")
    return failures


def _find_scene_image(
    project_dir: Path,
    scene_id: str,
) -> Path | None:
    images_dir = project_dir / "images"
    if not images_dir.is_dir():
        return None
    for suffix in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        candidate = images_dir / f"{scene_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def generate_motion_scene_videos(
    project: MorrowglassProject,
    project_dir: str | Path,
    *,
    overwrite: bool = False,
    comfyui_url: str | None = None,
    comfyui_workflow: str | Path | None = None,
    timeout: float = 2400.0,
) -> list[str]:
    """Animate only scenes the Scene Director marked as motion-worthy."""
    project_dir = Path(project_dir)
    workflow_path = (
        Path(comfyui_workflow).expanduser()
        if comfyui_workflow
        else default_video_workflow(project_dir)
    )
    if not workflow_path or not workflow_path.is_file():
        raise VideoGenerationUnavailable(
            "No ComfyUI video API workflow was found. Put it at "
            "workflows/video.json or pass a workflow path."
        )

    client = ComfyUIClient(comfyui_url)
    if not client.ping():
        raise VideoGenerationUnavailable(
            f"ComfyUI is not reachable at {client.base_url}"
        )
    workflow = load_api_workflow(workflow_path)

    videos_dir = project_dir / "videos"
    candidate_dir = project_dir / "cache" / "generated_videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    generated: list[str] = []
    width, height = project.resolution

    for scene in project.scenes:
        if scene.asset_type not in {
            AssetType.IMAGE_TO_VIDEO,
            AssetType.VIDEO,
        }:
            continue

        existing_videos = [
            item
            for item in videos_dir.glob(f"{scene.scene_id}.*")
            if item.is_file()
        ]
        if existing_videos and not overwrite:
            scene.asset_path = str(existing_videos[0].resolve())
            continue
        if overwrite:
            for item in existing_videos:
                item.unlink()

        image = _find_scene_image(
            project_dir,
            scene.scene_id,
        )
        if not image:
            failures.append(scene.scene_id)
            scene.qc_notes.append(
                "video generation skipped: source image is missing"
            )
            continue

        try:
            uploaded_name = client.upload_image(image)
            prepared = prepare_workflow(
                workflow,
                prompt=scene.image_prompt,
                negative_prompt=project.visual_bible.negative_prompt,
                seed=_scene_seed(scene.scene_id, 99),
                width=width,
                height=height,
                input_image=uploaded_name,
                output_prefix=f"Morrowglass_{scene.scene_id}_video",
                motion_prompt=scene.motion_prompt,
            )
            candidate = client.run(
                prepared,
                target_dir=candidate_dir,
                preferred_kind="video",
                timeout=timeout,
                prefix=scene.scene_id,
            )
            suffix = candidate.suffix.lower()
            if suffix not in VIDEO_SUFFIXES:
                raise ValueError(
                    "ComfyUI video workflow did not produce "
                    f"a video file: {candidate.name}"
                )
            target = videos_dir / f"{scene.scene_id}{suffix}"
            if target.exists():
                target.unlink()
            if candidate.resolve() != target.resolve():
                shutil.move(str(candidate), str(target))
            scene.asset_path = str(target.resolve())
            generated.append(scene.scene_id)
        except Exception as exc:
            failures.append(scene.scene_id)
            scene.qc_notes.append(
                "video generation failed: "
                f"{type(exc).__name__}: {exc}"
            )

    project.metadata["video_provider"] = "comfyui"
    project.metadata["comfyui_video_workflow"] = str(
        workflow_path.resolve()
    )
    project.metadata["comfyui_url"] = client.base_url
    project.metadata["video_generation_failures"] = failures
    project.metadata["video_generated_scenes"] = generated
    project.save(project_dir / "project.json")
    return failures
