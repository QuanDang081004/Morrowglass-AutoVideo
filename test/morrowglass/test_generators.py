import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from app.models.schema import MaterialInfo
from app.morrowglass.archive import ArchiveAsset
from app.morrowglass.generators import (
    ImageGenerationUnavailable,
    _motion_source_fingerprint,
    _resolve_image_provider,
    _scene_seed,
    generate_missing_scene_images,
    generate_motion_scene_videos,
)
from app.morrowglass.models import (
    AssetType,
    MorrowglassProject,
    Scene,
)


class GeneratorTests(unittest.TestCase):
    def test_scene_seed_is_stable(self):
        self.assertEqual(
            _scene_seed("scene_001", 1),
            _scene_seed("scene_001", 1),
        )
        self.assertNotEqual(
            _scene_seed("scene_001", 1),
            _scene_seed("scene_001", 2),
        )

    def test_generates_scene_named_image_with_mpt(self):
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
                    "paid_providers_enabled",
                    return_value=True,
                ),
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
                    provider="mpt_openai",
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

    def test_paid_image_provider_is_blocked_by_default(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "app.morrowglass.generators."
                "paid_providers_enabled",
                return_value=False,
            ),
        ):
            with self.assertRaises(
                ImageGenerationUnavailable
            ):
                _resolve_image_provider(
                    "mpt_openai",
                    Path(directory),
                    None,
                )

    def test_motion_fingerprint_changes_when_source_image_changes(self):
        scene = Scene(
            "scene_001",
            "motion",
            "visible motion",
            "prompt",
            motion_prompt="slow walk",
            asset_type=AssetType.IMAGE_TO_VIDEO,
        )
        project = MorrowglassProject(
            "x",
            "motion",
            [scene],
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "scene.png"
            workflow = root / "video.json"
            image.write_bytes(b"first")
            workflow.write_text(
                "{}",
                encoding="utf-8",
            )
            first = _motion_source_fingerprint(
                scene=scene,
                project=project,
                image=image,
                workflow_path=workflow,
            )
            image.write_bytes(b"second")
            second = _motion_source_fingerprint(
                scene=scene,
                project=project,
                image=image,
                workflow_path=workflow,
            )
        self.assertNotEqual(
            first,
            second,
        )

    def test_wikimedia_assigns_different_sources_to_adjacent_scenes(self):
        first = ArchiveAsset(
            title="Roman wax mask ancestor",
            image_url="https://example.com/a.jpg",
            source_page="https://example.com/a",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Roman wax mask ancestor family portrait",
        )
        second = ArchiveAsset(
            title="Roman wax mask family",
            image_url="https://example.com/b.jpg",
            source_page="https://example.com/b",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Roman wax mask family ancestor portrait",
        )
        project = MorrowglassProject(
            "x",
            "Ancient Rome wax mask ancestors. Ancient Rome wax mask family.",
            [
                Scene(
                    "scene_001",
                    "Ancient Rome wax mask ancestors.",
                    "Roman wax mask ancestors",
                    "Roman wax mask ancestors",
                    search_query="Ancient Rome wax mask ancestors",
                ),
                Scene(
                    "scene_002",
                    "Ancient Rome wax mask family.",
                    "Roman wax mask family",
                    "Roman wax mask family",
                    search_query="Ancient Rome wax mask family",
                ),
            ],
        )

        def fake_download(asset, target, **_kwargs):
            target = Path(target)
            color = (
                (10, 20, 30)
                if asset.source_page.endswith("/a")
                else (40, 50, 60)
            )
            Image.new(
                "RGB",
                (1280, 720),
                color,
            ).save(target)
            return target

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "app.morrowglass.generators."
                    "search_wikimedia_images",
                    return_value=[
                        first,
                        second,
                    ],
                ),
                patch(
                    "app.morrowglass.generators."
                    "download_archive_image",
                    side_effect=fake_download,
                ),
            ):
                failures = generate_missing_scene_images(
                    project,
                    directory,
                    provider="wikimedia",
                    semantic_qc=False,
                    max_attempts=2,
                )

        self.assertEqual(
            failures,
            [],
        )
        sources = project.metadata[
            "asset_sources"
        ]
        self.assertEqual(
            sources["scene_001"][
                "source_page"
            ],
            "https://example.com/a",
        )
        self.assertEqual(
            sources["scene_002"][
                "source_page"
            ],
            "https://example.com/b",
        )

    def test_wikimedia_rejects_same_bytes_from_different_sources(self):
        first = ArchiveAsset(
            title="Roman funeral mask A",
            image_url="https://example.com/a.jpg",
            source_page="https://example.com/a",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Roman funeral mask ancestor",
        )
        second = ArchiveAsset(
            title="Roman funeral mask B",
            image_url="https://example.com/b.jpg",
            source_page="https://example.com/b",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Roman funeral mask ancestor",
        )
        project = MorrowglassProject(
            "x",
            "Roman funeral mask. Roman funeral mask.",
            [
                Scene(
                    "scene_001",
                    "Roman funeral mask.",
                    "Roman funeral mask",
                    "Roman funeral mask",
                    search_query="Roman funeral mask",
                ),
                Scene(
                    "scene_002",
                    "Roman funeral mask.",
                    "Roman funeral mask",
                    "Roman funeral mask",
                    search_query="Roman funeral mask",
                ),
            ],
        )

        def same_download(_asset, target, **_kwargs):
            target = Path(target)
            Image.new(
                "RGB",
                (1280, 720),
                (12, 34, 56),
            ).save(target)
            return target

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch(
                    "app.morrowglass.generators."
                    "search_wikimedia_images",
                    return_value=[
                        first,
                        second,
                    ],
                ),
                patch(
                    "app.morrowglass.generators."
                    "download_archive_image",
                    side_effect=same_download,
                ),
            ):
                failures = generate_missing_scene_images(
                    project,
                    directory,
                    provider="wikimedia",
                    semantic_qc=False,
                    max_attempts=2,
                )

        self.assertEqual(
            failures,
            ["scene_002"],
        )
        self.assertTrue(
            any(
                "duplicate image hash" in note
                for note in project.scenes[
                    1
                ].qc_notes
            )
        )

    def test_comfyui_image_provider_uses_scene_prompt(self):
        project = MorrowglassProject(
            "x",
            "hello",
            [
                Scene(
                    "scene_001",
                    "hello",
                    "visible action",
                    "scene-specific prompt",
                )
            ],
        )
        project.scenes[0].start = 0.0
        project.scenes[0].end = 4.0

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = root / "image.json"
            workflow.write_text(
                '{"1":{"class_type":"Test","inputs":'
                '{"text":"{{PROMPT}}"}}}',
                encoding="utf-8",
            )

            fake_client = Mock()
            fake_client.base_url = "http://127.0.0.1:8188"
            fake_client.ping.return_value = True

            def fake_run(
                prepared,
                *,
                target_dir,
                preferred_kind,
                timeout,
                prefix,
            ):
                self.assertEqual(
                    prepared["1"]["inputs"]["text"],
                    "scene-specific prompt",
                )
                output = Path(target_dir) / "candidate.png"
                Image.new(
                    "RGB",
                    (1280, 720),
                ).save(output)
                return output

            fake_client.run.side_effect = fake_run

            with patch(
                "app.morrowglass.generators.ComfyUIClient",
                return_value=fake_client,
            ):
                failures = generate_missing_scene_images(
                    project,
                    root,
                    provider="comfyui",
                    comfyui_workflow=workflow,
                    semantic_qc=False,
                )

            self.assertEqual(failures, [])
            self.assertTrue(
                (
                    root
                    / "images"
                    / "scene_001.png"
                ).is_file()
            )

    def test_comfyui_video_only_animates_motion_scenes(self):
        motion = Scene(
            "scene_001",
            "motion narration",
            "visible motion",
            "historical image prompt",
            motion_prompt="slow walking motion",
            asset_type=AssetType.IMAGE_TO_VIDEO,
        )
        still = Scene(
            "scene_002",
            "still narration",
            "still visual",
            "still prompt",
            asset_type=AssetType.IMAGE,
        )
        project = MorrowglassProject(
            "x",
            "motion narration still narration",
            [motion, still],
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            images.mkdir()
            Image.new(
                "RGB",
                (1280, 720),
            ).save(images / "scene_001.png")
            Image.new(
                "RGB",
                (1280, 720),
            ).save(images / "scene_002.png")

            workflow = root / "video.json"
            workflow.write_text(
                '{"1":{"class_type":"Test","inputs":'
                '{"image":"{{INPUT_IMAGE}}",'
                '"text":"{{MOTION_PROMPT}}"}}}',
                encoding="utf-8",
            )

            fake_client = Mock()
            fake_client.base_url = "http://127.0.0.1:8188"
            fake_client.ping.return_value = True
            fake_client.upload_image.return_value = "scene_001.png"

            def fake_run(
                prepared,
                *,
                target_dir,
                preferred_kind,
                timeout,
                prefix,
            ):
                self.assertEqual(
                    prepared["1"]["inputs"]["image"],
                    "scene_001.png",
                )
                self.assertEqual(
                    prepared["1"]["inputs"]["text"],
                    "slow walking motion",
                )
                output = Path(target_dir) / "candidate.mp4"
                output.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                output.write_bytes(b"video")
                return output

            fake_client.run.side_effect = fake_run

            with patch(
                "app.morrowglass.generators.ComfyUIClient",
                return_value=fake_client,
            ):
                failures = generate_motion_scene_videos(
                    project,
                    root,
                    comfyui_workflow=workflow,
                )

            self.assertEqual(failures, [])
            self.assertTrue(
                (
                    root
                    / "videos"
                    / "scene_001.mp4"
                ).is_file()
            )
            self.assertFalse(
                (
                    root
                    / "videos"
                    / "scene_002.mp4"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
