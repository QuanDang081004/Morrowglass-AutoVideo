import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.models.schema import MaterialInfo
from app.morrowglass.generators import generate_missing_scene_images
from app.morrowglass.models import MorrowglassProject, Scene


class GeneratorTests(unittest.TestCase):
    def test_generates_scene_named_image(self):
        project = MorrowglassProject(
            "x",
            "hello",
            [
                Scene(
                    "scene_001",
                    "hello",
                    "hello visual",
                    "a precise historical image",
                )
            ],
        )
        project.scenes[0].start = 0.0
        project.scenes[0].end = 3.2

        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "raw.png"
            Image.new(
                "RGB",
                (1280, 720),
            ).save(generated)
            item = MaterialInfo(
                provider="openai_image",
                url=str(generated),
                duration=4,
            )

            with (
                patch(
                    "app.morrowglass.generators."
                    "mpt_openai_image_ready",
                    return_value=True,
                ),
                patch(
                    "app.morrowglass.generators.material."
                    "generate_images_openai",
                    return_value=[item],
                ) as generate,
            ):
                failures = generate_missing_scene_images(
                    project,
                    directory,
                    semantic_qc=False,
                )

            self.assertEqual(failures, [])
            self.assertTrue(
                (
                    Path(directory)
                    / "images"
                    / "scene_001.png"
                ).is_file()
            )
            self.assertIn(
                "a precise historical image",
                generate.call_args.kwargs["search_term"],
            )


if __name__ == "__main__":
    unittest.main()
