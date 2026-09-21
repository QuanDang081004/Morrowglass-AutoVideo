from __future__ import annotations

import json
from pathlib import Path

from .models import MorrowglassProject

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


def expected_asset_stems(scene_id: str) -> list[str]:
    return [scene_id, scene_id.replace("scene_", "s")]


def _asset_resolution_status(
    project: MorrowglassProject,
    scene_id: str,
    asset_path: str,
) -> str:
    if not asset_path:
        return "needs_manual_image"

    source = (
        project.metadata.get("asset_sources", {})
        or {}
    ).get(scene_id)
    if isinstance(source, dict) and source.get("provider") in {
        "wikimedia",
        "openverse",
        "metmuseum",
    }:
        return "resolved_by_search"

    return "resolved_by_manual_image"


def resolve_assets(project: MorrowglassProject, project_dir: str | Path) -> MorrowglassProject:
    project_dir = Path(project_dir)
    search_dirs = [project_dir / "videos", project_dir / "images", project_dir / "assets"]
    statuses: dict[str, str] = {}
    for scene in project.scenes:
        scene.asset_path = ""
        for folder in search_dirs:
            if not folder.exists():
                continue
            for stem in expected_asset_stems(scene.scene_id):
                for ext in VIDEO_EXTS + IMAGE_EXTS:
                    candidate = folder / f"{stem}{ext}"
                    if candidate.is_file():
                        scene.asset_path = str(candidate.resolve())
                        break
                if scene.asset_path:
                    break
            if scene.asset_path:
                break
        statuses[scene.scene_id] = _asset_resolution_status(
            project,
            scene.scene_id,
            scene.asset_path,
        )

    project.metadata["asset_resolution_status"] = statuses
    return project


def write_prompt_pack(project: MorrowglassProject, project_dir: str | Path) -> list[Path]:
    project_dir = Path(project_dir)
    prompt_dir = project_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for scene in project.scenes:
        text = [
            f"SCENE: {scene.scene_id}",
            f"NARRATION: {scene.narration}",
            "",
            "EXPECTED VISUAL:",
            scene.visual_description,
            "",
            "SEARCH QUERY:",
            scene.search_query or "(none)",
            "",
            "IMAGE PROMPT:",
            scene.image_prompt,
            "",
            "MOTION PROMPT:",
            scene.motion_prompt or "(still image preferred)",
            "",
            "HISTORICAL CONSTRAINTS:",
            *(f"- {item}" for item in scene.historical_constraints),
        ]
        path = prompt_dir / f"{scene.scene_id}.txt"
        path.write_text("\n".join(text).strip() + "\n", encoding="utf-8")
        out.append(path)
    return out


def _manual_queue_record(scene) -> dict:
    return {
        "scene_id": scene.scene_id,
        "target_filename": f"images/{scene.scene_id}.png",
        "narration": scene.narration,
        "expected_visual": scene.visual_description,
        "search_query": scene.search_query,
        "image_prompt": scene.image_prompt,
        "motion_prompt": scene.motion_prompt,
        "historical_constraints": list(scene.historical_constraints),
        "research_notes": list(scene.qc_notes),
    }


def write_manual_image_queue(
    project: MorrowglassProject,
    project_dir: str | Path,
) -> list[str]:
    """Write a handoff pack only for scenes that still need a manual image."""
    project_dir = Path(project_dir)
    prompt_dir = project_dir / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    missing = [
        scene
        for scene in project.scenes
        if not scene.asset_path
    ]
    records = [
        _manual_queue_record(scene)
        for scene in missing
    ]

    json_path = prompt_dir / "MANUAL_IMAGES.json"
    md_path = prompt_dir / "MANUAL_IMAGES.md"
    json_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Morrowglass manual image queue",
        "",
        (
            "Only scenes that could not be resolved by strict archive research "
            "appear here. Generate or source one image for each scene, then save "
            "it under the exact target filename shown below."
        ),
        "",
    ]
    if not records:
        lines.append("No manual images are required.")
    else:
        for record in records:
            lines.extend(
                [
                    f"## {record['scene_id']}",
                    f"- Target: \x60{record['target_filename']}\x60",
                    f"- Narration: {record['narration']}",
                    f"- Expected visual: {record['expected_visual']}",
                    f"- Research query: {record['search_query'] or '(none)'}",
                    "",
                    "### AI image prompt",
                    "",
                    record["image_prompt"],
                    "",
                ]
            )
            constraints = record["historical_constraints"]
            if constraints:
                lines.append("### Historical constraints")
                lines.extend(f"- {item}" for item in constraints)
                lines.append("")
            notes = record["research_notes"]
            if notes:
                lines.append("### Why research was not accepted")
                lines.extend(f"- {item}" for item in notes)
                lines.append("")

    md_path.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )
    project.metadata["manual_image_queue"] = [
        record["scene_id"]
        for record in records
    ]
    project.metadata["manual_image_queue_file"] = str(
        md_path.resolve()
    )
    return list(project.metadata["manual_image_queue"])


def missing_scene_ids(project: MorrowglassProject) -> list[str]:
    return [scene.scene_id for scene in project.scenes if not scene.asset_path]
