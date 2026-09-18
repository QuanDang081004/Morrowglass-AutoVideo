from __future__ import annotations

from pathlib import Path
from typing import Callable
from .assets import missing_scene_ids, resolve_assets, write_prompt_pack
from .director import SceneDirector
from .models import AssetMode, MorrowglassProject, VisualBible
from .timeline import assign_from_srt, parse_srt

class MorrowglassPipeline:
    def __init__(self, llm_call: Callable[[str], str] | None = None): self.director = SceneDirector(llm_call=llm_call)
    def plan_project(self, script: str, project_dir: str | Path, *, title: str = "Morrowglass Video", bible: VisualBible | None = None, asset_mode: AssetMode = AssetMode.HYBRID, use_llm: bool = True) -> MorrowglassProject:
        project_dir = Path(project_dir); project_dir.mkdir(parents=True, exist_ok=True)
        for name in ("images", "videos", "audio", "subtitles", "prompts", "output", "cache"): (project_dir / name).mkdir(exist_ok=True)
        project = self.director.plan(script, title=title, bible=bible, use_llm=use_llm); project.asset_mode = asset_mode
        write_prompt_pack(project, project_dir); resolve_assets(project, project_dir); project.save(project_dir / "project.json"); return project
    def attach_timeline_from_srt(self, project: MorrowglassProject, subtitle_file: str | Path, *, audio_duration: float | None = None) -> MorrowglassProject:
        assign_from_srt(project.scenes, parse_srt(subtitle_file), audio_duration=audio_duration); return project
    def refresh_assets(self, project: MorrowglassProject, project_dir: str | Path) -> list[str]:
        resolve_assets(project, project_dir); project.save(Path(project_dir) / "project.json"); return missing_scene_ids(project)
