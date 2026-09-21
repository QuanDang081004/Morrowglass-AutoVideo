from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.morrowglass.audio import (  # noqa: E402
    ENGLISH_KOKORO_VOICES,
    VIETNAMESE_KOKORO_VOICES,
    narration_fingerprint,
    synthesize_narration,
)
from app.morrowglass.assets import (  # noqa: E402
    missing_scene_ids,
    resolve_assets,
)
from app.morrowglass.comfyui import (  # noqa: E402
    default_base_url,
    default_image_workflow,
    default_video_workflow,
)
from app.morrowglass.generators import (  # noqa: E402
    ImageGenerationUnavailable,
    VideoGenerationUnavailable,
)
from app.morrowglass.models import (  # noqa: E402
    AssetMode,
    MorrowglassProject,
    VisualBible,
)
from app.morrowglass.pipeline import (  # noqa: E402
    MorrowglassPipeline,
)
from app.morrowglass.qc import (  # noqa: E402
    duplicate_scene_asset_groups,
    duplicate_scene_ids,
)
from app.morrowglass.timeline import TIMELINE_VERSION  # noqa: E402
from app.morrowglass.tts_profiles import (  # noqa: E402
    default_kokoro_en_python as detect_kokoro_en_python,
    default_kokoro_vi_python as detect_kokoro_vi_python,
)
from app.services import llm  # noqa: E402


IMAGE_EXTS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
}
VIDEO_EXTS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".gif",
}


def _llm_call(prompt: str) -> str:
    return llm._generate_response(prompt)


