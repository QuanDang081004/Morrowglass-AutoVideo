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


def cmd_plan(args) -> int:
    script_path = Path(args.script)
    script = script_path.read_text(encoding="utf-8-sig")
    bible = VisualBible(period=args.period or "", location=args.location or "")
    pipeline = MorrowglassPipeline(llm_call=None if args.no_llm else _mpt_llm_call)
    project = pipeline.plan_project(
        script,
        args.project_dir,
        title=args.title,
        bible=bible,
        asset_mode=AssetMode(args.asset_mode),
        use_llm=not args.no_llm,
    )
    print(f"Created {len(project.scenes)} scenes")
    print(f"Manifest: {Path(args.project_dir) / 'project.json'}")
    print(f"Prompts:  {Path(args.project_dir) / 'prompts'}")
    return 0


def cmd_status(args) -> int:
    manifest = Path(args.project_dir) / "project.json"
    project = MorrowglassProject.load(manifest)
    resolve_assets(project, args.project_dir)
    project.save(manifest)
    missing = missing_scene_ids(project)
    print(f"Scenes: {len(project.scenes)}")
    print(f"Ready assets: {len(project.scenes) - len(missing)}")
    print(f"Missing assets: {len(missing)}")
    if missing:
        print("Missing: " + ", ".join(missing))
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Morrowglass scene-aware automation layer")
    sub = p.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Turn a script into scene manifests and generation prompts")
    plan.add_argument("script", help="UTF-8 text file containing final narration script")
    plan.add_argument("--project-dir", required=True)
    plan.add_argument("--title", default="Morrowglass Video")
    plan.add_argument("--period", default="")
    plan.add_argument("--location", default="")
    plan.add_argument("--asset-mode", choices=[m.value for m in AssetMode], default="hybrid")
    plan.add_argument("--no-llm", action="store_true", help="Use deterministic sentence splitting")
    plan.set_defaults(func=cmd_plan)

    status = sub.add_parser("status", help="Check which scene assets are present")
    status.add_argument("--project-dir", required=True)
    status.set_defaults(func=cmd_status)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
