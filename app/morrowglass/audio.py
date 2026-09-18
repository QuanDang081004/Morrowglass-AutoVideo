from __future__ import annotations

import os
from pathlib import Path
import subprocess


LOCAL_KOKORO_PREFIX = "kokoro-local:"


def is_local_kokoro_voice(
    voice_name: str | None,
) -> bool:
    return str(
        voice_name or ""
    ).startswith(
        LOCAL_KOKORO_PREFIX
    )


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
) -> Path:
    configured = str(
        value
        or os.getenv(
            "MORROWGLASS_KOKORO_PYTHON",
            "",
        )
    ).strip()
    if not configured:
        raise FileNotFoundError(
            "Local Kokoro selected but no Python "
            "interpreter was configured. Set "
            "MORROWGLASS_KOKORO_PYTHON or choose "
            "the Kokoro Python path in the WebUI."
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


def _synthesize_local_kokoro(
    project,
    project_dir: Path,
    *,
    selected_voice: str,
    voice_rate: float,
    kokoro_python: str | Path | None,
) -> Path:
    python_path = _resolve_kokoro_python(
        kokoro_python
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

    project.metadata[
        "kokoro_python"
    ] = str(
        python_path.resolve()
    )
    project.metadata[
        "tts_provider"
    ] = "kokoro-local"
    return output


def synthesize_narration(
    project,
    project_dir: str | Path,
    *,
    voice_name: str | None = None,
    voice_rate: float = 1.0,
    voice_volume: float = 1.0,
    kokoro_python: str | Path | None = None,
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
            kokoro_python=kokoro_python,
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
