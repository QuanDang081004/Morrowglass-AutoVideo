from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.morrowglass.assets import (
    missing_scene_ids,
    resolve_assets,
)
from app.morrowglass.audio import narration_fingerprint
from app.morrowglass.comfyui import default_video_workflow
from app.morrowglass.doctor import (
    required_checks_pass,
    run_doctor,
)
from app.morrowglass.generators import (
    ImageGenerationUnavailable,
    VideoGenerationUnavailable,
)
from app.morrowglass.models import (
    AssetMode,
    MorrowglassProject,
    VisualBible,
)
from app.morrowglass.pipeline import MorrowglassPipeline
from app.morrowglass.timeline import TIMELINE_VERSION


def _mpt_llm_call(prompt: str) -> str:
    from app.services import llm

    return llm._generate_response(prompt)


def _pipeline(
    use_llm: bool = True,
) -> MorrowglassPipeline:
    return MorrowglassPipeline(
        llm_call=_mpt_llm_call if use_llm else None
    )


def _resolved_tts_settings(
    project: MorrowglassProject,
    args,
) -> tuple[str, float, float]:
    voice_name = (
        getattr(args, "voice", "")
        or project.voice_name
    )
    stored_rate = float(
        project.metadata.get(
            "voice_rate",
            1.0,
        )
    )
    stored_volume = float(
        project.metadata.get(
            "voice_volume",
            1.0,
        )
    )
    rate_arg = getattr(
        args,
        "rate",
        None,
    )
    volume_arg = getattr(
        args,
        "volume",
        None,
    )
    voice_rate = (
        float(rate_arg)
        if rate_arg is not None
        else stored_rate
    )
    voice_volume = (
        float(volume_arg)
        if volume_arg is not None
        else stored_volume
    )
    return (
        voice_name,
        voice_rate,
        voice_volume,
    )


def cmd_plan(args) -> int:
    script = Path(args.script).read_text(
        encoding="utf-8-sig"
    )
    bible = VisualBible(
        period=args.period or "",
        location=args.location or "",
    )
    project = _pipeline(
        not args.no_llm
    ).plan_project(
        script,
        args.project_dir,
        title=args.title,
        bible=bible,
        asset_mode=AssetMode(args.asset_mode),
        use_llm=not args.no_llm,
    )
    print(f"Created {len(project.scenes)} scenes")
    print(
        f"Manifest: "
        f"{Path(args.project_dir) / 'project.json'}"
    )
    print(
        f"Prompts:  "
        f"{Path(args.project_dir) / 'prompts'}"
    )
    return 0


def cmd_voice(args) -> int:
    manifest = (
        Path(args.project_dir) / "project.json"
    )
    project = MorrowglassProject.load(manifest)
    voice_name, voice_rate, voice_volume = (
        _resolved_tts_settings(
            project,
            args,
        )
    )
    _pipeline(False).build_audio_timeline(
        project,
        args.project_dir,
        voice_name=voice_name,
        voice_rate=voice_rate,
        voice_volume=voice_volume,
        kokoro_python=args.kokoro_python or None,
        kokoro_en_python=args.kokoro_en_python or None,
        kokoro_vi_python=args.kokoro_vi_python or None,
        kokoro_vi_device=args.kokoro_vi_device,
    )
    project = MorrowglassProject.load(manifest)
    print(
        f"Narration: "
        f"{project.metadata.get('audio_file')}"
    )
    print(
        f"Word timing: "
        f"{project.metadata.get('word_subtitle_file')}"
    )
    timed = sum(
        1
        for scene in project.scenes
        if scene.start is not None
        and scene.end is not None
    )
    print(
        f"Timed scenes: {timed}/{len(project.scenes)}"
    )
    return 0


def cmd_status(args) -> int:
    manifest = (
        Path(args.project_dir) / "project.json"
    )
    project = MorrowglassProject.load(manifest)
    resolve_assets(
        project,
        args.project_dir,
    )
    project.save(manifest)
    missing = missing_scene_ids(project)
    print(f"Scenes: {len(project.scenes)}")
    print(
        f"Ready assets: "
        f"{len(project.scenes) - len(missing)}"
    )
    print(f"Missing assets: {len(missing)}")
    if missing:
        print("Missing: " + ", ".join(missing))
        return 2
    return 0


