import json
import unittest

from app.morrowglass.director import SceneDirector
from app.morrowglass.models import AssetType, VisualBible


class SceneDirectorTests(unittest.TestCase):
    def test_fallback_keeps_script_order(self):
        script = (
            "First sentence explains the setting. "
            "Second sentence shows the ritual. "
            "Third sentence explains why it mattered."
        )
        project = SceneDirector().plan(
            script,
            use_llm=False,
            target_scene_seconds=3,
        )
        self.assertEqual(
            " ".join(scene.narration for scene in project.scenes),
            script,
        )
        self.assertTrue(
            all(
                scene.scene_id.startswith("scene_")
                for scene in project.scenes
            )
        )

    def test_llm_json_is_normalized(self):
        script = (
            "A child carries food. "
            "A brick is placed at the entrance."
        )
        payload = [
            {
                "narration": "A child carries food.",
                "visual_description": "child carrying a basket",
                "image_prompt": "historical child carrying food",
                "motion_prompt": "slow walk",
                "asset_type": "image_to_video",
                "historical_constraints": ["no modern objects"],
            },
            {
                "narration": "A brick is placed at the entrance.",
                "visual_description": (
                    "brick placed at stone entrance"
                ),
                "image_prompt": (
                    "close shot of brick and stone entrance"
                ),
                "motion_prompt": "hand places brick",
                "asset_type": "video",
                "historical_constraints": ["no modern objects"],
            },
        ]
        project = SceneDirector(
            lambda _: json.dumps(payload)
        ).plan(
            script,
            bible=VisualBible(period="medieval"),
        )
        self.assertEqual(len(project.scenes), 2)
        self.assertEqual(
            project.scenes[0].asset_type,
            AssetType.IMAGE_TO_VIDEO,
        )


if __name__ == "__main__":
    unittest.main()
