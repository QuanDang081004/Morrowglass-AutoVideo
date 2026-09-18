from __future__ import annotations

import subprocess
from pathlib import Path

from app.models.schema import VideoAspect, VideoFitMode, VideoParams
from app.services import video
from app.utils import utils

from .captions import build_readable_captions
from .models import MorrowglassProject

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _fit_filter(width: int, height: int, fit_mode: str = "cover", fps: int = 30) -> str:
    mode = VideoFitMode(fit_mode)
    if mode == VideoFitMode.cover:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},format=yuv420p"
        )
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,fps={fps},format=yuv420p"
    )


def _build_scene_ffmpeg_command(
    *,
    asset_path: str | Path,
    output_path: str | Path,
    duration: float,
    width: int,
    height: int,
    fit_mode: str = "cover",
    fps: int = 30,
    ffmpeg_binary: str | None = None,
) -> list[str]:
    asset = Path(asset_path)
    suffix = asset.suffix.lower()
    if duration <= 0:
        raise ValueError("scene duration must be positive")
    if suffix not in IMAGE_EXTS | VIDEO_EXTS:
        raise ValueError(f"unsupported scene asset: {asset}")

    command = [ffmpeg_binary or utils.get_ffmpeg_binary(), "-y"]
    if suffix in IMAGE_EXTS:
        command.extend(["-loop", "1", "-framerate", str(fps), "-i", str(asset)])
    else:
        command.extend(["-stream_loop", "-1", "-i", str(asset)])

    command.extend(
        [
            "-t",
            f"{duration:.3f}",
            "-vf",
            _fit_filter(width, height, fit_mode, fps),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def _run_ffmpeg(command: list[str], *, label: str) -> None:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"{label} failed: {details[-4000:]}")


def render_scene_timeline(
    project: MorrowglassProject,
    project_dir: str | Path,
    *,
    fit_mode: str = "cover",
    fps: int = 30,
) -> Path:
    """Render every scene to its exact timeline duration, then concatenate."""
    project_dir = Path(project_dir)
    cache_dir = project_dir / "cache" / "scene_clips"
    output_dir = project_dir / "output"
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    width, height = project.resolution
    clip_files: list[str] = []

    for scene in project.scenes:
        if not scene.asset_path:
            raise FileNotFoundError(f"missing asset for {scene.scene_id}")
        asset = Path(scene.asset_path)
        if not asset.is_file():
            raise FileNotFoundError(f"asset does not exist for {scene.scene_id}: {asset}")
        if scene.start is None or scene.end is None:
            raise ValueError(f"scene timing is missing for {scene.scene_id}")
        duration = scene.end - scene.start
        if duration <= 0.02:
            raise ValueError(f"invalid duration for {scene.scene_id}: {duration:.3f}s")

        scene_clip = cache_dir / f"{scene.scene_id}.mp4"
        command = _build_scene_ffmpeg_command(
            asset_path=asset,
            output_path=scene_clip,
            duration=duration,
            width=width,
            height=height,
            fit_mode=fit_mode,
            fps=fps,
        )
        _run_ffmpeg(command, label=f"render {scene.scene_id}")
        clip_files.append(str(scene_clip))

    audio_duration = float(project.metadata.get("audio_duration") or 0)
    if audio_duration <= 0:
        audio_duration = float(project.scenes[-1].end or 0) if project.scenes else 0
    if audio_duration <= 0:
        raise ValueError("audio duration is unavailable")

    combined = output_dir / "scene_timeline.mp4"
    video.concat_video_clips_with_ffmpeg(
        clip_files=clip_files,
        output_file=str(combined),
        threads=2,
        output_dir=str(cache_dir),
        max_duration=audio_duration,
    )
    project.metadata["combined_video_file"] = str(combined.resolve())
    return combined


def render_final_video(
    project: MorrowglassProject,
    project_dir: str | Path,
    *,
    bgm_file: str | Path | None = None,
    bgm_volume: float = 0.12,
    font_name: str = "STHeitiMedium.ttc",
    font_size: int = 48,
    subtitle_position: str = "bottom",
    text_color: str = "#FFFFFF",
    stroke_color: str = "#000000",
    stroke_width: float = 2.0,
    fit_mode: str = "cover",
) -> Path:
    project_dir = Path(project_dir)
    audio_file = Path(str(project.metadata.get("audio_file") or ""))
    word_srt = Path(str(project.metadata.get("word_subtitle_file") or ""))
    if not audio_file.is_file():
        raise FileNotFoundError("narration audio is missing; run the voice stage first")
    if not word_srt.is_file():
        raise FileNotFoundError("word timing is missing; run the voice stage first")

    combined = render_scene_timeline(project, project_dir, fit_mode=fit_mode)
    subtitle_file = build_readable_captions(
        word_srt,
        project_dir / "subtitles" / "captions.srt",
    )

    params = VideoParams(
        video_subject=project.title,
        video_script=project.script,
        video_aspect=VideoAspect.landscape.value,
        video_fit_mode=VideoFitMode(fit_mode),
        voice_name=project.voice_name,
        bgm_type="custom" if bgm_file else "",
        bgm_file="",
        bgm_volume=float(bgm_volume),
        subtitle_enabled=True,
        subtitle_position=subtitle_position,
        subtitle_display_mode="sentence",
        subtitle_animation="none",
        font_name=font_name,
        font_size=int(font_size),
        text_fore_color=text_color,
        stroke_color=stroke_color,
        stroke_width=float(stroke_width),
        n_threads=2,
    )
    final_file = project_dir / "output" / "morrowglass_final.mp4"
    bgm_override = ""
    if bgm_file:
        candidate = Path(bgm_file)
        if not candidate.is_file():
            raise FileNotFoundError(f"BGM file does not exist: {candidate}")
        bgm_override = str(candidate.resolve())

    video.generate_video(
        video_path=str(combined),
        audio_path=str(audio_file),
        subtitle_path=str(subtitle_file),
        output_file=str(final_file),
        params=params,
        bgm_file_override=bgm_override,
    )
    if not final_file.is_file() or final_file.stat().st_size == 0:
        raise RuntimeError("final render did not produce a video")

    project.metadata["subtitle_file"] = str(subtitle_file.resolve())
    project.metadata["final_video_file"] = str(final_file.resolve())
    project.metadata["bgm_file"] = bgm_override
    project.save(project_dir / "project.json")
    return final_file
