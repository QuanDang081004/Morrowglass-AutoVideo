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

    def test_exact_word_boundary_not_86_percent(self):
        first = "one two three four five six seven eight nine ten"
        second = "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
        scenes = [
            Scene("scene_001", first, "v1", "p1"),
            Scene("scene_002", second, "v2", "p2"),
        ]
        words = (first + " " + second).split()
        cues = [
            Cue(i * 0.5, (i + 1) * 0.5, word)
            for i, word in enumerate(words)
        ]
        assign_from_srt(scenes, cues, audio_duration=10.0)
        self.assertEqual(scenes[0].end, 5.0)
        self.assertEqual(scenes[1].start, 5.0)

    def test_cut_uses_midpoint_of_pause(self):
        scenes = [
            Scene("scene_001", "hello world", "v1", "p1"),
            Scene("scene_002", "next scene", "v2", "p2"),
        ]
        cues = [
            Cue(0.0, 0.4, "hello"),
            Cue(0.4, 0.8, "world"),
            Cue(1.2, 1.5, "next"),
            Cue(1.5, 1.9, "scene"),
        ]
        assign_from_srt(scenes, cues, audio_duration=1.9)
        self.assertAlmostEqual(scenes[0].end, 1.0, places=3)
        self.assertAlmostEqual(scenes[1].start, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
