import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.morrowglass import audio
from app.morrowglass.models import MorrowglassProject, Scene


class AudioTests(unittest.TestCase):
    def test_transcribe_word_timing_records_path(self):
        project = MorrowglassProject(
            "x",
            "hello",
            [
                Scene(
                    "scene_001",
                    "hello",
                    "hello",
                    "hello",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            wav = Path(directory) / "audio.mp3"
            wav.write_bytes(b"x")

            def fake_create(audio_file, subtitle_file, word_level=False):
                self.assertTrue(word_level)
                Path(subtitle_file).write_text(
                    "1\n"
                    "00:00:00,000 --> 00:00:01,000\n"
                    "hello\n",
                    encoding="utf-8",
                )

            with patch(
                "app.services.subtitle.create",
                side_effect=fake_create,
            ):
                out = audio.transcribe_word_timing(
                    project,
                    directory,
                    wav,
                )

            self.assertTrue(out.exists())
            self.assertIn(
                "word_subtitle_file",
                project.metadata,
            )


if __name__ == "__main__":
    unittest.main()
