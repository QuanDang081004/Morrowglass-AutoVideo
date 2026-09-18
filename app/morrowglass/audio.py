from __future__ import annotations

import os
from pathlib import Path
import subprocess

from .tts_profiles import (
    default_kokoro_en_python,
    default_kokoro_vi_python,
)


KOKORO_EN_PREFIX = "kokoro-en:"
KOKORO_VI_PREFIX = "kokoro-vi:"
LEGACY_LOCAL_KOKORO_PREFIX = "kokoro-local:"

VIETNAMESE_KOKORO_VOICES = (
    "diem_trinh",
    "hung_thinh",
    "mai_linh",
    "mai_loan",
    "manh_dung",
    "my_yen",
    "ngoc_huyen",
    "phat_tai",
    "thanh_dat",
    "thuc_trinh",
    "tuan_ngoc",
    "storyvert",
    "duc_an",
    "duc_duy",
)


def local_kokoro_engine(
    voice_name: str | None,
) -> str | None:
    value = str(
        voice_name or ""
    ).strip()
    if value.startswith(
        KOKORO_VI_PREFIX
    ):
        return "vietnamese"
    if value.startswith(
        KOKORO_EN_PREFIX
    ) or value.startswith(
        LEGACY_LOCAL_KOKORO_PREFIX
    ):
        return "english"
    return None


def is_local_kokoro_voice(
    voice_name: str | None,
) -> bool:
    return local_kokoro_engine(
        voice_name
    ) is not None


def _local_kokoro_voice_id(
    voice_name: str,
) -> str:
    value = voice_name.split(
        ":",
        1,
    )[1].strip()
    if not value:
        raise ValueError(
            "local Kokoro voice id is empty"
        )
    return value


def _resolve_kokoro_python(
    value: str | Path | None,
    *,
    engine: str = "english",
    legacy_value: str | Path | None = None,
) -> Path:
    if engine == "vietnamese":
        env_name = (
            "MORROWGLASS_KOKORO_VI_PYTHON"
        )
    else:
        env_name = (
            "MORROWGLASS_KOKORO_EN_PYTHON"
        )

    detected_default = (
        default_kokoro_vi_python()
        if engine == "vietnamese"
        else default_kokoro_en_python()
    )
    configured = str(
        value
        or os.getenv(
            env_name,
            "",
        )
        or legacy_value
        or os.getenv(
            "MORROWGLASS_KOKORO_PYTHON",
            "",
        )
        or detected_default
    ).strip()
    if not configured:
        label = (
            "Vietnamese"
            if engine == "vietnamese"
            else "English"
        )
        raise FileNotFoundError(
            f"{label} Kokoro selected but no Python "
            "interpreter was configured. Set "
            f"{env_name} or choose the matching "
            "Kokoro Python path in the WebUI."
        )

    python_path = Path(
        configured
    ).expanduser()
    if not python_path.is_file():
        raise FileNotFoundError(
            "Configured Kokoro Python does not exist: "
            f"{python_path}"
        )
    return python_path


def _postprocess_local_audio(
    audio_file: Path,
    *,
    speed: float,
    volume: float,
    engine: str,
) -> None:
    filters: list[str] = []

    if abs(
        float(volume) - 1.0
    ) > 0.001:
        filters.append(
            f"volume={float(volume):.4f}"
        )

    if not filters:
        return

    from app.utils import utils

    temp_file = audio_file.with_name(
        f"{audio_file.stem}.processed.wav"
    )
    command = [
        utils.get_ffmpeg_binary(),
        "-y",
        "-i",
        str(audio_file),
        "-af",
        ",".join(filters),
        "-c:a",
        "pcm_s16le",
        str(temp_file),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
    )
    if result.returncode != 0:
        details = (
            result.stderr
            or result.stdout
            or ""
        ).strip()
        raise RuntimeError(
            "Kokoro audio post-processing "
            f"failed: {details[-3000:]}"
        )
    temp_file.replace(audio_file)


