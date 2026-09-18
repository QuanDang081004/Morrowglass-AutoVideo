from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.morrowglass.assets import missing_scene_ids, resolve_assets
from app.morrowglass.models import AssetMode, MorrowglassProject, VisualBible
from app.morrowglass.pipeline import MorrowglassPipeline


def _mpt_llm_call(prompt: str) -> str:
    from app.services import llm
    return llm._generate_response(prompt)


def _pipeline(use_llm: bool = True) -> MorrowglassPipeline:
    return MorrowglassPipeline(llm_call=_mpt_llm_call if use_llm else None)


def cmd_plan(args) -> int:
    script = Path(args.script).read_text(encoding="utf-8-sig")
    bible = VisualBible(period=args.period or "", location=args.location or "")
    project = _pipeline(not args.no_llm).plan_project(script, args.project_dir, title=args.title, bible=bible, asset_mode=AssetMode(args.asset_mode), use_llm=not args.no_llm)
    print(f"Created {len(project.scenes)} scenes")
    print(f"Manifest: {Path(args.project_dir) / 'project.json'}")
    print(f"Prompts:  {Path(args.project_dir) / 'prompts'}")
    return 0


def cmd_voice(args) -> int:
    manifest = Path(args.project_dir) / "project.json"
    project = MorrowglassProject.load(manifest)
    _pipeline(False).build_audio_timeline(project, args.project_dir, voice_name=args.voice or None, voice_rate=args.rate)
    project = MorrowglassProject.load(manifest)
    print(f"Narration: {project.metadata.get('audio_file')}")
    print(f"Word timing: {project.metadata.get('word_subtitle_file')}")
    print(f"Timed scenes: {sum(1 for s in project.scenes if s.start is not None and s.end is not None)}/{len(project.scenes)}")
    return 0


def cmd_status(args) -> int:
    manifest = Path(args.project_dir) / "project.json"
    project = MorrowglassProject.load(manifest)
    resolve_assets(project, args.project_dir); project.save(manifest)
    missing = missing_scene_ids(project)
    print(f"Scenes: {len(project.scenes)}")
    print(f"Ready assets: {len(project.scenes) - len(missing)}")
    print(f"Missing assets: {len(missing)}")
    if missing: print("Missing: " + ", ".join(missing)); return 2
    return 0


def cmd_render(args) -> int:
    manifest = Path(args.project_dir) / "project.json"
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
        )
    except FileNotFoundError as exc:
        print(str(exc))
        print(f"Create the missing assets using prompts in {Path(args.project_dir) / 'prompts'}")
        return 2
    print(f"Final video: {final}")
    return 0


def cmd_run(args) -> int:
    project_dir = Path(args.project_dir)
    manifest = project_dir / "project.json"
    if not manifest.is_file():
        script = Path(args.script).read_text(encoding="utf-8-sig")
        bible = VisualBible(period=args.period or "", location=args.location or "")
        project = _pipeline(not args.no_llm).plan_project(
            script, project_dir, title=args.title, bible=bible,
            asset_mode=AssetMode(args.asset_mode), use_llm=not args.no_llm,
        )
    else:
        project = MorrowglassProject.load(manifest)

    if not project.metadata.get("audio_file") or not project.metadata.get("word_subtitle_file"):
        _pipeline(False).build_audio_timeline(
            project, project_dir, voice_name=args.voice or None, voice_rate=args.rate
        )
        project = MorrowglassProject.load(manifest)

    missing = _pipeline(False).refresh_assets(project, project_dir)
    if missing:
        print("HYBRID checkpoint: assets are required before render.")
        print("Missing: " + ", ".join(missing))
        print(f"Prompts: {project_dir / 'prompts'}")
        return 2

    final = _pipeline(False).render(
        project, project_dir, bgm_file=args.bgm or None,
        bgm_volume=args.bgm_volume, font_name=args.font,
        font_size=args.font_size, subtitle_position=args.subtitle_position,
        fit_mode=args.fit_mode,
    )
    print(f"Final video: {final}")
    return 0


def _add_render_options(parser):
    parser.add_argument("--bgm", default="")
    parser.add_argument("--bgm-volume", type=float, default=0.12)
    parser.add_argument("--font", default="STHeitiMedium.ttc")
    parser.add_argument("--font-size", type=int, default=48)
    parser.add_argument("--subtitle-position", default="bottom")
    parser.add_argument("--fit-mode", choices=["cover", "contain"], default="cover")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Morrowglass scene-aware automation layer")
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Turn a script into scene manifests and generation prompts")
    plan.add_argument("script"); plan.add_argument("--project-dir", required=True); plan.add_argument("--title", default="Morrowglass Video")
    plan.add_argument("--period", default=""); plan.add_argument("--location", default=""); plan.add_argument("--asset-mode", choices=[m.value for m in AssetMode], default="hybrid")
    plan.add_argument("--no-llm", action="store_true"); plan.set_defaults(func=cmd_plan)

    voice = sub.add_parser("voice", help="Generate TTS narration, Whisper word timing, and scene timeline")
    voice.add_argument("--project-dir", required=True); voice.add_argument("--voice", default=""); voice.add_argument("--rate", type=float, default=1.0); voice.set_defaults(func=cmd_voice)

    status = sub.add_parser("status", help="Check which scene assets are present")
    status.add_argument("--project-dir", required=True); status.set_defaults(func=cmd_status)

    render = sub.add_parser("render", help="Render timed scene assets into the final MP4")
    render.add_argument("--project-dir", required=True); _add_render_options(render); render.set_defaults(func=cmd_render)

    run = sub.add_parser("run", help="Run plan -> voice/timing -> asset checkpoint -> final render")
    run.add_argument("script"); run.add_argument("--project-dir", required=True); run.add_argument("--title", default="Morrowglass Video")
    run.add_argument("--period", default=""); run.add_argument("--location", default=""); run.add_argument("--asset-mode", choices=[m.value for m in AssetMode], default="hybrid")
    run.add_argument("--no-llm", action="store_true"); run.add_argument("--voice", default=""); run.add_argument("--rate", type=float, default=1.0)
    _add_render_options(run); run.set_defaults(func=cmd_run)
    return p


def main() -> int:
    args = build_parser().parse_args(); return int(args.func(args))

if __name__ == "__main__": sys.exit(main())
