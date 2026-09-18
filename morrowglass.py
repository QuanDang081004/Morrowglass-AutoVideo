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
    return p


def main() -> int:
    args = build_parser().parse_args(); return int(args.func(args))

if __name__ == "__main__": sys.exit(main())
