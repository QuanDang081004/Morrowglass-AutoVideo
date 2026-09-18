from __future__ import annotations

from pathlib import Path

from .models import MorrowglassProject

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")


def expected_asset_stems(scene_id: str) -> list[str]:
    return [scene_id, scene_id.replace("scene_", "s")]


def resolve_assets(project: MorrowglassProject, project_dir: str | Path) -> MorrowglassProject:
    project_dir = Path(project_dir)
    search_dirs = [project_dir / "videos", project_dir / "images", project_dir / "assets"]
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


def missing_scene_ids(project: MorrowglassProject) -> list[str]:
    return [scene.scene_id for scene in project.scenes if not scene.asset_path]
