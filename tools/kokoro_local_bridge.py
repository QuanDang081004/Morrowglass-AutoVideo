from __future__ import annotations

import argparse
from pathlib import Path
import wave

import numpy as np


SAMPLE_RATE = 24000
SUPPORTED_LANG_CODES = {
    "a",
    "b",
    "e",
    "f",
    "h",
    "i",
    "j",
    "p",
    "z",
}


def _to_numpy(audio) -> np.ndarray:
    if hasattr(audio, "detach"):
        audio = audio.detach()
    if hasattr(audio, "cpu"):
        audio = audio.cpu()
    if hasattr(audio, "numpy"):
        audio = audio.numpy()
    return np.asarray(
        audio,
        dtype=np.float32,
    ).reshape(-1)


def _write_pcm16_wav(
    path: Path,
    audio: np.ndarray,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    clipped = np.clip(
        audio,
        -1.0,
        1.0,
    )
    pcm = (
        clipped * 32767.0
    ).astype(np.int16)
    with wave.open(
        str(path),
        "wb",
    ) as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(
            SAMPLE_RATE
        )
        handle.writeframes(
            pcm.tobytes()
        )


def synthesize_english(
    *,
    text: str,
    output: Path,
    voice: str,
    lang: str = "auto",
    speed: float = 1.0,
) -> None:
    from kokoro import KPipeline

    if lang == "auto":
        candidate = (
            voice[0].lower()
            if voice
            else "a"
        )
        lang = (
            candidate
            if candidate
            in SUPPORTED_LANG_CODES
            else "a"
        )

    pipeline = KPipeline(
        lang_code=lang,
    )
    chunks: list[np.ndarray] = []
    generator = pipeline(
        text,
        voice=voice,
        speed=float(speed),
    )
    for result in generator:
        if hasattr(result, "audio"):
            audio = result.audio
        else:
            audio = result[2]
        if audio is None:
            continue
        array = _to_numpy(audio)
        if array.size:
            chunks.append(array)

    if not chunks:
        raise RuntimeError(
            "English Kokoro produced no audio"
        )

    _write_pcm16_wav(
        output,
        np.concatenate(chunks),
    )


def synthesize_vietnamese(
    *,
    text: str,
    output: Path,
    voice: str,
    device: str = "cpu",
) -> None:
    from kokoro_vietnamese import KokoroVietnamese

    tts = KokoroVietnamese(
        device=device,
        voice=voice,
    )
    audio, _phonemes = tts.synthesize(
        text
    )
    array = _to_numpy(audio)
    if not array.size:
        raise RuntimeError(
            "Vietnamese Kokoro produced no audio"
        )

    _write_pcm16_wav(
        output,
        array,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a WAV file with an existing "
            "English or Vietnamese Kokoro environment"
        )
    )
    parser.add_argument(
        "--engine",
        choices=["english", "vietnamese"],
        default="english",
    )
    parser.add_argument(
        "--text-file",
        required=True,
    )
    parser.add_argument(
        "--output",
        required=True,
    )
    parser.add_argument(
        "--voice",
        required=True,
    )
    parser.add_argument(
        "--lang",
        default="auto",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--device",
        default="cpu",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    text = Path(
        args.text_file
    ).read_text(
        encoding="utf-8-sig"
    ).strip()
    if not text:
        raise ValueError(
            "text file is empty"
        )

    output = Path(args.output)
    if args.engine == "vietnamese":
        synthesize_vietnamese(
            text=text,
            output=output,
            voice=args.voice,
            device=args.device,
        )
    else:
        synthesize_english(
            text=text,
            output=output,
            voice=args.voice,
            lang=args.lang,
            speed=args.speed,
        )

    print(
        f"Kokoro audio: {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
