from __future__ import annotations

import os
import re
import hashlib
import json
import math
import shutil
from pathlib import Path

from app.models.schema import VideoAspect
from app.services import material

from .archive import (
    archive_asset_keys,
    archive_record_keys,
    archive_text_tokens,
    attribution_record,
    download_archive_image,
    rank_archive_assets,
    relevance_score,
    search_openverse_images,
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
from .query_language import build_archive_query


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


def _file_sha256(
    path: str | Path,
) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def _motion_source_fingerprint(
    *,
    scene,
    project: MorrowglassProject,
    image: Path,
    workflow_path: Path,
) -> str:
    payload = {
        "scene_id": scene.scene_id,
        "image_sha256": _file_sha256(image),
        "image_prompt": scene.image_prompt,
        "motion_prompt": scene.motion_prompt,
        "aspect": project.aspect,
        "resolution": list(project.resolution),
        "workflow_sha256": _file_sha256(
            workflow_path
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(
        encoded
    ).hexdigest()


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
    project: MorrowglassProject,
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
        video_aspect=VideoAspect(
            project.aspect
        ),
        save_dir=str(images_dir),
    )
    if not results:
        return None
    source = Path(results[0].url)
    return source if source.is_file() else None


def _archive_query_variants(
    *,
    scene,
    project: MorrowglassProject,
) -> list[str]:
    base = build_archive_query(
        scene.narration,
        script=project.script,
        location=project.visual_bible.location,
        period=project.visual_bible.period,
        existing_query=str(
            getattr(
                scene,
                "search_query",
                "",
            )
            or ""
        ),
    )
    words = base.split()

    short = " ".join(
        words[:5]
    ).strip()
    context = build_archive_query(
        "",
        script=project.script,
        location=project.visual_bible.location,
        period=project.visual_bible.period,
        existing_query="",
        max_terms=3,
    )
    context_specific = " ".join(
        value
        for value in (
            context,
            " ".join(words[-3:]),
        )
        if value
    ).strip()

    variants: list[str] = []
    for value in (
        base,
        short,
        context_specific,
        context,
    ):
        normalized = " ".join(
            str(value or "").split()
        ).strip()
        if (
            normalized
            and normalized not in variants
        ):
            variants.append(
                normalized
            )
    return variants

def _collect_archive_results(
    queries: list[str],
    *,
    provider: str,
    project: MorrowglassProject,
    attempt: int,
) -> list:
    assets = []
    seen_keys: set[str] = set()

    for query in queries:
        if provider == "wikimedia":
            found = search_wikimedia_images(
                query,
                limit=max(
                    16,
                    attempt + 10,
                ),
                thumb_width=max(
                    project.resolution
                ),
            )
        elif provider == "openverse":
            found = search_openverse_images(
                query,
                limit=max(
                    20,
                    attempt + 12,
                ),
            )
        else:
            raise ValueError(
                f"unknown archive provider: {provider}"
            )

        for asset in found:
            keys = archive_asset_keys(
                asset
            )
            if (
                keys
                and keys & seen_keys
            ):
                continue
            seen_keys.update(
                keys
            )
            assets.append(
                asset
            )

        if len(assets) >= max(
            8,
            attempt + 4,
        ):
            break

    return assets


def _pick_archive_asset(
    assets: list,
    *,
    scene,
    base_query: str,
    required_terms: set[str],
    excluded_asset_keys: set[str],
):
    ranked = rank_archive_assets(
        assets,
        query=base_query,
        visual_description=base_query,
        excluded_keys=excluded_asset_keys,
        required_terms=required_terms,
    )
    if not ranked:
        return None

    asset = ranked[0]
    score = relevance_score(
        asset,
        base_query,
        base_query,
    )
    if score < 4.0:
        return None
    return asset


def _generate_wikimedia_candidate(
    *,
    scene,
    project: MorrowglassProject,
    candidate_dir: Path,
    attempt: int,
    excluded_asset_keys: set[str] | None = None,
):
    queries = _archive_query_variants(
        scene=scene,
        project=project,
    )
    base_query = (
        queries[0]
        if queries
        else scene.narration
    )
    context_query = build_archive_query(
        "",
        script=project.script,
        location=(
            project.visual_bible.location
        ),
        period=(
            project.visual_bible.period
        ),
        existing_query="",
        max_terms=3,
    )
    required_terms = (
        archive_text_tokens(
            base_query
        )
        - archive_text_tokens(
            context_query
        )
    )
    required_terms -= {
        "historical",
        "artifact",
        "documentary",
        "ancient",
    }
    excluded = (
        excluded_asset_keys
        or set()
    )

    asset = None
    provider_errors: list[str] = []

    try:
        wikimedia_assets = (
            _collect_archive_results(
                queries,
                provider="wikimedia",
                project=project,
                attempt=attempt,
            )
        )
        asset = _pick_archive_asset(
            wikimedia_assets,
            scene=scene,
            base_query=base_query,
            required_terms=required_terms,
            excluded_asset_keys=excluded,
        )
    except Exception as exc:
        provider_errors.append(
            "Wikimedia: "
            f"{type(exc).__name__}: {exc}"
        )

    if asset is None:
        try:
            openverse_assets = (
                _collect_archive_results(
                    queries,
                    provider="openverse",
                    project=project,
                    attempt=attempt,
                )
            )
            asset = _pick_archive_asset(
                openverse_assets,
                scene=scene,
                base_query=base_query,
                required_terms=required_terms,
                excluded_asset_keys=excluded,
            )
        except Exception as exc:
            provider_errors.append(
                "Openverse: "
                f"{type(exc).__name__}: {exc}"
            )

    if asset is None:
        if required_terms:
            scene.qc_notes.append(
                "free archive rejected: no unused result matched "
                "scene-specific terms "
                + ", ".join(
                    sorted(
                        required_terms
                    )
                )
            )
        if provider_errors:
            scene.qc_notes.extend(
                provider_errors
            )
        return None, None

    safe_provider = re.sub(
        r"[^a-z0-9_-]+",
        "_",
        str(
            getattr(
                asset,
                "provider",
                "archive",
            )
            or "archive"
        ).lower(),
    )
    target = (
        candidate_dir
        / (
            f"{scene.scene_id}_"
            f"{safe_provider}_{attempt}.jpg"
        )
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
        comfy_client = ComfyUIClient(
            comfyui_url
        )
        if not comfy_client.ping():
            if (
                str(provider or "auto")
                .strip()
                .lower()
                == "auto"
            ):
                provider_name = (
                    "wikimedia"
                )
                workflow_path = None
                comfy_client = None
            else:
                raise ImageGenerationUnavailable(
                    "ComfyUI is not reachable at "
                    f"{comfy_client.base_url}"
                )
        else:
            comfy_workflow_data = (
                load_api_workflow(
                    workflow_path
                )
            )

    failures: list[str] = []
    asset_sources = (
        {}
        if overwrite
        else dict(
            project.metadata.get(
                "asset_sources"
            )
            or {}
        )
    )
    asset_hashes = (
        {}
        if overwrite
        else dict(
            project.metadata.get(
                "asset_hashes"
            )
            or {}
        )
    )
    used_archive_keys: set[str] = set()
    used_image_hashes: set[str] = set()

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
            existing_hash = (
                _file_sha256(
                    existing
                )
            )
            used_image_hashes.add(
                existing_hash
            )
            asset_hashes[
                scene.scene_id
            ] = existing_hash
            record = asset_sources.get(
                scene.scene_id
            )
            if isinstance(
                record,
                dict,
            ):
                used_archive_keys.update(
                    archive_record_keys(
                        record
                    )
                )
            continue

        existing_images = [
            item
            for item in images_dir.glob(f"{scene.scene_id}.*")
            if item.is_file()
        ]
        if existing_images and not overwrite:
            scene.asset_path = str(
                existing_images[0].resolve()
            )
            existing_hash = (
                _file_sha256(
                    existing_images[0]
                )
            )
            used_image_hashes.add(
                existing_hash
            )
            asset_hashes[
                scene.scene_id
            ] = existing_hash
            record = asset_sources.get(
                scene.scene_id
            )
            if isinstance(
                record,
                dict,
            ):
                used_archive_keys.update(
                    archive_record_keys(
                        record
                    )
                )
            continue

        if overwrite:
            _remove_scene_images(images_dir, scene.scene_id)

        accepted = False
        scene.qc_notes = []
        scene_excluded_asset_keys = set(
            used_archive_keys
        )
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
                        project=project,
                        candidate_dir=candidate_dir,
                        attempt=attempt,
                        excluded_asset_keys=(
                            scene_excluded_asset_keys
                        ),
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
                    project=project,
                    images_dir=candidate_dir,
                )

            if not source or not source.is_file():
                scene.qc_notes.append(
                    f"attempt {attempt}: provider returned no image"
                )
                continue

            candidate_archive_keys = (
                archive_asset_keys(
                    archive_asset
                )
                if archive_asset is not None
                else set()
            )
            scene_excluded_asset_keys.update(
                candidate_archive_keys
            )
            candidate_hash = _file_sha256(
                source
            )
            if candidate_hash in used_image_hashes:
                scene.qc_notes.append(
                    f"attempt {attempt}: duplicate image hash rejected"
                )
                try:
                    source.unlink()
                except OSError:
                    pass
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
                used_image_hashes.add(
                    candidate_hash
                )
                asset_hashes[
                    scene.scene_id
                ] = candidate_hash
                if archive_asset is not None:
                    record = attribution_record(
                        archive_asset
                    )
                    record[
                        "image_sha256"
                    ] = candidate_hash
                    asset_sources[
                        scene.scene_id
                    ] = record
                    used_archive_keys.update(
                        candidate_archive_keys
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
    project.metadata["asset_hashes"] = asset_hashes
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
    video_sources = dict(
        project.metadata.get("video_sources")
        or {}
    )
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

        source_fingerprint = (
            _motion_source_fingerprint(
                scene=scene,
                project=project,
                image=image,
                workflow_path=workflow_path,
            )
        )
        previous_source = video_sources.get(
            scene.scene_id,
            {}
        )
        can_reuse_video = (
            bool(existing_videos)
            and not overwrite
            and isinstance(
                previous_source,
                dict,
            )
            and previous_source.get(
                "fingerprint"
            )
            == source_fingerprint
        )
        if can_reuse_video:
            scene.asset_path = str(
                existing_videos[0].resolve()
            )
            continue

        for item in existing_videos:
            item.unlink()

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
            video_sources[
                scene.scene_id
            ] = {
                "fingerprint": (
                    source_fingerprint
                ),
                "source_image": str(
                    image.resolve()
                ),
                "source_image_sha256": (
                    _file_sha256(image)
                ),
                "video_file": str(
                    target.resolve()
                ),
            }
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
    project.metadata["video_sources"] = video_sources
    project.save(project_dir / "project.json")
    return failures