def _generate_images_for_project(
    project: MorrowglassProject,
    args,
) -> int:
    try:
        failures = _pipeline(
            False
        ).auto_generate_images(
            project,
            args.project_dir,
            overwrite=getattr(
                args,
                "overwrite_images",
                False,
            ),
            semantic_qc=not getattr(
                args,
                "no_semantic_qc",
                False,
            ),
            min_qc_score=getattr(
                args,
                "min_qc_score",
                75.0,
            ),
            max_attempts=getattr(
                args,
                "image_attempts",
                2,
            ),
            provider=getattr(
                args,
                "image_provider",
                "auto",
            ),
            comfyui_url=getattr(
                args,
                "comfyui_url",
                "",
            )
            or None,
            comfyui_workflow=getattr(
                args,
                "comfyui_image_workflow",
                "",
            )
            or None,
        )
    except ImageGenerationUnavailable as exc:
        print(str(exc))
        return 2

    if failures:
        print(
            "Image generation/QC failed for: "
            + ", ".join(failures)
        )
        return 2

    print("All missing scene images were generated.")
    return 0


def _generate_videos_for_project(
    project: MorrowglassProject,
    args,
    *,
    strict: bool,
) -> int:
    try:
        failures = _pipeline(
            False
        ).auto_generate_videos(
            project,
            args.project_dir,
            overwrite=getattr(
                args,
                "overwrite_videos",
                False,
            ),
            comfyui_url=getattr(
                args,
                "comfyui_url",
                "",
            )
            or None,
            comfyui_workflow=getattr(
                args,
                "comfyui_video_workflow",
                "",
            )
            or None,
            timeout=getattr(
                args,
                "video_timeout",
                2400.0,
            ),
        )
    except VideoGenerationUnavailable as exc:
        if strict:
            print(str(exc))
            return 2
        print(
            "Video generation skipped: "
            f"{exc}"
        )
        return 0

    if failures:
        message = (
            "Video generation failed for: "
            + ", ".join(failures)
        )
        if strict:
            print(message)
            return 2
        print(
            message
            + ". Still images will be used for those scenes."
        )
    else:
        print("Motion scenes generated successfully.")
    return 0


def cmd_generate_images(args) -> int:
    manifest = (
        Path(args.project_dir) / "project.json"
    )
    project = MorrowglassProject.load(manifest)
    return _generate_images_for_project(
        project,
        args,
    )


def cmd_generate_videos(args) -> int:
    manifest = (
        Path(args.project_dir) / "project.json"
    )
    project = MorrowglassProject.load(manifest)
    return _generate_videos_for_project(
        project,
        args,
        strict=True,
    )


def cmd_render(args) -> int:
    manifest = (
        Path(args.project_dir) / "project.json"
    )
    project = MorrowglassProject.load(manifest)
    try:
        final = _pipeline(False).render(
            project,
            args.project_dir,
            bgm_file=args.bgm or None,
            bgm_volume=args.bgm_volume,
            font_name=args.font,
            font_size=args.font_size,
            subtitle_position=args.subtitle_position,
            fit_mode=args.fit_mode,
            image_motion=args.image_motion,
        )
    except FileNotFoundError as exc:
        print(str(exc))
        print(
            "Create the missing assets using prompts in "
            f"{Path(args.project_dir) / 'prompts'}"
        )
        return 2

    print(f"Final video: {final}")
    return 0


def _video_workflow_configured(args) -> bool:
    explicit = str(
        getattr(
            args,
            "comfyui_video_workflow",
            "",
        )
        or ""
    ).strip()
    if explicit:
        return Path(explicit).expanduser().is_file()

    workflow = default_video_workflow(
        args.project_dir
    )
    return bool(
        workflow
        and workflow.is_file()
    )


