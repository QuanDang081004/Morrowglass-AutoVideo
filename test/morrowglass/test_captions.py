import tempfile
import unittest
from pathlib import Path

from app.morrowglass.captions import group_word_cues, write_srt
from app.morrowglass.timeline import Cue, parse_srt

class CaptionTests(unittest.TestCase):
    def test_groups_words_and_keeps_punctuation(self):
        cues = [
            Cue(0.0, 0.3, "And"), Cue(0.3, 0.6, "with"),
            Cue(0.6, 0.9, "every"), Cue(0.9, 1.2, "visit,"),
            Cue(1.2, 1.5, "another"), Cue(1.5, 1.8, "brick"),
            Cue(1.8, 2.1, "was"), Cue(2.1, 2.4, "added."),
        ]
        groups = group_word_cues(cues, max_words=4)
        self.assertEqual(groups[0].text, "And with every visit,")
        self.assertEqual(groups[1].text, "another brick was added.")

    def test_write_srt_ends_with_blank_line_for_moviepy(self):
        cues = [
            Cue(
                0.0,
                1.0,
                "single caption",
            )
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = write_srt(
                cues,
                Path(directory) / "single.srt",
            )
            payload = path.read_text(
                encoding="utf-8"
            )
        self.assertTrue(
            payload.endswith("\n\n")
        )

    def test_write_and_parse_roundtrip(self):
        cues = [Cue(0.0, 1.25, "hello world")]
        with tempfile.TemporaryDirectory() as d:
            path = write_srt(cues, Path(d) / "x.srt")
            parsed = parse_srt(path)
        self.assertEqual(parsed[0].text, "hello world")
        self.assertAlmostEqual(parsed[0].end, 1.25, places=2)

if __name__ == "__main__": unittest.main()
