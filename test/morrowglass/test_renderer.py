import unittest
from app.morrowglass.renderer import _build_scene_ffmpeg_command, _fit_filter

class RendererTests(unittest.TestCase):
    def test_cover_filter_targets_exact_canvas(self):
        value = _fit_filter(1920, 1080, "cover", 30)
        self.assertIn("scale=1920:1080", value)
        self.assertIn("crop=1920:1080", value)

    def test_image_command_loops_for_exact_duration(self):
        cmd = _build_scene_ffmpeg_command(
            asset_path="scene_001.jpg", output_path="out.mp4", duration=4.25,
            width=1920, height=1080, ffmpeg_binary="ffmpeg",
        )
        self.assertIn("-loop", cmd)
        self.assertIn("4.250", cmd)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_video_command_stream_loops(self):
        cmd = _build_scene_ffmpeg_command(
            asset_path="scene_001.mp4", output_path="out.mp4", duration=2.0,
            width=1920, height=1080, ffmpeg_binary="ffmpeg",
        )
        self.assertIn("-stream_loop", cmd)

if __name__ == "__main__": unittest.main()