def cmd_run(args) -> int:
    project_dir = Path(args.project_dir)
    manifest = project_dir / "project.json"

    if not manifest.is_file():
        script = Path(args.script).read_text(
            encoding="utf-8-sig"
        )
        bible = VisualBible(
            period=args.period or "",
            location=args.location or "",
        )
        project = _pipeline(
            not args.no_llm
        ).plan_project(
            script,
            project_dir,
            title=args.title,
            bible=bible,
            asset_mode=AssetMode(
                args.asset_mode
            ),
            use_llm=not args.no_llm,
        )
    else:
        project = MorrowglassProject.load(
            manifest
        )
        project.asset_mode = AssetMode(
            args.asset_mode
        )
        if args.voice:
            project.voice_name = args.voice
        project.save(manifest)

    (
        voice_name,
        voice_rate,
        voice_volume,
    ) = _resolved_tts_settings(
        project,
        args,
    )
    audio_file = Path(
        str(
            project.metadata.get(
                "audio_file"
            )
            or ""
        )
    )
    word_timing_file = Path(
        str(
            project.metadata.get(
                "word_subtitle_file"
            )
            or ""
        )
    )
    expected_tts_fingerprint = (
        narration_fingerprint(
            project,
            voice_name=voice_name,
            voice_rate=voice_rate,
            voice_volume=voice_volume,
            kokoro_python=(
                args.kokoro_python
                or None
            ),
            kokoro_en_python=(
                args.kokoro_en_python
                or None
            ),
            kokoro_vi_python=(
                args.kokoro_vi_python
                or None
            ),
            kokoro_vi_device=(
                args.kokoro_vi_device
            ),
        )
    )
    audio_ready = (
        audio_file.is_file()
        and word_timing_file.is_file()
        and project.metadata.get(
            "tts_fingerprint"
        )
        == expected_tts_fingerprint
    )
    timing_ready = (
        project.metadata.get("timeline_version")
        == TIMELINE_VERSION
        and bool(project.scenes)
        and all(
            scene.start is not None
            and scene.end is not None
            for scene in project.scenes
        )
    )
    if not (
        audio_ready
        and timing_ready
    ):
        _pipeline(False).build_audio_timeline(
            project,
            project_dir,
            voice_name=voice_name,
            voice_rate=voice_rate,
            voice_volume=voice_volume,
            kokoro_python=args.kokoro_python or None,
            kokoro_en_python=args.kokoro_en_python or None,
            kokoro_vi_python=args.kokoro_vi_python or None,
            kokoro_vi_device=args.kokoro_vi_device,
        )
        project = MorrowglassProject.load(
            manifest
        )

    missing = _pipeline(
        False
    ).refresh_assets(
        project,
        project_dir,
    )
    should_auto_images = (
        project.asset_mode == AssetMode.AUTO
        or bool(args.auto_images)
    )
    if (
        missing
        and should_auto_images
    ):
        result = _generate_images_for_project(
            project,
            args,
        )
        if result != 0:
            return result
        project = MorrowglassProject.load(
            manifest
        )
        missing = _pipeline(
            False
        ).refresh_assets(
            project,
            project_dir,
        )

    should_auto_videos = (
        bool(args.auto_videos)
        or (
            project.asset_mode == AssetMode.AUTO
            and _video_workflow_configured(
                args
            )
        )
    )
    if should_auto_videos:
        _generate_videos_for_project(
            project,
            args,
            strict=False,
        )
        project = MorrowglassProject.load(
            manifest
        )
        missing = _pipeline(
            False
        ).refresh_assets(
            project,
            project_dir,
        )

    if missing:
        print(
            "HYBRID checkpoint: "
            "assets are required before render."
        )
        print(
            "Missing: "
            + ", ".join(missing)
        )
        print(
            f"Prompts: "
            f"{project_dir / 'prompts'}"
        )
        return 2

    final = _pipeline(False).render(
        project,
        project_dir,
        bgm_file=args.bgm or None,
        bgm_volume=args.bgm_volume,
        font_name=args.font,
        font_size=args.font_size,
        subtitle_position=args.subtitle_position,
        fit_mode=args.fit_mode,
        image_motion=args.image_motion,
    )
    print(f"Final video: {final}")
    return 0