def _synthesize_local_kokoro(
    project,
    project_dir: Path,
    *,
    selected_voice: str,
    voice_rate: float,
    voice_volume: float,
    kokoro_python: str | Path | None,
    kokoro_en_python: str | Path | None,
    kokoro_vi_python: str | Path | None,
    kokoro_vi_device: str,
) -> Path:
    engine = local_kokoro_engine(
        selected_voice
    )
    if engine is None:
        raise ValueError(
            f"not a local Kokoro voice: {selected_voice}"
        )

    profile_python = (
        kokoro_vi_python
        if engine == "vietnamese"
        else kokoro_en_python
    )
    python_path = _resolve_kokoro_python(
        profile_python,
        engine=engine,
        legacy_value=kokoro_python,
    )

    repo_root = Path(
        __file__
    ).resolve().parents[2]
    bridge = (
        repo_root
        / "tools"
        / "kokoro_local_bridge.py"
    )
    if not bridge.is_file():
        raise FileNotFoundError(
            f"Kokoro bridge not found: {bridge}"
        )

    cache_dir = (
        project_dir
        / "cache"
        / "tts"
    )
    cache_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    text_file = (
        cache_dir
        / "narration.txt"
    )
    text_file.write_text(
        project.script.strip() + "\n",
        encoding="utf-8",
    )

    output = (
        project_dir
        / "audio"
        / "narration.wav"
    )
    command = [
        str(python_path),
        str(bridge),
        "--engine",
        engine,
        "--text-file",
        str(text_file),
        "--output",
        str(output),
        "--voice",
        _local_kokoro_voice_id(
            selected_voice
        ),
        "--speed",
        str(float(voice_rate)),
        "--device",
        (
            kokoro_vi_device
            if engine == "vietnamese"
            else "cpu"
        ),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=3600,
    )
    if result.returncode != 0:
        details = (
            result.stderr
            or result.stdout
            or ""
        ).strip()
        raise RuntimeError(
            "Local Kokoro failed: "
            f"{details[-4000:]}"
        )
    if (
        not output.is_file()
        or output.stat().st_size == 0
    ):
        raise RuntimeError(
            "Local Kokoro produced no audio file"
        )

    _postprocess_local_audio(
        output,
        speed=voice_rate,
        volume=voice_volume,
        engine=engine,
    )

    project.metadata[
        "kokoro_engine"
    ] = engine
    project.metadata[
        "kokoro_python"
    ] = str(
        python_path.resolve()
    )
    project.metadata[
        "tts_provider"
    ] = (
        f"kokoro-{engine}-local"
    )
    project.metadata[
        "voice_rate"
    ] = float(voice_rate)
    project.metadata[
        "voice_volume"
    ] = float(voice_volume)
    if engine == "vietnamese":
        project.metadata[
            "kokoro_vi_device"
        ] = kokoro_vi_device

    return output


def synthesize_narration(
    project,
    project_dir: str | Path,
    *,
    voice_name: str | None = None,
    voice_rate: float = 1.0,
    voice_volume: float = 1.0,
    kokoro_python: str | Path | None = None,
    kokoro_en_python: str | Path | None = None,
    kokoro_vi_python: str | Path | None = None,
    kokoro_vi_device: str = "cpu",
) -> tuple[Path, float]:
    """Generate narration using local Kokoro or MPT's TTS stack."""
    from app.services import voice

    project_dir = Path(
        project_dir
    )
    audio_dir = (
        project_dir
        / "audio"
    )
    audio_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    selected_voice = (
        voice_name
        or project.voice_name
    )

    if is_local_kokoro_voice(
        selected_voice
    ):
        output = _synthesize_local_kokoro(
            project,
            project_dir,
            selected_voice=selected_voice,
            voice_rate=voice_rate,
            voice_volume=voice_volume,
            kokoro_python=kokoro_python,
            kokoro_en_python=kokoro_en_python,
            kokoro_vi_python=kokoro_vi_python,
            kokoro_vi_device=kokoro_vi_device,
        )
    else:
        output = (
            audio_dir
            / "narration.mp3"
        )
        sub_maker = voice.tts(
            text=project.script,
            voice_name=voice.parse_voice_name(
                selected_voice
            ),
            voice_rate=voice_rate,
            voice_file=str(output),
            voice_volume=voice_volume,
        )
        if (
            sub_maker is None
            or not output.is_file()
            or output.stat().st_size == 0
        ):
            raise RuntimeError(
                "failed to synthesize narration"
            )
        project.metadata[
            "tts_provider"
        ] = "mpt"
        project.metadata[
            "voice_rate"
        ] = float(voice_rate)
        project.metadata[
            "voice_volume"
        ] = float(voice_volume)

    duration = float(
        voice.get_audio_duration(
            str(output)
        )
    )
    if duration <= 0:
        raise RuntimeError(
            "generated narration has zero duration"
        )

    project.voice_name = selected_voice
    project.metadata[
        "audio_file"
    ] = str(
        output.resolve()
    )
    project.metadata[
        "audio_duration"
    ] = duration
    return output, duration


def transcribe_word_timing(
    project,
    project_dir: str | Path,
    audio_file: str | Path,
) -> Path:
    """Create word-level SRT through MPT's faster-whisper service."""
    from app.services import subtitle

    project_dir = Path(
        project_dir
    )
    subtitle_dir = (
        project_dir
        / "subtitles"
    )
    subtitle_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    output = (
        subtitle_dir
        / "words.srt"
    )
    result = subtitle.create(
        str(audio_file),
        str(output),
        word_level=True,
    )
    if (
        result is None
        and not output.is_file()
    ):
        raise RuntimeError(
            "Whisper failed to create word timing"
        )
    if (
        not output.is_file()
        or output.stat().st_size == 0
    ):
        raise RuntimeError(
            "Whisper did not produce word timing"
        )
    project.metadata[
        "word_subtitle_file"
    ] = str(
        output.resolve()
    )
    return output
