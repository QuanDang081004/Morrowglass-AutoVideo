import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.morrowglass.archive import ArchiveAsset
from app.morrowglass.assets import (
    resolve_assets,
    write_manual_image_queue,
)
from app.morrowglass.generators import _resolve_image_provider
from app.morrowglass.models import MorrowglassProject, Scene
from app.morrowglass.pipeline import MorrowglassPipeline


class ResearchFirstWorkflowTests(unittest.TestCase):
    def _project(self) -> MorrowglassProject:
        return MorrowglassProject(
            "Research first",
            (
                "Ancient Rome funeral mask actors. "
                "A family carries an ancestor image in a funeral procession."
            ),
            [
                Scene(
                    "scene_001",
                    "Ancient Rome funeral mask actors.",
                    "Roman funeral actors wearing ritual masks",
                    "photorealistic Roman funeral actors wearing ritual masks",
                    search_query="Ancient Rome funeral actors ritual masks",
                ),
                Scene(
                    "scene_002",
                    "A family carries an ancestor image in a funeral procession.",
                    "Roman family funeral procession carrying ancestor portrait",
                    "photorealistic Roman family funeral procession ancestor portrait",
                    search_query="Roman family funeral procession ancestor portrait",
                ),
            ],
        )

    def test_auto_provider_never_switches_to_comfyui(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / "image.json"
            workflow.write_text("{}", encoding="utf-8")

            provider, selected_workflow = _resolve_image_provider(
                "auto",
                root,
                workflow,
            )

        self.assertEqual(provider, "wikimedia")
        self.assertIsNone(selected_workflow)

    def test_manual_queue_contains_only_unresolved_scenes(self):
        project = self._project()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            images.mkdir()
            Image.new("RGB", (1280, 720)).save(
                images / "scene_001.png"
            )
            project.metadata["asset_sources"] = {
                "scene_001": {
                    "provider": "wikimedia",
                    "source_page": "https://example.com/source",
                }
            }

            resolve_assets(project, root)
            missing = write_manual_image_queue(project, root)

            self.assertEqual(missing, ["scene_002"])
            self.assertEqual(
                project.metadata["asset_resolution_status"]["scene_001"],
                "resolved_by_search",
            )
            self.assertEqual(
                project.metadata["asset_resolution_status"]["scene_002"],
                "needs_manual_image",
            )

            payload = json.loads(
                (root / "prompts" / "MANUAL_IMAGES.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["scene_id"], "scene_002")
            self.assertEqual(
                payload[0]["target_filename"],
                "images/scene_002.png",
            )
            self.assertIn(
                "ancestor portrait",
                payload[0]["image_prompt"],
            )

            Image.new("RGB", (1280, 720)).save(
                images / "scene_002.png"
            )
            resolve_assets(project, root)
            missing = write_manual_image_queue(project, root)

            self.assertEqual(missing, [])
            self.assertEqual(
                project.metadata["asset_resolution_status"]["scene_002"],
                "resolved_by_manual_image",
            )
            markdown = (
                root / "prompts" / "MANUAL_IMAGES.md"
            ).read_text(encoding="utf-8")
            self.assertIn("No manual images are required.", markdown)

    def test_context_only_archive_match_is_rejected_and_queued(self):
        project = MorrowglassProject(
            "Strict relevance",
            "Ancient Rome funeral mask actors.",
            [
                Scene(
                    "scene_001",
                    "Ancient Rome funeral mask actors.",
                    "Roman funeral actors wearing ritual masks",
                    "photorealistic Roman funeral actors wearing ritual masks",
                    search_query="Ancient Rome funeral actors ritual masks",
                )
            ],
        )
        weak = ArchiveAsset(
            title="Ancient Rome city panorama",
            image_url="https://example.com/rome.jpg",
            source_page="https://example.com/rome",
            license_name="Public domain",
            license_url="",
            artist="",
            description="General Roman Empire city architecture history",
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch(
                    "app.morrowglass.generators.search_wikimedia_images",
                    return_value=[weak],
                ),
                patch(
                    "app.morrowglass.generators.search_openverse_images",
                    return_value=[],
                ),
                patch(
                    "app.morrowglass.generators.search_met_images",
                    return_value=[],
                ),
                patch(
                    "app.morrowglass.generators.download_archive_image"
                ) as download,
            ):
                failures = MorrowglassPipeline().auto_generate_images(
                    project,
                    root,
                    provider="auto",
                    semantic_qc=False,
                    max_attempts=1,
                )

            self.assertEqual(failures, ["scene_001"])
            download.assert_not_called()
            self.assertFalse(
                (root / "images" / "scene_001.jpg").exists()
            )
            manual = (
                root / "prompts" / "MANUAL_IMAGES.md"
            ).read_text(encoding="utf-8")
            self.assertIn("scene_001", manual)
            self.assertIn(
                "photorealistic Roman funeral actors wearing ritual masks",
                manual,
            )
            self.assertTrue(
                any(
                    "research rejected" in note
                    for note in project.scenes[0].qc_notes
                )
            )


if __name__ == "__main__":
    unittest.main()
