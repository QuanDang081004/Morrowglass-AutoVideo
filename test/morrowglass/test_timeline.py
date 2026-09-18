import unittest

from app.morrowglass.models import Scene
from app.morrowglass.timeline import Cue, assign_from_srt


class TimelineTests(unittest.TestCase):
    def test_assigns_ordered_ranges(self):
        scenes = [
            Scene(
                "scene_001",
                "one two three four",
                "v",
                "p",
            ),
            Scene(
                "scene_002",
                "five six seven eight",
                "v",
                "p",
            ),
        ]
        cues = [
            Cue(0, 1, "one two"),
            Cue(1, 2, "three four"),
            Cue(2, 3, "five six"),
            Cue(3, 4, "seven eight"),
        ]
        assign_from_srt(scenes, cues)
        self.assertEqual(
            (scenes[0].start, scenes[0].end),
            (0, 2),
        )
        self.assertEqual(
            (scenes[1].start, scenes[1].end),
            (2, 4),
        )


if __name__ == "__main__":
    unittest.main()