def _external_ai_enabled() -> bool:
    return os.getenv(
        "MORROWGLASS_ALLOW_PAID_PROVIDERS",
        "",
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _pipeline(
    use_llm: bool = True,
) -> MorrowglassPipeline:
    allow_external = (
        use_llm
        and _external_ai_enabled()
    )
    return MorrowglassPipeline(
        llm_call=(
            _llm_call
            if allow_external
            else None
        )
    )


def _apply_pending_project_switch(
    state,
    *,
    default_project: str,
) -> None:
    pending = state.pop(
        "morrowglass_pending_project_folder",
        None,
    )
    if (
        "morrowglass_project_folder"
        not in state
    ):
        state[
            "morrowglass_project_folder"
        ] = default_project
    if pending:
        state[
            "morrowglass_project_folder"
        ] = str(pending)


def _queue_project_switch(
    project_folder: str,
) -> None:
    st.session_state[
        "morrowglass_pending_project_folder"
    ] = str(project_folder)


def _manifest(
    project_dir: Path,
) -> Path:
    return project_dir / "project.json"


def _load_project(
    project_dir: Path,
) -> MorrowglassProject | None:
    manifest = _manifest(project_dir)
    if not manifest.is_file():
        return None
    return MorrowglassProject.load(manifest)


def _project_rows(
    project: MorrowglassProject,
) -> list[dict]:
    rows = []
    for scene in project.scenes:
        asset = (
            Path(scene.asset_path).name
            if scene.asset_path
            else ""
        )
        rows.append(
            {
                "scene": scene.scene_id,
                "type": scene.asset_type.value,
                "start": (
                    round(scene.start, 2)
                    if scene.start is not None
                    else None
                ),
                "end": (
                    round(scene.end, 2)
                    if scene.end is not None
                    else None
                ),
                "duration": (
                    round(scene.duration, 2)
                    if scene.duration is not None
                    else None
                ),
                "asset": asset,
                "qc_score": scene.qc_score,
                "narration": scene.narration,
            }
        )
    return rows


def _delete_scene_assets(
    project_dir: Path,
    scene_id: str,
) -> None:
    for folder_name in (
        "images",
        "videos",
    ):
        folder = project_dir / folder_name
        if not folder.exists():
            continue
        for candidate in folder.glob(
            f"{scene_id}.*"
        ):
            if candidate.is_file():
                candidate.unlink()


def _clear_scene_asset_state(
    project: MorrowglassProject,
    project_dir: Path,
    scene_ids: list[str] | set[str],
) -> None:
    targets = set(scene_ids)
    for scene in project.scenes:
        if scene.scene_id not in targets:
            continue
        _delete_scene_assets(
            project_dir,
            scene.scene_id,
        )
        scene.asset_path = ""

    for metadata_key in (
        "asset_sources",
        "asset_hashes",
        "video_sources",
    ):
        mapping = project.metadata.get(
            metadata_key
        )
        if isinstance(mapping, dict):
            for scene_id in targets:
                mapping.pop(
                    scene_id,
                    None,
                )
            project.metadata[
                metadata_key
            ] = mapping

    project.metadata[
        "image_generation_failures"
    ] = [
        scene_id
        for scene_id in (
            project.metadata.get(
                "image_generation_failures"
            )
            or []
        )
        if scene_id not in targets
    ]
    project.metadata[
        "video_generation_failures"
    ] = [
        scene_id
        for scene_id in (
            project.metadata.get(
                "video_generation_failures"
            )
            or []
        )
        if scene_id not in targets
    ]
    project.save(
        _manifest(
            project_dir
        )
    )


def _save_uploaded_asset(
    project_dir: Path,
    scene_id: str,
    uploaded,
) -> Path:
    suffix = Path(
        uploaded.name
    ).suffix.lower()
    if suffix in IMAGE_EXTS:
        folder = project_dir / "images"
    elif suffix in VIDEO_EXTS:
        folder = project_dir / "videos"
    else:
        raise ValueError(
            "Use PNG/JPG/WEBP/BMP or "
            "MP4/MOV/MKV/WEBM/GIF."
        )

    _delete_scene_assets(
        project_dir,
        scene_id,
    )
    folder.mkdir(
        parents=True,
        exist_ok=True,
    )
    target = folder / f"{scene_id}{suffix}"
    target.write_bytes(uploaded.getvalue())
    return target


def _batch_asset_assignments(
    project: MorrowglassProject,
    uploads,
) -> tuple[list[tuple[str, object]], list[str]]:
    scene_ids = {
        scene.scene_id
        for scene in project.scenes
    }
    missing = [
        scene.scene_id
        for scene in project.scenes
        if not scene.asset_path
    ]

    assignments: list[
        tuple[str, object]
    ] = []
    unmatched = []
    used: set[str] = set()

    for uploaded in uploads:
        stem = Path(
            uploaded.name
        ).stem.lower()
        match = re.search(
            r"scene[_ -]?(\d+)",
            stem,
        )
        scene_id = ""
        if match:
            scene_id = (
                f"scene_{int(match.group(1)):03d}"
            )
        if (
            scene_id
            and scene_id in scene_ids
            and scene_id not in used
        ):
            assignments.append(
                (scene_id, uploaded)
            )
            used.add(scene_id)
        else:
            unmatched.append(uploaded)

    remaining = [
        scene_id
        for scene_id in missing
        if scene_id not in used
    ]
    if (
        unmatched
        and len(unmatched)
        == len(remaining)
    ):
        assignments.extend(
            zip(
                remaining,
                unmatched,
            )
        )
        unmatched = []

    return (
        assignments,
        [
            item.name
            for item in unmatched
        ],
    )


def _ensure_audio_timeline(
    project: MorrowglassProject,
    project_dir: Path,
    *,
    voice_name: str,
    voice_rate: float,
    voice_volume: float,
    kokoro_en_python: str,
    kokoro_vi_python: str,
    kokoro_vi_device: str,
) -> MorrowglassProject:
    audio_file = Path(
        str(
            project.metadata.get(
                "audio_file"
            )
            or ""
        )
    )
    timing_file = Path(
        str(
            project.metadata.get(
                "word_subtitle_file"
            )
            or ""
        )
    )
    expected_fingerprint = (
        narration_fingerprint(
            project,
            voice_name=voice_name or None,
            voice_rate=voice_rate,
            voice_volume=voice_volume,
            kokoro_en_python=(
                kokoro_en_python
                or None
            ),
            kokoro_vi_python=(
                kokoro_vi_python
                or None
            ),
            kokoro_vi_device=(
                kokoro_vi_device
            ),
        )
    )
    if (
        audio_file.is_file()
        and timing_file.is_file()
        and project.metadata.get(
            "tts_fingerprint"
        )
        == expected_fingerprint
        and project.metadata.get(
            "timeline_version"
        )
        == TIMELINE_VERSION
        and all(
            scene.start is not None
            and scene.end is not None
            for scene in project.scenes
        )
    ):
        return project

    return _pipeline(
        False
    ).build_audio_timeline(
        project,
        project_dir,
        voice_name=voice_name or None,
        voice_rate=voice_rate,
        voice_volume=voice_volume,
        kokoro_en_python=kokoro_en_python or None,
        kokoro_vi_python=kokoro_vi_python or None,
        kokoro_vi_device=kokoro_vi_device,
    )


def _auto_images(
    project: MorrowglassProject,
    project_dir: Path,
    *,
    overwrite: bool = False,
    attempts: int,
    min_qc_score: float,
    semantic_qc: bool,
    provider: str,
    comfyui_url: str,
    comfyui_image_workflow: str,
) -> list[str]:
    return _pipeline(
        False
    ).auto_generate_images(
        project,
        project_dir,
        overwrite=overwrite,
        semantic_qc=semantic_qc,
        min_qc_score=min_qc_score,
        max_attempts=attempts,
        provider=provider,
        comfyui_url=comfyui_url or None,
        comfyui_workflow=(
            comfyui_image_workflow
            or None
        ),
    )


def _auto_videos(
    project: MorrowglassProject,
    project_dir: Path,
    *,
    comfyui_url: str,
    comfyui_video_workflow: str,
) -> list[str]:
    return _pipeline(
        False
    ).auto_generate_videos(
        project,
        project_dir,
        comfyui_url=comfyui_url or None,
        comfyui_workflow=(
            comfyui_video_workflow
            or None
        ),
    )


def _save_ui_settings(
    project: MorrowglassProject,
    manifest: Path,
    *,
    asset_mode: str,
    aspect: str,
    voice_name: str,
    voice_rate: float,
    voice_volume: float,
    kokoro_en_python: str,
    kokoro_vi_python: str,
    kokoro_vi_device: str,
    image_provider: str,
    comfyui_url: str,
    comfyui_image_workflow: str,
    comfyui_video_workflow: str,
    auto_videos: bool,
) -> None:
    project.asset_mode = AssetMode(
        asset_mode
    )
    project.set_aspect(aspect)
    project.voice_name = voice_name
    project.metadata[
        "voice_rate"
    ] = float(voice_rate)
    project.metadata[
        "voice_volume"
    ] = float(voice_volume)
    project.metadata[
        "kokoro_en_python"
    ] = kokoro_en_python
    project.metadata[
        "kokoro_vi_python"
    ] = kokoro_vi_python
    project.metadata[
        "kokoro_vi_device"
    ] = kokoro_vi_device
    project.metadata[
        "preferred_image_provider"
    ] = image_provider
    project.metadata[
        "preferred_comfyui_url"
    ] = comfyui_url
    project.metadata[
        "preferred_comfyui_image_workflow"
    ] = comfyui_image_workflow
    project.metadata[
        "preferred_comfyui_video_workflow"
    ] = comfyui_video_workflow
    project.metadata[
        "auto_videos"
    ] = bool(auto_videos)
    project.save(manifest)


st.set_page_config(
    page_title="Morrowglass AutoVideo",
    page_icon="🎬",
    layout="wide",
)
st.title("Morrowglass AutoVideo")
st.caption(
    "Paste script → scene plan → Kokoro → Whisper → "
    "strict image research → manual AI fill-in → final MP4"
)
if not _external_ai_enabled():
    st.success(
        "FREE-ONLY mode is ON — paid/external AI providers "
        "are blocked by default."
    )

default_project = str(
    ROOT
    / "storage"
    / "morrowglass"
    / "video-001"
)
projects_root = (
    ROOT
    / "storage"
    / "morrowglass"
)
projects_root.mkdir(
    parents=True,
    exist_ok=True,
)

_apply_pending_project_switch(
    st.session_state,
    default_project=default_project,
)

recent_projects = [
    item
    for item in sorted(
        projects_root.iterdir(),
        key=lambda path: (
            path.stat().st_mtime
            if path.exists()
            else 0
        ),
        reverse=True,
    )
    if (
        item.is_dir()
        and (item / "project.json").is_file()
    )
]

load_cols = st.columns(
    [3, 1]
)
with load_cols[0]:
    project_folder_value = st.text_input(
        "Project folder",
        key="morrowglass_project_folder",
    )
with load_cols[1]:
    load_clicked = st.button(
        "Load project",
        use_container_width=True,
    )

if recent_projects:
    current_value = str(
        st.session_state[
            "morrowglass_project_folder"
        ]
    )
    recent_labels = [
        str(item)
        for item in recent_projects
    ]
    recent_default = (
        recent_labels.index(
            current_value
        )
        if current_value in recent_labels
        else 0
    )
    recent_project = st.selectbox(
        "Recent projects",
        options=recent_labels,
        index=recent_default,
        help=(
            "Choose a saved project, then click Load project."
        ),
    )
    st.button(
        "Load selected recent project",
        use_container_width=True,
        on_click=_queue_project_switch,
        args=(recent_project,),
    )

project_dir = Path(
    str(
        project_folder_value
    )
).expanduser()
manifest = _manifest(
    project_dir
)
project = _load_project(
    project_dir
)

if load_clicked:
    if manifest.is_file():
        st.success(
            f"Loaded project: {project_dir.name}"
        )
        st.rerun()
    else:
        st.error(
            "No project.json found in this folder: "
            f"{project_dir}"
        )

stored = (
    project.metadata
    if project
    else {}
)
stored_image_provider = str(
    stored.get(
        "preferred_image_provider",
        "auto",
    )
)
if stored_image_provider not in {
    "auto",
    "wikimedia",
}:
    stored_image_provider = "auto"

default_image_workflow_path = (
    str(
        stored.get(
            "preferred_comfyui_image_workflow",
            "",
        )
        or ""
    )
)
if not default_image_workflow_path:
    detected = default_image_workflow(
        project_dir
    )
    if detected:
        default_image_workflow_path = str(
            detected
        )

default_video_workflow_path = (
    str(
        stored.get(
            "preferred_comfyui_video_workflow",
            "",
        )
        or ""
    )
)
if not default_video_workflow_path:
    detected = default_video_workflow(
        project_dir
    )
    if detected:
        default_video_workflow_path = str(
            detected
        )

default_kokoro_en_python = str(
    stored.get(
        "kokoro_en_python",
        "",
    )
    or stored.get(
        "kokoro_python",
        "",
    )
    or detect_kokoro_en_python()
)
default_kokoro_vi_python = str(
    stored.get(
        "kokoro_vi_python",
        "",
    )
    or detect_kokoro_vi_python()
)
default_voice_rate = float(
    stored.get(
        "voice_rate",
        1.0,
    )
)
default_voice_volume = float(
    stored.get(
        "voice_volume",
        1.0,
    )
)

default_comfyui_url = str(
    stored.get(
        "preferred_comfyui_url",
        "",
    )
    or default_base_url()
)

with st.sidebar:
    st.header("Project settings")
    title = st.text_input(
        "Video title",
        value=(
            project.title
            if project
            else "Morrowglass Video"
        ),
    )
    period = st.text_input(
        "Historical period",
        value=(
            project.visual_bible.period
            if project
            else ""
        ),
        help=(
            "Optional. Leave blank and "
            "the Scene Director will infer it."
        ),
    )
    location = st.text_input(
        "Location",
        value=(
            project.visual_bible.location
            if project
            else ""
        ),
        help=(
            "Optional. Leave blank and "
            "the Scene Director will infer it."
        ),
    )
    aspect_options = [
        "16:9",
        "9:16",
    ]
    current_aspect = (
        project.aspect
        if project
        else "16:9"
    )
    if current_aspect not in aspect_options:
        current_aspect = "16:9"
    output_aspect = st.selectbox(
        "Output format",
        options=aspect_options,
        index=aspect_options.index(
            current_aspect
        ),
        format_func=lambda value: (
            "Horizontal 16:9 — YouTube"
            if value == "16:9"
            else "Vertical 9:16 — Shorts/TikTok"
        ),
        help=(
            "This controls planning, generation framing, "
            "scene rendering, subtitles, and final resolution."
        ),
    )
    asset_mode_value = st.selectbox(
        "Asset mode",
        options=[
            mode.value
            for mode in AssetMode
        ],
        index=(
            [
                mode.value
                for mode in AssetMode
            ].index(
                project.asset_mode.value
            )
            if project
            else 0
        ),
    )
    current_voice = (
        project.voice_name
        if project
        else "kokoro-en:am_michael"
    )
    if current_voice.startswith("kokoro-vi:"):
        default_tts_engine = "Kokoro Vietnamese"
    elif (
        current_voice.startswith("kokoro-en:")
        or current_voice.startswith("kokoro-local:")
    ):
        default_tts_engine = "Kokoro English"
    else:
        default_tts_engine = (
            "MPT / other"
            if _external_ai_enabled()
            else "Kokoro English"
        )

    tts_engines = [
        "Kokoro English",
        "Kokoro Vietnamese",
    ]
    if _external_ai_enabled():
        tts_engines.append(
            "MPT / other"
        )
    tts_engine = st.selectbox(
        "TTS engine",
        options=tts_engines,
        index=tts_engines.index(
            default_tts_engine
        ),
    )

    if tts_engine == "Kokoro Vietnamese":
        current_vi_voice = (
            current_voice.split(":", 1)[1]
            if current_voice.startswith("kokoro-vi:")
            else "manh_dung"
        )
        if current_vi_voice not in VIETNAMESE_KOKORO_VOICES:
            current_vi_voice = "manh_dung"
        vi_voice = st.selectbox(
            "Vietnamese voice",
            options=list(
                VIETNAMESE_KOKORO_VOICES
            ),
            index=list(
                VIETNAMESE_KOKORO_VOICES
            ).index(
                current_vi_voice
            ),
        )
        voice_name = f"kokoro-vi:{vi_voice}"
    elif tts_engine == "Kokoro English":
        current_en_voice = (
            current_voice.split(":", 1)[1]
            if (
                current_voice.startswith("kokoro-en:")
                or current_voice.startswith("kokoro-local:")
            )
            else "am_michael"
        )
        if current_en_voice not in ENGLISH_KOKORO_VOICES:
            current_en_voice = "am_michael"

        def _english_voice_label(voice_id: str) -> str:
            prefix, _, name = voice_id.partition("_")
            accent = (
                "American"
                if prefix.startswith("a")
                else "British"
            )
            gender = (
                "Female"
                if prefix.endswith("f")
                else "Male"
            )
            display_name = name.replace("_", " ").title()
            return (
                f"{accent} {gender} — "
                f"{display_name} ({voice_id})"
            )

        en_voice = st.selectbox(
            "English voice",
            options=list(
                ENGLISH_KOKORO_VOICES
            ),
            index=list(
                ENGLISH_KOKORO_VOICES
            ).index(
                current_en_voice
            ),
            format_func=_english_voice_label,
            help=(
                "Official English voices from Kokoro-82M. "
                "af/am = American female/male; "
                "bf/bm = British female/male."
            ),
        )
        voice_name = f"kokoro-en:{en_voice}"
    else:
        voice_name = st.text_input(
            "MPT voice",
            value=(
                current_voice
                if default_tts_engine == "MPT / other"
                else ""
            ),
        )

    kokoro_en_python = st.text_input(
        "English Kokoro Python",
        value=default_kokoro_en_python,
        placeholder=(
            r"C:\MorrowglassTTS\venv\Scripts\python.exe"
        ),
    )
    kokoro_vi_python = st.text_input(
        "Vietnamese Kokoro Python",
        value=default_kokoro_vi_python,
        placeholder=(
            r"D:\Kokoro-Vietnamese\venv\Scripts\python.exe"
        ),
    )
    kokoro_vi_device = st.selectbox(
        "Vietnamese Kokoro device",
        options=["cpu", "cuda"],
        index=0,
        help=(
            "Use cpu on the current Intel Iris Xe machine."
        ),
    )
    voice_rate = st.slider(
        "Voice speed",
        min_value=0.75,
        max_value=1.25,
        value=min(
            1.25,
            max(
                0.75,
                default_voice_rate,
            ),
        ),
        step=0.05,
    )
    voice_volume = st.slider(
        "Voice volume",
        min_value=0.50,
        max_value=1.50,
        value=min(
            1.50,
            max(
                0.50,
                default_voice_volume,
            ),
        ),
        step=0.05,
    )

    preview_default = (
        "Ngày xưa, có những câu chuyện lịch sử "
        "khiến người ta phải nhìn lại quá khứ."
        if tts_engine == "Kokoro Vietnamese"
        else (
            "Somewhere beyond the village, "
            "a forgotten story is waiting to be told."
        )
    )
    preview_text = st.text_area(
        "Voice preview text",
        value=preview_default,
        height=90,
    )
    if st.button(
        "▶ Preview voice",
        use_container_width=True,
    ):
        if not preview_text.strip():
            st.warning(
                "Enter preview text first."
            )
        else:
            try:
                with st.spinner(
                    "Generating voice preview..."
                ):
                    with tempfile.TemporaryDirectory() as directory:
                        preview_project = MorrowglassProject(
                            title="Voice Preview",
                            script=preview_text.strip(),
                            scenes=[],
                            voice_name=voice_name,
                        )
                        preview_audio, _duration = (
                            synthesize_narration(
                                preview_project,
                                directory,
                                voice_name=voice_name,
                                voice_rate=voice_rate,
                                voice_volume=voice_volume,
                                kokoro_en_python=(
                                    kokoro_en_python
                                    or None
                                ),
                                kokoro_vi_python=(
                                    kokoro_vi_python
                                    or None
                                ),
                                kokoro_vi_device=(
                                    kokoro_vi_device
                                ),
                            )
                        )
                        audio_bytes = (
                            preview_audio.read_bytes()
                        )
                        audio_format = (
                            "audio/wav"
                            if preview_audio.suffix.lower()
                            == ".wav"
                            else "audio/mpeg"
                        )
                st.audio(
                    audio_bytes,
                    format=audio_format,
                )
            except Exception as exc:
                st.error(
                    f"Voice preview failed: {exc}"
                )

    st.divider()
    st.subheader("Image research")
    image_provider_options = [
        "auto",
        "wikimedia",
    ]
    image_provider = st.selectbox(
        "Image provider",
        options=image_provider_options,
        index=image_provider_options.index(
            stored_image_provider
        ),
        help=(
            "AUTO is research-only: Wikimedia Commons → Openverse → The Met. "
            "Weak matches are rejected and exported to MANUAL_IMAGES.md. "
            "AI image generation is never invoked by this workflow."
        ),
    )
    # Image generation is intentionally outside the normal WebUI flow.
    # Keep the saved value for backward compatibility, but do not offer an
    # image-generation control that could bypass research-first behavior.
    comfyui_image_workflow = default_image_workflow_path

    st.caption(
        "AI image generation is manual: unresolved scenes are exported to "
        "prompts/MANUAL_IMAGES.md."
    )
    comfyui_url = st.text_input(
        "ComfyUI URL (optional motion video only)",
        value=default_comfyui_url,
    )
    comfyui_video_workflow = st.text_input(
        "Video workflow (optional motion video API JSON)",
        value=default_video_workflow_path,
        placeholder=(
            str(
                project_dir
                / "workflows"
                / "video.json"
            )
        ),
    )
    auto_videos = st.checkbox(
        "Animate motion scenes with ComfyUI",
        value=bool(
            stored.get(
                "auto_videos",
                False,
            )
        ),
        help=(
            "Only scenes marked image_to_video/"
            "video by the Scene Director are animated."
        ),
    )

    st.divider()
    st.subheader("Asset QC")
    image_attempts = st.slider(
        "Research attempts per scene",
        min_value=1,
        max_value=4,
        value=2,
    )
    min_qc_score = st.slider(
        "Semantic QC minimum",
        min_value=50,
        max_value=95,
        value=75,
    )
    semantic_qc = st.checkbox(
        "Use semantic vision QC when configured",
        value=True,
    )
    st.caption(
        "Without a vision model, technical "
        "image QC still runs."
    )

    st.divider()
    st.subheader("Render")
    bgm_path = st.text_input(
        "Optional BGM file",
        value="",
    )
    bgm_volume = st.slider(
        "BGM volume",
        min_value=0.0,
        max_value=0.5,
        value=0.12,
        step=0.01,
    )
    font_size = st.slider(
        "Subtitle font size",
        min_value=28,
        max_value=80,
        value=48,
    )
    image_motion = st.selectbox(
        "Still-image motion",
        options=[
            "slow_zoom",
            "none",
        ],
        index=0,
        help=(
            "slow_zoom adds subtle "
            "documentary-style motion."
        ),
    )

script_default = (
    project.script
    if project
    else ""
)
script = st.text_area(
    "Final narration script",
    value=script_default,
    height=320,
    placeholder=(
        "Paste the finished English "
        "history script here..."
    ),
)

action_cols = st.columns(5)
plan_clicked = action_cols[0].button(
    "1. Plan scenes",
    use_container_width=True,
)
voice_clicked = action_cols[1].button(
    "2. Voice + timing",
    use_container_width=True,
)
assets_clicked = action_cols[2].button(
    "3. Research images",
    use_container_width=True,
)
render_clicked = action_cols[3].button(
    "4. Render",
    use_container_width=True,
)
full_clicked = action_cols[4].button(
    "▶ Full run",
    type="primary",
    use_container_width=True,
)

regenerate_assets_clicked = st.button(
    "↻ Regenerate all assets",
    use_container_width=True,
    help=(
        "Delete existing scene images/videos and research them again. "
        "Unresolved scenes remain empty for manual AI generation. "
        "Narration and timing are preserved."
    ),
)

current_duplicate_ids = (
    duplicate_scene_ids(
        project
    )
    if project
    else []
)
regenerate_duplicates_clicked = st.button(
    "↻ Regenerate duplicate assets only",
    use_container_width=True,
    disabled=not bool(
        current_duplicate_ids
    ),
    help=(
        "Keep the earliest scene that uses an asset and rebuild "
        "only later scenes that duplicate the same source/image."
    ),
)

try:
    if plan_clicked:
        if not script.strip():
            st.error("Paste a script first.")
        else:
            project_dir.mkdir(
                parents=True,
                exist_ok=True,
            )
            (
                project_dir
                / "script.txt"
            ).write_text(
                script.strip() + "\n",
                encoding="utf-8",
            )
            project = _pipeline(
                True
            ).plan_project(
                script,
                project_dir,
                title=title,
                bible=VisualBible(
                    period=period,
                    location=location,
                ),
                asset_mode=AssetMode(
                    asset_mode_value
                ),
                aspect=output_aspect,
                use_llm=True,
            )
            _save_ui_settings(
                project,
                manifest,
                asset_mode=asset_mode_value,
                aspect=output_aspect,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_volume=voice_volume,
                kokoro_en_python=kokoro_en_python,
                kokoro_vi_python=kokoro_vi_python,
                kokoro_vi_device=kokoro_vi_device,
                image_provider=image_provider,
                comfyui_url=comfyui_url,
                comfyui_image_workflow=(
                    comfyui_image_workflow
                ),
                comfyui_video_workflow=(
                    comfyui_video_workflow
                ),
                auto_videos=auto_videos,
            )
            st.success(
                f"Planned "
                f"{len(project.scenes)} scenes."
            )

    if voice_clicked:
        project = _load_project(
            project_dir
        )
        if not project:
            st.error("Plan scenes first.")
        else:
            _save_ui_settings(
                project,
                manifest,
                asset_mode=asset_mode_value,
                aspect=output_aspect,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_volume=voice_volume,
                kokoro_en_python=kokoro_en_python,
                kokoro_vi_python=kokoro_vi_python,
                kokoro_vi_device=kokoro_vi_device,
                image_provider=image_provider,
                comfyui_url=comfyui_url,
                comfyui_image_workflow=(
                    comfyui_image_workflow
                ),
                comfyui_video_workflow=(
                    comfyui_video_workflow
                ),
                auto_videos=auto_videos,
            )
            with st.spinner(
                "Generating narration "
                "and Whisper timing..."
            ):
                project = _pipeline(
                    False
                ).build_audio_timeline(
                    project,
                    project_dir,
                    voice_name=(
                        voice_name
                        or None
                    ),
                    voice_rate=voice_rate,
                    voice_volume=voice_volume,
                    kokoro_en_python=(
                        kokoro_en_python
                        or None
                    ),
                    kokoro_vi_python=(
                        kokoro_vi_python
                        or None
                    ),
                    kokoro_vi_device=kokoro_vi_device,
                )
            st.success(
                "Narration and scene "
                "timing are ready."
            )

    if (
        assets_clicked
        or regenerate_assets_clicked
        or regenerate_duplicates_clicked
    ):
        project = _load_project(
            project_dir
        )
        if not project:
            st.error("Plan scenes first.")
        else:
            if regenerate_assets_clicked:
                _clear_scene_asset_state(
                    project,
                    project_dir,
                    [
                        scene.scene_id
                        for scene in project.scenes
                    ],
                )
                project = _load_project(
                    project_dir
                )
                st.info(
                    "Existing scene assets cleared. "
                    "Researching all scenes again..."
                )
            elif regenerate_duplicates_clicked:
                duplicate_targets = (
                    duplicate_scene_ids(
                        project
                    )
                )
                _clear_scene_asset_state(
                    project,
                    project_dir,
                    duplicate_targets,
                )
                project = _load_project(
                    project_dir
                )
                st.info(
                    "Rebuilding duplicate scenes only: "
                    + ", ".join(
                        duplicate_targets
                    )
                )

            _save_ui_settings(
                project,
                manifest,
                asset_mode=asset_mode_value,
                aspect=output_aspect,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_volume=voice_volume,
                kokoro_en_python=kokoro_en_python,
                kokoro_vi_python=kokoro_vi_python,
                kokoro_vi_device=kokoro_vi_device,
                image_provider=image_provider,
                comfyui_url=comfyui_url,
                comfyui_image_workflow=(
                    comfyui_image_workflow
                ),
                comfyui_video_workflow=(
                    comfyui_video_workflow
                ),
                auto_videos=auto_videos,
            )
            with st.spinner(
                "Researching and checking "
                "scene images..."
            ):
                failures = _auto_images(
                    project,
                    project_dir,
                    overwrite=(
                        regenerate_assets_clicked
                    ),
                    attempts=image_attempts,
                    min_qc_score=float(
                        min_qc_score
                    ),
                    semantic_qc=semantic_qc,
                    provider=image_provider,
                    comfyui_url=comfyui_url,
                    comfyui_image_workflow=(
                        comfyui_image_workflow
                    ),
                )
            if failures:
                st.warning(
                    "Some scenes still need "
                    "manual images: "
                    + ", ".join(failures)
                )
            else:
                st.success(
                    "All scene images are ready."
                )

            project = _load_project(
                project_dir
            )
            if auto_videos and project:
                with st.spinner(
                    "Animating motion scenes "
                    "with ComfyUI..."
                ):
                    video_failures = _auto_videos(
                        project,
                        project_dir,
                        comfyui_url=comfyui_url,
                        comfyui_video_workflow=(
                            comfyui_video_workflow
                        ),
                    )
                if video_failures:
                    st.warning(
                        "Video generation failed for "
                        "some scenes; their still "
                        "images remain usable: "
                        + ", ".join(
                            video_failures
                        )
                    )
                else:
                    st.success(
                        "Motion scenes are ready."
                    )

    if render_clicked:
        project = _load_project(
            project_dir
        )
        if not project:
            st.error("Plan scenes first.")
        else:
            _save_ui_settings(
                project,
                manifest,
                asset_mode=asset_mode_value,
                aspect=output_aspect,
                voice_name=voice_name,
                voice_rate=voice_rate,
                voice_volume=voice_volume,
                kokoro_en_python=kokoro_en_python,
                kokoro_vi_python=kokoro_vi_python,
                kokoro_vi_device=kokoro_vi_device,
                image_provider=image_provider,
                comfyui_url=comfyui_url,
                comfyui_image_workflow=(
                    comfyui_image_workflow
                ),
                comfyui_video_workflow=(
                    comfyui_video_workflow
                ),
                auto_videos=auto_videos,
            )
            with st.spinner(
                "Rendering final video..."
            ):
                final = _pipeline(
                    False
                ).render(
                    project,
                    project_dir,
                    bgm_file=(
                        bgm_path
                        or None
                    ),
                    bgm_volume=bgm_volume,
                    font_size=font_size,
                    image_motion=image_motion,
                )
            st.success(
                f"Final video: {final}"
            )
            st.video(str(final))

    if full_clicked:
        if (
            not script.strip()
            and not project
        ):
            st.error("Paste a script first.")
        else:
            with st.status(
                "Running Morrowglass pipeline...",
                expanded=True,
            ) as status:
                project = _load_project(
                    project_dir
                )
                if project:
                    _save_ui_settings(
                        project,
                        manifest,
                        asset_mode=(
                            asset_mode_value
                        ),
                        aspect=output_aspect,
                        voice_name=voice_name,
                        voice_rate=voice_rate,
                        voice_volume=voice_volume,
                        kokoro_en_python=kokoro_en_python,
                        kokoro_vi_python=kokoro_vi_python,
                        kokoro_vi_device=kokoro_vi_device,
                        image_provider=(
                            image_provider
                        ),
                        comfyui_url=(
                            comfyui_url
                        ),
                        comfyui_image_workflow=(
                            comfyui_image_workflow
                        ),
                        comfyui_video_workflow=(
                            comfyui_video_workflow
                        ),
                        auto_videos=(
                            auto_videos
                        ),
                    )

                if not project:
                    status.write(
                        "Planning scenes "
                        "and Visual Bible..."
                    )
                    project_dir.mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    (
                        project_dir
                        / "script.txt"
                    ).write_text(
                        script.strip()
                        + "\n",
                        encoding="utf-8",
                    )
                    project = _pipeline(
                        True
                    ).plan_project(
                        script,
                        project_dir,
                        title=title,
                        bible=VisualBible(
                            period=period,
                            location=location,
                        ),
                        asset_mode=AssetMode(
                            asset_mode_value
                        ),
                        aspect=output_aspect,
                        use_llm=True,
                    )
                    _save_ui_settings(
                        project,
                        manifest,
                        asset_mode=(
                            asset_mode_value
                        ),
                        aspect=output_aspect,
                        voice_name=voice_name,
                        voice_rate=voice_rate,
                        voice_volume=voice_volume,
                        kokoro_en_python=kokoro_en_python,
                        kokoro_vi_python=kokoro_vi_python,
                        kokoro_vi_device=kokoro_vi_device,
                        image_provider=(
                            image_provider
                        ),
                        comfyui_url=(
                            comfyui_url
                        ),
                        comfyui_image_workflow=(
                            comfyui_image_workflow
                        ),
                        comfyui_video_workflow=(
                            comfyui_video_workflow
                        ),
                        auto_videos=(
                            auto_videos
                        ),
                    )

                status.write(
                    "Preparing narration "
                    "and timing..."
                )
                project = _ensure_audio_timeline(
                    project,
                    project_dir,
                    voice_name=voice_name,
                    voice_rate=voice_rate,
                    voice_volume=voice_volume,
                    kokoro_en_python=kokoro_en_python,
                    kokoro_vi_python=kokoro_vi_python,
                    kokoro_vi_device=kokoro_vi_device,
                )

                missing = _pipeline(
                    False
                ).refresh_assets(
                    project,
                    project_dir,
                )
                if (
                    missing
                    and project.asset_mode
                    == AssetMode.AUTO
                ):
                    status.write(
                        "Researching archive images "
                        "for each scene..."
                    )
                    failures = _auto_images(
                        project,
                        project_dir,
                        attempts=image_attempts,
                        min_qc_score=float(
                            min_qc_score
                        ),
                        semantic_qc=semantic_qc,
                        provider=image_provider,
                        comfyui_url=comfyui_url,
                        comfyui_image_workflow=(
                            comfyui_image_workflow
                        ),
                    )
                    if failures:
                        status.write(
                            "Strict research could not safely resolve "
                            "every scene. Manual AI prompts were created for: "
                            + ", ".join(failures)
                        )
                    project = _load_project(
                        project_dir
                    )

                duplicate_targets = (
                    duplicate_scene_ids(
                        project
                    )
                    if project
                    else []
                )
                if (
                    duplicate_targets
                    and project
                    and project.asset_mode
                    == AssetMode.AUTO
                ):
                    status.write(
                        "Duplicate assets detected. "
                        "Rebuilding only later duplicate scenes: "
                        + ", ".join(
                            duplicate_targets
                        )
                    )
                    _clear_scene_asset_state(
                        project,
                        project_dir,
                        duplicate_targets,
                    )
                    project = _load_project(
                        project_dir
                    )
                    duplicate_failures = (
                        _auto_images(
                            project,
                            project_dir,
                            attempts=image_attempts,
                            min_qc_score=float(
                                min_qc_score
                            ),
                            semantic_qc=semantic_qc,
                            provider="auto",
                            comfyui_url=comfyui_url,
                            comfyui_image_workflow=(
                                comfyui_image_workflow
                            ),
                        )
                    )
                    if duplicate_failures:
                        status.write(
                            "Could not replace every duplicate scene: "
                            + ", ".join(
                                duplicate_failures
                            )
                        )
                    project = _load_project(
                        project_dir
                    )

                if (
                    auto_videos
                    and project
                ):
                    status.write(
                        "Animating motion scenes..."
                    )
                    video_failures = _auto_videos(
                        project,
                        project_dir,
                        comfyui_url=comfyui_url,
                        comfyui_video_workflow=(
                            comfyui_video_workflow
                        ),
                    )
                    if video_failures:
                        status.write(
                            "Some AI videos failed; "
                            "using still images for: "
                            + ", ".join(
                                video_failures
                            )
                        )
                    project = _load_project(
                        project_dir
                    )

                missing = _pipeline(
                    False
                ).refresh_assets(
                    project,
                    project_dir,
                )
                duplicate_groups = (
                    duplicate_scene_asset_groups(
                        project
                    )
                )
                if (
                    missing
                    or duplicate_groups
                ):
                    status.update(
                        label=(
                            "Research checkpoint: "
                            "manual images needed"
                        ),
                        state="complete",
                    )
                    if missing:
                        st.warning(
                            "Missing: "
                            + ", ".join(
                                missing
                            )
                        )
                    if duplicate_groups:
                        st.warning(
                            "Duplicate assets remain: "
                            + " | ".join(
                                ", ".join(
                                    group
                                )
                                for group in duplicate_groups
                            )
                        )
                    st.info(
                        "Research stopped safely instead of using weak visuals. "
                        "Create the missing images from prompts/MANUAL_IMAGES.md, "
                        "save them with the requested scene filenames, then run again."
                    )
                else:
                    status.write(
                        "Rendering final MP4..."
                    )
                    final = _pipeline(
                        False
                    ).render(
                        project,
                        project_dir,
                        bgm_file=(
                            bgm_path
                            or None
                        ),
                        bgm_volume=(
                            bgm_volume
                        ),
                        font_size=font_size,
                        image_motion=(
                            image_motion
                        ),
                    )
                    status.update(
                        label=(
                            "Morrowglass video "
                            "complete"
                        ),
                        state="complete",
                    )
                    st.success(
                        f"Final video: {final}"
                    )
                    st.video(str(final))

except (
    ImageGenerationUnavailable,
    VideoGenerationUnavailable,
) as exc:
    st.error(str(exc))
except Exception as exc:
    st.exception(exc)

project = _load_project(project_dir)
if project:
    resolve_assets(
        project,
        project_dir,
    )
    project.save(manifest)
    missing = missing_scene_ids(
        project
    )
    duplicate_groups = (
        duplicate_scene_asset_groups(
            project
        )
    )

    st.divider()
    if duplicate_groups:
        st.error(
            "Duplicate scene assets detected: "
            + " | ".join(
                ", ".join(group)
                for group in duplicate_groups
            )
            + ". AUTO should regenerate later duplicates before render."
        )
    left, right = st.columns(
        [2, 1]
    )
    with left:
        st.subheader(
            f"Scenes ({len(project.scenes)})"
        )
        st.dataframe(
            _project_rows(project),
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.metric(
            "Assets ready",
            (
                len(project.scenes)
                - len(missing)
            ),
        )
        st.metric(
            "Missing",
            len(missing),
        )
        rendered = project.metadata.get(
            "scene_clips_rendered"
        )
        reused = project.metadata.get(
            "scene_clips_reused"
        )
        if (
            rendered is not None
            or reused is not None
        ):
            st.caption(
                "Last render cache: "
                f"{rendered or 0} rebuilt / "
                f"{reused or 0} reused"
            )

        final_path = Path(
            str(
                project.metadata.get(
                    "final_video_file"
                )
                or ""
            )
        )
        if final_path.is_file():
            st.video(
                str(final_path)
            )

    if missing:
        st.subheader(
            "Manual AI fill-in"
        )
        st.caption(
            "Research could not safely resolve these scenes. Use "
            "prompts/MANUAL_IMAGES.md to generate the missing images, then "
            "upload them here. Files named scene_001.*, scene_002.* are "
            "matched automatically."
        )
        batch_uploads = st.file_uploader(
            "Batch upload missing scene assets",
            type=[
                "png",
                "jpg",
                "jpeg",
                "webp",
                "bmp",
                "mp4",
                "mov",
                "mkv",
                "webm",
                "gif",
            ],
            accept_multiple_files=True,
            key="batch_scene_assets",
        )
        if (
            batch_uploads
            and st.button(
                "Auto-match & save batch",
                use_container_width=True,
            )
        ):
            (
                assignments,
                unmatched_names,
            ) = _batch_asset_assignments(
                project,
                batch_uploads,
            )
            for (
                scene_id,
                uploaded,
            ) in assignments:
                _clear_scene_asset_state(
                    project,
                    project_dir,
                    [scene_id],
                )
                project = _load_project(
                    project_dir
                )
                _save_uploaded_asset(
                    project_dir,
                    scene_id,
                    uploaded,
                )
            resolve_assets(
                project,
                project_dir,
            )
            project.save(manifest)
            if unmatched_names:
                st.warning(
                    "Could not safely match: "
                    + ", ".join(
                        unmatched_names
                    )
                )
            if assignments:
                st.success(
                    f"Saved {len(assignments)} "
                    "scene assets."
                )
                st.rerun()

    st.subheader(
        "Scene review / replacement"
    )
    scene_ids = [
        scene.scene_id
        for scene in project.scenes
    ]
    selected_id = st.selectbox(
        "Scene",
        scene_ids,
    )
    selected = next(
        scene
        for scene in project.scenes
        if scene.scene_id
        == selected_id
    )

    scene_left, scene_right = (
        st.columns(2)
    )
    with scene_left:
        st.write("**Narration**")
        st.write(
            selected.narration
        )
        st.write(
            "**Expected visual**"
        )
        st.write(
            selected.visual_description
        )
        st.write(
            "**Generation prompt**"
        )
        st.code(
            selected.image_prompt
        )
        if selected.motion_prompt:
            st.write(
                "**Motion prompt**"
            )
            st.code(
                selected.motion_prompt
            )
        if selected.qc_notes:
            st.write("**QC notes**")
            for note in selected.qc_notes:
                st.caption(note)

    with scene_right:
        if selected.asset_path:
            selected_path = Path(
                selected.asset_path
            )
            if (
                selected_path.suffix.lower()
                in IMAGE_EXTS
            ):
                st.image(
                    str(selected_path),
                    use_container_width=True,
                )
            elif (
                selected_path.suffix.lower()
                in VIDEO_EXTS
            ):
                st.video(
                    str(selected_path)
                )
        else:
            st.info(
                "No asset for this "
                "scene yet."
            )

        uploaded = st.file_uploader(
            "Replace this scene asset",
            type=[
                "png",
                "jpg",
                "jpeg",
                "webp",
                "bmp",
                "mp4",
                "mov",
                "mkv",
                "webm",
                "gif",
            ],
            key=(
                f"asset_{selected_id}"
            ),
        )
        if (
            uploaded is not None
            and st.button(
                "Save replacement",
                key=(
                    f"save_{selected_id}"
                ),
            )
        ):
            _clear_scene_asset_state(
                project,
                project_dir,
                [selected_id],
            )
            saved = _save_uploaded_asset(
                project_dir,
                selected_id,
                uploaded,
            )
            project = _load_project(
                project_dir
            )
            resolve_assets(
                project,
                project_dir,
            )
            project.save(manifest)
            st.success(
                f"Saved: {saved}"
            )
            st.rerun()

    failures = project.metadata.get(
        "image_generation_failures"
    )
    if failures:
        st.warning(
            "Unresolved research scenes: "
            + ", ".join(failures)
        )

    video_failures = project.metadata.get(
        "video_generation_failures"
    )
    if video_failures:
        st.warning(
            "Video generation failures: "
            + ", ".join(
                video_failures
            )
        )

    vision_url = os.getenv(
        "MORROWGLASS_VISION_BASE_URL",
        "",
    )
    if vision_url:
        st.caption(
            "Semantic vision QC configured."
        )
