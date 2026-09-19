import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.morrowglass.models import (
    MorrowglassProject,
    Scene,
)
from app.morrowglass.qc import (
    duplicate_scene_asset_groups,
    duplicate_scene_ids,
    semantic_scene_qc,
    technical_image_qc,
)

class QCTests(unittest.TestCase):
    def test_duplicate_scene_assets_detect_same_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "scene_001.png"
            second = root / "scene_002.png"
            Image.new(
                "RGB",
                (1280, 720),
            ).save(first)
            second.write_bytes(
                first.read_bytes()
            )
            project = MorrowglassProject(
                "x",
                "one two",
                [
                    Scene(
                        "scene_001",
                        "one",
                        "one",
                        "one",
                        asset_path=str(first),
                    ),
                    Scene(
                        "scene_002",
                        "two",
                        "two",
                        "two",
                        asset_path=str(second),
                    ),
                ],
            )
            groups = (
                duplicate_scene_asset_groups(
                    project
                )
            )
            duplicate_ids = (
                duplicate_scene_ids(
                    project
                )
            )

        self.assertEqual(
            groups,
            [["scene_001", "scene_002"]],
        )
        self.assertEqual(
            duplicate_ids,
            ["scene_002"],
        )

    def test_technical_qc_accepts_decodable_hd_image(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.png"
            Image.new("RGB", (1280, 720)).save(path)
            result = technical_image_qc(path)
        self.assertTrue(result.passed)

    def test_remote_semantic_qc_is_blocked_in_free_only(self):
        scene = Scene(
            "scene_001",
            "hello",
            "visible scene",
            "prompt",
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.png"
            Image.new(
                "RGB",
                (1280, 720),
            ).save(path)
            with patch.dict(
                "os.environ",
                {
                    "MORROWGLASS_VISION_BASE_URL": (
                        "https://paid.example/v1"
                    ),
                    "MORROWGLASS_VISION_MODEL": "vision",
                },
                clear=True,
            ):
                result = semantic_scene_qc(
                    scene,
                    path,
                )
        self.assertTrue(
            result.passed
        )
        self.assertTrue(
            any(
                "FREE-ONLY" in note
                for note in result.notes
            )
        )

    def test_technical_qc_rejects_tiny_image(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.png"
            Image.new("RGB", (100, 100)).save(path)
            result = technical_image_qc(path)
        self.assertFalse(result.passed)

if __name__ == "__main__": unittest.main()
