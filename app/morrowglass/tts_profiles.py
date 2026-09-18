from __future__ import annotations

import os
from pathlib import Path


WINDOWS_EN_CANDIDATES = (
    Path(r"C:\MorrowglassTTS\venv\Scripts\python.exe"),
)

WINDOWS_VI_CANDIDATES = (
    Path(r"D:\Kokoro-Vietnamese\venv\Scripts\python.exe"),
)


def _first_existing(
    candidates: tuple[Path, ...],
) -> str:
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return ""


def default_kokoro_en_python() -> str:
    configured = (
        os.getenv(
            "MORROWGLASS_KOKORO_EN_PYTHON",
            "",
        ).strip()
        or os.getenv(
            "MORROWGLASS_KOKORO_PYTHON",
            "",
        ).strip()
    )
    if configured:
        return configured
    return _first_existing(
        WINDOWS_EN_CANDIDATES
    )


def default_kokoro_vi_python() -> str:
    configured = os.getenv(
        "MORROWGLASS_KOKORO_VI_PYTHON",
        "",
    ).strip()
    if configured:
        return configured
    return _first_existing(
        WINDOWS_VI_CANDIDATES
    )
