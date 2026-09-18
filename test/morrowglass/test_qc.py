import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.morrowglass.qc import (
    Scene,
    semantic_scene_qc,
    technical_image_qc,
)

class QCTests(unittest.TestCase):
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