def cmd_doctor(args) -> int:
    checks = run_doctor(
        getattr(
            args,
            "project_dir",
            None,
        ),
        kokoro_python=(
            getattr(
                args,
                "kokoro_python",
                "",
            )
            or None
        ),
        kokoro_en_python=(
            getattr(
                args,
                "kokoro_en_python",
                "",
            )
            or None
        ),
        kokoro_vi_python=(
            getattr(
                args,
                "kokoro_vi_python",
                "",
            )
            or None
        ),
    )
    print("")
    print(
        "Morrowglass environment check"
    )
    print("-" * 72)
    for check in checks:
        marker = (
            "OK"
            if check.ok
            else (
                "OPTIONAL"
                if not check.required
                else "FAIL"
            )
        )
        print(
            f"[{marker:8}] "
            f"{check.name:12} "
            f"{check.detail}"
        )
    print("-" * 72)
    if required_checks_pass(checks):
        print(
            "Required components are ready."
        )
        return 0
    print(
        "One or more required components "
        "need attention."
    )
    return 2


def _add_tts_options(parser) -> None:
    parser.add_argument(
        "--voice",
        default="",
        help=(
            "Examples: kokoro-en:am_michael, "
            "kokoro-vi:manh_dung, or another MPT voice."
        ),
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=None,
        help=(
            "Narration speed. Reuses the project value "
            "when omitted; new projects default to 1.0."
        ),
    )
    parser.add_argument(
        "--volume",
        type=float,
        default=None,
        help=(
            "Narration volume. Reuses the project value "
            "when omitted; new projects default to 1.0."
        ),
    )
    parser.add_argument(
        "--kokoro-python",
        default="",
        help=(
            "Legacy local Kokoro Python path. "
            "Prefer --kokoro-en-python / --kokoro-vi-python."
        ),
    )
    parser.add_argument(
        "--kokoro-en-python",
        default="",
        help=(
            "Python executable for the English Kokoro environment."
        ),
    )
    parser.add_argument(
        "--kokoro-vi-python",
        default="",
        help=(
            "Python executable for the Vietnamese Kokoro environment."
        ),
    )
    parser.add_argument(
        "--kokoro-vi-device",
        choices=["cpu", "cuda"],
        default="cpu",
        help=(
            "Vietnamese Kokoro inference device. "
            "Use cpu on the current Iris Xe machine."
        ),
    )


def _add_render_options(parser) -> None:
    parser.add_argument(
        "--bgm",
        default="",
    )
    parser.add_argument(
        "--bgm-volume",
        type=float,
        default=0.12,
    )
    parser.add_argument(
        "--font",
        default="STHeitiMedium.ttc",
    )
    parser.add_argument(
        "--font-size",
        type=int,
        default=48,
    )
    parser.add_argument(
        "--subtitle-position",
        default="bottom",
    )
    parser.add_argument(
        "--fit-mode",
        choices=["cover", "contain"],
        default="cover",
    )
    parser.add_argument(
        "--image-motion",
        choices=["slow_zoom", "none"],
        default="slow_zoom",
    )


def _add_comfyui_options(parser) -> None:
    parser.add_argument(
        "--comfyui-url",
        default="",
    )
    parser.add_argument(
        "--comfyui-image-workflow",
        default="",
    )
    parser.add_argument(
        "--comfyui-video-workflow",
        default="",
    )


def _add_image_options(parser) -> None:
    parser.add_argument(
        "--auto-images",
        action="store_true",
    )
    parser.add_argument(
        "--overwrite-images",
        action="store_true",
    )
    parser.add_argument(
        "--image-provider",
        choices=[
            "auto",
            "wikimedia",
            "mpt_openai",
            "comfyui",
        ],
        default="auto",
    )
    parser.add_argument(
        "--image-attempts",
        type=int,
        default=2,
    )
    parser.add_argument(
        "--min-qc-score",
        type=float,
        default=75.0,
    )
    parser.add_argument(
        "--no-semantic-qc",
        action="store_true",
    )


