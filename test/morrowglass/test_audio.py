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

            def fake_create(
                audio_file,
                subtitle_file,
                word_level=False,
            ):
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

    def test_local_kokoro_voice_helpers(self):
        self.assertEqual(
            audio.local_kokoro_engine(
                "kokoro-en:am_michael"
            ),
            "english",
        )
        self.assertEqual(
            audio.local_kokoro_engine(
                "kokoro-local:am_michael"
            ),
            "english",
        )
        self.assertEqual(
            audio.local_kokoro_engine(
                "kokoro-vi:manh_dung"
            ),
            "vietnamese",
        )
        self.assertFalse(
            audio.is_local_kokoro_voice(
                "kokoro:am_michael"
            )
        )
        self.assertEqual(
            audio._local_kokoro_voice_id(
                "kokoro-vi:manh_dung"
            ),
            "manh_dung",
        )

    def test_vietnamese_voice_list_contains_known_voice(self):
        self.assertIn(
            "manh_dung",
            audio.VIETNAMESE_KOKORO_VOICES,
        )
        self.assertIn(
            "diem_trinh",
            audio.VIETNAMESE_KOKORO_VOICES,
        )

    def test_local_kokoro_records_audio_metadata(self):
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
        project.voice_name = (
            "kokoro-en:am_michael"
        )

        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            audio_dir = project_dir / "audio"
            audio_dir.mkdir()
            output = audio_dir / "narration.wav"
            output.write_bytes(
                b"valid-enough-for-mocked-duration"
            )

            with (
                patch(
                    "app.morrowglass.audio."
                    "_synthesize_local_kokoro",
                    return_value=output,
                ) as local_tts,
                patch(
                    "app.services.voice.get_audio_duration",
                    return_value=1.25,
                ),
            ):
                result, duration = audio.synthesize_narration(
                    project,
                    project_dir,
                    voice_name="kokoro-en:am_michael",
                    voice_rate=0.95,
                    voice_volume=1.1,
                    kokoro_en_python=(
                        r"C:\KokoroEN\venv\Scripts\python.exe"
                    ),
                )

            self.assertEqual(result, output)
            self.assertEqual(duration, 1.25)
            self.assertEqual(
                project.metadata["audio_duration"],
                1.25,
            )
            self.assertTrue(
                str(
                    project.metadata["audio_file"]
                ).endswith("narration.wav")
            )
            local_tts.assert_called_once()

    def test_missing_local_kokoro_python_is_clear(self):
        with patch.dict(
            "os.environ",
            {},
            clear=True,
        ):
            with self.assertRaises(
                FileNotFoundError
            ):
                audio._resolve_kokoro_python(
                    "",
                    engine="vietnamese",
                )


if __name__ == "__main__":
    unittest.main()
