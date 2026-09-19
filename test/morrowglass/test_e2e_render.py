import tempfile
import unittest
import wave
from pathlib import Path

from moviepy import VideoFileClip
from PIL import Image

from app.morrowglass.models import (
    MorrowglassProject,
    Scene,
)
from app.morrowglass.renderer import render_final_video
from app.utils import utils


def _write_silence(
    path: Path,
    *,
    duration: float,
    sample_rate: int = 24000,
) -> None:
    frame_count = int(
        duration * sample_rate
    )
    with wave.open(
        str(path),
        "wb",
    ) as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(
            sample_rate
        )
        handle.writeframes(
            b"\x00\x00" * frame_count
        )


class EndToEndRenderTests(unittest.TestCase):
    def test_two_scene_project_renders_real_mp4(self):
        if not utils.check_ffmpeg_ready():
            self.skipTest(
                "FFmpeg is unavailable"
            )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images_dir = root / "images"
            audio_dir = root / "audio"
            subtitles_dir = root / "subtitles"
            for folder in (
                images_dir,
                audio_dir,
                subtitles_dir,
                root / "output",
                root / "cache",
            ):
                folder.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            first_image = (
                images_dir
                / "scene_001.png"
            )
            second_image = (
                images_dir
                / "scene_002.png"
            )
            Image.new(
                "RGB",
                (640, 360),
                (32, 48, 64),
            ).save(first_image)
            Image.new(
                "RGB",
                (640, 360),
                (96, 72, 48),
            ).save(second_image)

            narration = (
                audio_dir
                / "narration.wav"
            )
            _write_silence(
                narration,
                duration=2.0,
            )

            words = (
                subtitles_dir
                / "words.srt"
            )
            words.write_text(
                "1\n"
                "00:00:00,000 --> 00:00:01,000\n"
                "Hello\n\n"
                "2\n"
                "00:00:01,000 --> 00:00:02,000\n"
                "history\n",
                encoding="utf-8",
            )

            scenes = [
                Scene(
                    scene_id="scene_001",
                    narration="Hello",
                    visual_description=(
                        "first historical visual"
                    ),
                    image_prompt="first visual",
                    start=0.0,
                    end=1.0,
                    asset_path=str(
                        first_image
                    ),
                ),
                Scene(
                    scene_id="scene_002",
                    narration="history",
                    visual_description=(
                        "second historical visual"
                    ),
                    image_prompt="second visual",
                    start=1.0,
                    end=2.0,
                    asset_path=str(
                        second_image
                    ),
                ),
            ]
            project = MorrowglassProject(
                title="E2E Test",
                script="Hello history",
                scenes=scenes,
                resolution=(640, 360),
            )
            project.metadata.update(
                {
                    "audio_file": str(
                        narration
                    ),
                    "audio_duration": 2.0,
                    "word_subtitle_file": str(
                        words
                    ),
                }
            )

            final = render_final_video(
                project,
                root,
                font_name=(
                    "BeVietnamPro-Medium.ttf"
                ),
                font_size=24,
                image_motion="none",
            )

            self.assertTrue(
                final.is_file()
            )
            self.assertGreater(
                final.stat().st_size,
                1000,
            )
            with VideoFileClip(
                str(final)
            ) as clip:
                self.assertEqual(
                    tuple(clip.size),
                    (640, 360),
                )
                self.assertGreater(
                    clip.duration,
                    1.7,
                )
                self.assertLess(
                    clip.duration,
                    2.3,
                )


if __name__ == "__main__":
    unittest.main()