def _add_video_options(parser) -> None:
    parser.add_argument(
        "--auto-videos",
        action="store_true",
    )
    parser.add_argument(
        "--overwrite-videos",
        action="store_true",
    )
    parser.add_argument(
        "--video-timeout",
        type=float,
        default=2400.0,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Morrowglass scene-aware "
            "automation layer"
        )
    )
    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    plan = sub.add_parser(
        "plan",
        help=(
            "Turn a script into scene "
            "manifests and generation prompts"
        ),
    )
    plan.add_argument("script")
    plan.add_argument(
        "--project-dir",
        required=True,
    )
    plan.add_argument(
        "--title",
        default="Morrowglass Video",
    )
    plan.add_argument(
        "--period",
        default="",
    )
    plan.add_argument(
        "--location",
        default="",
    )
    plan.add_argument(
        "--asset-mode",
        choices=[
            mode.value
            for mode in AssetMode
        ],
        default="auto",
    )
    plan.add_argument(
        "--no-llm",
        action="store_true",
    )
    plan.set_defaults(func=cmd_plan)

    voice = sub.add_parser(
        "voice",
        help=(
            "Generate TTS narration, "
            "Whisper timing, and scene timeline"
        ),
    )
    voice.add_argument(
        "--project-dir",
        required=True,
    )
    _add_tts_options(voice)
    voice.set_defaults(func=cmd_voice)

    images = sub.add_parser(
        "images",
        help=(
            "Generate missing scene "
            "images and run QC"
        ),
    )
    images.add_argument(
        "--project-dir",
        required=True,
    )
    _add_comfyui_options(images)
    _add_image_options(images)
    images.set_defaults(
        func=cmd_generate_images
    )

    videos = sub.add_parser(
        "videos",
        help=(
            "Generate ComfyUI videos for "
            "motion-worthy scenes"
        ),
    )
    videos.add_argument(
        "--project-dir",
        required=True,
    )
    _add_comfyui_options(videos)
    _add_video_options(videos)
    videos.set_defaults(
        func=cmd_generate_videos
    )

    status = sub.add_parser(
        "status",
        help=(
            "Check which scene assets "
            "are present"
        ),
    )
    status.add_argument(
        "--project-dir",
        required=True,
    )
    status.set_defaults(func=cmd_status)

    doctor = sub.add_parser(
        "doctor",
        help=(
            "Check FFmpeg, Kokoro, Whisper, "
            "ComfyUI, and optional providers"
        ),
    )
    doctor.add_argument(
        "--project-dir",
        default="",
    )
    doctor.add_argument(
        "--kokoro-python",
        default="",
    )
    doctor.add_argument(
        "--kokoro-en-python",
        default="",
    )
    doctor.add_argument(
        "--kokoro-vi-python",
        default="",
    )
    doctor.set_defaults(func=cmd_doctor)

    render = sub.add_parser(
        "render",
        help=(
            "Render timed scene assets "
            "into the final MP4"
        ),
    )
    render.add_argument(
        "--project-dir",
        required=True,
    )
    _add_render_options(render)
    render.set_defaults(func=cmd_render)

    run = sub.add_parser(
        "run",
        help=(
            "Run plan -> voice/timing -> "
            "assets -> final render"
        ),
    )
    run.add_argument("script")
    run.add_argument(
        "--project-dir",
        required=True,
    )
    run.add_argument(
        "--title",
        default="Morrowglass Video",
    )
    run.add_argument(
        "--period",
        default="",
    )
    run.add_argument(
        "--location",
        default="",
    )
    run.add_argument(
        "--asset-mode",
        choices=[
            mode.value
            for mode in AssetMode
        ],
        default="auto",
    )
    run.add_argument(
        "--no-llm",
        action="store_true",
    )
    _add_tts_options(run)
    _add_comfyui_options(run)
    _add_image_options(run)
    _add_video_options(run)
    _add_render_options(run)
    run.set_defaults(func=cmd_run)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
