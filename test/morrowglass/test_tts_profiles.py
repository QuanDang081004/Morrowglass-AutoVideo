import unittest
from unittest.mock import patch

from app.morrowglass import tts_profiles


class TTSProfileTests(unittest.TestCase):
    def test_environment_overrides_autodetect(self):
        with patch.dict(
            "os.environ",
            {
                "MORROWGLASS_KOKORO_EN_PYTHON": r"C:\CustomEN\python.exe",
                "MORROWGLASS_KOKORO_VI_PYTHON": r"D:\CustomVI\python.exe",
            },
            clear=True,
        ):
            self.assertEqual(
                tts_profiles.default_kokoro_en_python(),
                r"C:\CustomEN\python.exe",
            )
            self.assertEqual(
                tts_profiles.default_kokoro_vi_python(),
                r"D:\CustomVI\python.exe",
            )

    def test_known_windows_paths_are_candidates(self):
        self.assertIn(
            r"C:\MorrowglassTTS\venv\Scripts\python.exe",
            [str(path) for path in tts_profiles.WINDOWS_EN_CANDIDATES],
        )
        self.assertIn(
            r"D:\Kokoro-Vietnamese\venv\Scripts\python.exe",
            [str(path) for path in tts_profiles.WINDOWS_VI_CANDIDATES],
        )


if __name__ == "__main__":
    unittest.main()
