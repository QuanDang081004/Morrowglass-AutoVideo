import tempfile
import unittest
from pathlib import Path

from app.morrowglass.renderer import (
    _build_scene_ffmpeg_command,
    _fit_filter,
    _image_motion_filter,
    _load_render_cache,
    _save_render_cache,
    _scene_render_fingerprint,
)


class RendererTests(unittest.TestCase):
    def test_cover_filter_targets_exact_canvas(self):
        value = _fit_filter(
            1920,
            1080,
            "cover",
            30,
        )
        self.assertIn("scale=1920:1080", value)
        self.assertIn("crop=1920:1080", value)

    def test_image_command_loops_for_exact_duration(self):
        cmd = _build_scene_ffmpeg_command(
            asset_path="scene_001.jpg",
            output_path="out.mp4",
            duration=4.25,
            width=1920,
            height=1080,
            image_motion="none",
            ffmpeg_binary="ffmpeg",
        )
        self.assertIn("-loop", cmd)
        self.assertIn("4.250", cmd)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_video_command_stream_loops(self):
        cmd = _build_scene_ffmpeg_command(
            asset_path="scene_001.mp4",
            output_path="out.mp4",
            duration=2.0,
            width=1920,
            height=1080,
            ffmpeg_binary="ffmpeg",
        )
        self.assertIn("-stream_loop", cmd)

    def test_slow_zoom_uses_zoompan(self):
        value = _image_motion_filter(
            1920,
            1080,
            duration=6.0,
            motion_mode="slow_zoom",
            motion_variant=2,
        )
        self.assertIn("zoompan=", value)
        self.assertIn("1.06", value)
        self.assertIn("iw-iw/zoom", value)

    def test_none_motion_keeps_static_filter(self):
        value = _image_motion_filter(
            1920,
            1080,
            duration=6.0,
            motion_mode="none",
        )
        self.assertNotIn("zoompan=", value)
        self.assertIn("crop=1920:1080", value)

    def test_scene_fingerprint_changes_with_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            asset = Path(directory) / "scene.png"
            asset.write_bytes(b"asset")
            common = {
                "scene_id": "scene_001",
                "asset_path": asset,
                "width": 1920,
                "height": 1080,
                "fit_mode": "cover",
                "fps": 30,
                "image_motion": "slow_zoom",
                "motion_variant": 0,
            }
            first = _scene_render_fingerprint(
                duration=4.0,
                **common,
            )
            second = _scene_render_fingerprint(
                duration=5.0,
                **common,
            )
        self.assertNotEqual(first, second)

    def test_render_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "render-cache.json"
            _save_render_cache(
                path,
                {"scene_001": "fingerprint"},
            )
            loaded = _load_render_cache(path)
        self.assertEqual(
            loaded,
            {"scene_001": "fingerprint"},
        )


if __name__ == "__main__":
    unittest.main()
