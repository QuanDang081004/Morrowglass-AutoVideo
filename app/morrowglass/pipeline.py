from __future__ import annotations

from pathlib import Path
from typing import Callable

from .assets import (
    missing_scene_ids,
    resolve_assets,
    write_prompt_pack,
)
from .audio import synthesize_narration, transcribe_word_timing
from .bible import enrich_visual_bible
from .director import SceneDirector
from .generators import (
    generate_missing_scene_images,
    generate_motion_scene_videos,
)
from .models import AssetMode, MorrowglassProject, VisualBible
from .renderer import render_final_video
from .timeline import TIMELINE_VERSION, assign_from_srt, parse_srt


class MorrowglassPipeline:
    def __init__(
        self,
        llm_call: Callable[[str], str] | None = None,
    ):
        self.director = SceneDirector(llm_call=llm_call)

    def plan_project(
        self,
        script: str,
        project_dir: str | Path,
        *,
        title: str = "Morrowglass Video",
        bible: VisualBible | None = None,
        asset_mode: AssetMode = AssetMode.HYBRID,
        use_llm: bool = True,
    ) -> MorrowglassProject:
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "images",
            "videos",
            "audio",
            "subtitles",
            "prompts",
            "output",
            "cache",
        ):
            (project_dir / name).mkdir(exist_ok=True)

        bible = bible or VisualBible()
        if use_llm:
            bible = enrich_visual_bible(
                script,
                bible,
                llm_call=self.director.llm_call,
            )
        project = self.director.plan(
            script,
            title=title,
            bible=bible,
            use_llm=use_llm,
        )
        project.asset_mode = asset_mode
        write_prompt_pack(project, project_dir)
        resolve_assets(project, project_dir)
        project.save(project_dir / "project.json")
        return project

    def attach_timeline_from_srt(
        self,
        project: MorrowglassProject,
        subtitle_file: str | Path,
        *,
        audio_duration: float | None = None,
    ) -> MorrowglassProject:
        assign_from_srt(
            project.scenes,
            parse_srt(subtitle_file),
            audio_duration=audio_duration,
        )
        return project

    def build_audio_timeline(
        self,
        project: MorrowglassProject,
        project_dir: str | Path,
        *,
        voice_name: str | None = None,
        voice_rate: float = 1.0,
        voice_volume: float = 1.0,
        kokoro_python: str | Path | None = None,
        kokoro_en_python: str | Path | None = None,
        kokoro_vi_python: str | Path | None = None,
        kokoro_vi_device: str = "cpu",
    ) -> MorrowglassProject:
        audio_file, duration = synthesize_narration(
            project,
            project_dir,
            voice_name=voice_name,
            voice_rate=voice_rate,
            voice_volume=voice_volume,
            kokoro_python=kokoro_python,
            kokoro_en_python=kokoro_en_python,
            kokoro_vi_python=kokoro_vi_python,
            kokoro_vi_device=kokoro_vi_device,
        )
        words_srt = transcribe_word_timing(
            project,
            project_dir,
            audio_file,
        )
        self.attach_timeline_from_srt(
            project,
            words_srt,
            audio_duration=duration,
        )
        project.metadata["timeline_version"] = TIMELINE_VERSION
        project.save(Path(project_dir) / "project.json")
        return project

    def refresh_assets(
        self,
        project: MorrowglassProject,
        project_dir: str | Path,
    ) -> list[str]:
        resolve_assets(project, project_dir)
        project.save(Path(project_dir) / "project.json")
        return missing_scene_ids(project)

    def auto_generate_images(
        self,
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
        self.refresh_assets(project, project_dir)
        failures = generate_missing_scene_images(
            project,
            project_dir,
            overwrite=overwrite,
            semantic_qc=semantic_qc,
            min_qc_score=min_qc_score,
            max_attempts=max_attempts,
            provider=provider,
            comfyui_url=comfyui_url,
            comfyui_workflow=comfyui_workflow,
        )
        self.refresh_assets(project, project_dir)
        return failures

    def auto_generate_videos(
        self,
        project: MorrowglassProject,
        project_dir: str | Path,
        *,
        overwrite: bool = False,
        comfyui_url: str | None = None,
        comfyui_workflow: str | Path | None = None,
        timeout: float = 2400.0,
    ) -> list[str]:
        self.refresh_assets(project, project_dir)
        failures = generate_motion_scene_videos(
            project,
            project_dir,
            overwrite=overwrite,
            comfyui_url=comfyui_url,
            comfyui_workflow=comfyui_workflow,
            timeout=timeout,
        )
        self.refresh_assets(project, project_dir)
        return failures

    def render(
        self,
        project: MorrowglassProject,
        project_dir: str | Path,
        **kwargs,
    ) -> Path:
        missing = self.refresh_assets(project, project_dir)
        if missing:
            raise FileNotFoundError(
                "missing scene assets: " + ", ".join(missing)
            )
        return render_final_video(
            project,
            project_dir,
            **kwargs,
        )
