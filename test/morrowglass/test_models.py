import tempfile
import unittest
from pathlib import Path

from app.morrowglass.models import (
    AssetMode,
    AssetType,
    MorrowglassProject,
    Scene,
    VisualBible,
)


class ProjectModelTests(unittest.TestCase):
    def test_vertical_aspect_retargets_resolution_and_prompt(self):
        project = MorrowglassProject(
            title="Vertical",
            script="A scene.",
            scenes=[
                Scene(
                    "scene_001",
                    "A scene.",
                    "visible scene",
                    "historical scene",
                )
            ],
        )
        project.set_aspect(
            "9:16"
        )
        self.assertEqual(
            project.aspect,
            "9:16",
        )
        self.assertEqual(
            project.resolution,
            (1080, 1920),
        )
        self.assertIn(
            "vertical 9:16 composition",
            project.visual_bible.style,
        )
        self.assertIn(
            "vertical 9:16 composition",
            project.scenes[0].image_prompt,
        )

    def test_project_json_roundtrip(self):
        project = MorrowglassProject(
            title="History",
            script="A historical sentence.",
            scenes=[
                Scene(
                    scene_id="scene_001",
                    narration="A historical sentence.",
                    visual_description="A visible historical scene",
                    image_prompt="historical scene prompt",
                    asset_type=AssetType.IMAGE_TO_VIDEO,
                    start=0.0,
                    end=4.25,
                    qc_score=88.0,
                )
            ],
            visual_bible=VisualBible(
                period="13th century",
                location="Japan",
            ),
            asset_mode=AssetMode.AUTO,
            voice_name="kokoro:am_michael",
        )
        project.metadata["audio_duration"] = 4.25

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            project.save(path)
            loaded = MorrowglassProject.load(path)

        self.assertEqual(loaded.asset_mode, AssetMode.AUTO)
        self.assertEqual(
            loaded.scenes[0].asset_type,
            AssetType.IMAGE_TO_VIDEO,
        )
        self.assertEqual(loaded.resolution, (1920, 1080))
        self.assertEqual(
            loaded.metadata["audio_duration"],
            4.25,
        )
        self.assertEqual(
            loaded.visual_bible.period,
            "13th century",
        )


if __name__ == "__main__":
    unittest.main()
