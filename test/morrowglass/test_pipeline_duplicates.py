import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.morrowglass.models import (
    MorrowglassProject,
    Scene,
)
from app.morrowglass.pipeline import (
    MorrowglassPipeline,
)


class PipelineDuplicateTests(unittest.TestCase):
    def test_render_refuses_duplicate_scene_assets(self):
        project = MorrowglassProject(
            "x",
            "one two",
            [
                Scene(
                    "scene_001",
                    "one",
                    "one",
                    "one",
                ),
                Scene(
                    "scene_002",
                    "two",
                    "two",
                    "two",
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            images.mkdir(
                parents=True
            )
            first = images / "scene_001.png"
            second = images / "scene_002.png"
            Image.new(
                "RGB",
                (1280, 720),
                (10, 20, 30),
            ).save(first)
            second.write_bytes(
                first.read_bytes()
            )

            with patch(
                "app.morrowglass.pipeline."
                "render_final_video"
            ) as render:
                with self.assertRaisesRegex(
                    ValueError,
                    "duplicate scene assets",
                ):
                    MorrowglassPipeline().render(
                        project,
                        root,
                    )
                render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
