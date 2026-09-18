from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json


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
        "realistic anatomy, atmospheric lighting, 16:9 composition"
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
    asset_mode: AssetMode = AssetMode.HYBRID
    voice_name: str = "kokoro-en:am_michael"
    aspect: str = "16:9"
    resolution: tuple[int, int] = (1920, 1080)
    metadata: dict[str, Any] = field(default_factory=dict)

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
        resolution = tuple(raw.get("resolution", (1920, 1080)))
        return cls(
            title=raw.get("title", "Morrowglass Video"),
            script=raw.get("script", ""),
            scenes=scenes,
            visual_bible=bible,
            asset_mode=AssetMode(raw.get("asset_mode", AssetMode.HYBRID.value)),
            voice_name=raw.get("voice_name", "kokoro-en:am_michael"),
            aspect=raw.get("aspect", "16:9"),
            resolution=(int(resolution[0]), int(resolution[1])),
            metadata=raw.get("metadata") or {},
        )
