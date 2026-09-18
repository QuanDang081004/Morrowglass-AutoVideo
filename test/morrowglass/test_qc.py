import tempfile
import unittest
from pathlib import Path

from PIL import Image

from app.morrowglass.qc import technical_image_qc

class QCTests(unittest.TestCase):
    def test_technical_qc_accepts_decodable_hd_image(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.png"
            Image.new("RGB", (1280, 720)).save(path)
            result = technical_image_qc(path)
        self.assertTrue(result.passed)

    def test_technical_qc_rejects_tiny_image(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.png"
            Image.new("RGB", (100, 100)).save(path)
            result = technical_image_qc(path)
        self.assertFalse(result.passed)

if __name__ == "__main__": unittest.main()
