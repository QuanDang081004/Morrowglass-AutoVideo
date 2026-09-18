from __future__ import annotations

from pathlib import Path


def synthesize_narration(project, project_dir: str | Path, *, voice_name: str | None = None, voice_rate: float = 1.0, voice_volume: float = 1.0) -> tuple[Path, float]:
    """Generate narration with MoneyPrinterTurbo's existing TTS stack.

    Kokoro works when voice_name uses the existing MPT prefix, e.g. kokoro:am_michael.
    """
    from app.services import voice

    project_dir = Path(project_dir)
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    output = audio_dir / "narration.mp3"
    selected_voice = voice_name or project.voice_name
    sub_maker = voice.tts(
        text=project.script,
        voice_name=voice.parse_voice_name(selected_voice),
        voice_rate=voice_rate,
        voice_file=str(output),
        voice_volume=voice_volume,
    )
    if sub_maker is None or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("failed to synthesize narration")
    duration = float(voice.get_audio_duration(str(output)))
    if duration <= 0:
        raise RuntimeError("generated narration has zero duration")
    project.voice_name = selected_voice
    project.metadata["audio_file"] = str(output.resolve())
    project.metadata["audio_duration"] = duration
    return output, duration


def transcribe_word_timing(project, project_dir: str | Path, audio_file: str | Path) -> Path:
    """Create word-level SRT through MPT's faster-whisper service."""
    from app.services import subtitle

    project_dir = Path(project_dir)
    subtitle_dir = project_dir / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    output = subtitle_dir / "words.srt"
    result = subtitle.create(str(audio_file), str(output), word_level=True)
    if result is None and not output.is_file():
        raise RuntimeError("Whisper failed to create word timing")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Whisper did not produce word timing")
    project.metadata["word_subtitle_file"] = str(output.resolve())
    return output
