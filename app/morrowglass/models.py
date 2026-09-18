from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json


ASPECT_RESOLUTIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
}


def normalize_aspect(value: str | None) -> str:
    aspect = str(value or "16:9").strip()
    if aspect not in ASPECT_RESOLUTIONS:
        raise ValueError(
            "aspect must be 16:9 or 9:16"
        )
    return aspect


def resolution_for_aspect(
    value: str | None,
) -> tuple[int, int]:
    return ASPECT_RESOLUTIONS[
        normalize_aspect(value)
    ]


def aspect_composition(
    value: str | None,
) -> str:
    aspect = normalize_aspect(value)
    if aspect == "9:16":
        return (
            "vertical 9:16 composition, mobile-first framing, "
            "main subject kept inside the center safe area"
        )
    return (
        "horizontal 16:9 composition, cinematic widescreen framing"
    )


class AssetMode(str, Enum):
    AUTO = "auto"
    HYBRID = "hybrid"
    MANUAL = "manual"


class AssetType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    IMAGE_TO_VIDEO = "image_to_video"
    STOCK = "stock"
    MANUAL = "manual"


@dataclass(slots=True)
class VisualBible:
    style: str = (
        "cinematic historical documentary, photorealistic, natural muted colors, "
        "realistic anatomy, atmospheric lighting"
    )
    period: str = ""
    location: str = ""
    characters: dict[str, str] = field(default_factory=dict)
    historical_constraints: list[str] = field(default_factory=list)
    negative_prompt: str = (
        "modern objects, modern clothing, electricity, text, watermark, logo, "
        "deformed hands, extra fingers, duplicate people, anachronism"
    )


@dataclass(slots=True)
class Scene:
    scene_id: str
    narration: str
    visual_description: str
    image_prompt: str
    motion_prompt: str = ""
    asset_type: AssetType = AssetType.IMAGE
    historical_constraints: list[str] = field(default_factory=list)
    start: float | None = None
    end: float | None = None
    asset_path: str = ""
    qc_score: float | None = None
    qc_notes: list[str] = field(default_factory=list)
    search_query: str = ""

    @property
    def duration(self) -> float | None:
        if self.start is None or self.end is None:
            return None
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class MorrowglassProject:
    title: str
    script: str
    scenes: list[Scene]
    visual_bible: VisualBible = field(default_factory=VisualBible)
    asset_mode: AssetMode = AssetMode.AUTO
    voice_name: str = "kokoro-en:am_michael"
    aspect: str = "16:9"
    resolution: tuple[int, int] = (1920, 1080)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set_aspect(
        self,
        aspect: str,
    ) -> None:
        normalized = normalize_aspect(
            aspect
        )
        self.aspect = normalized
        self.resolution = (
            resolution_for_aspect(
                normalized
            )
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["asset_mode"] = self.asset_mode.value
        for scene in data["scenes"]:
            scene["asset_type"] = scene["asset_type"].value if isinstance(scene["asset_type"], AssetType) else scene["asset_type"]
        return data

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "MorrowglassProject":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        bible_raw = raw.get("visual_bible") or {}
        bible = VisualBible(**bible_raw)
        scenes = []
        for item in raw.get("scenes", []):
            item = dict(item)
            item["asset_type"] = AssetType(item.get("asset_type", AssetType.IMAGE.value))
            scenes.append(Scene(**item))
        aspect = normalize_aspect(
            raw.get("aspect", "16:9")
        )
        resolution = tuple(
            raw.get(
                "resolution",
                resolution_for_aspect(
                    aspect
                ),
            )
        )
        return cls(
            title=raw.get("title", "Morrowglass Video"),
            script=raw.get("script", ""),
            scenes=scenes,
            visual_bible=bible,
            asset_mode=AssetMode(raw.get("asset_mode", AssetMode.AUTO.value)),
            voice_name=raw.get("voice_name", "kokoro-en:am_michael"),
            aspect=aspect,
            resolution=(int(resolution[0]), int(resolution[1])),
            metadata=raw.get("metadata") or {},
        )
