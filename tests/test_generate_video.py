import base64
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import generate_video


class ImageRefToValue(unittest.TestCase):
    def test_url_passthrough(self):
        self.assertEqual(generate_video.image_ref_to_value("https://x.com/a.png"),
                         "https://x.com/a.png")

    def test_local_png_becomes_data_uri(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.png"
            p.write_bytes(b"\x89PNG\r\n\x1a\nabc")
            val = generate_video.image_ref_to_value(str(p))
            self.assertTrue(val.startswith("data:image/png;base64,"))
            self.assertEqual(base64.b64decode(val.split(",", 1)[1]), b"\x89PNG\r\n\x1a\nabc")

    def test_jpg_maps_to_jpeg_mime(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.jpg"
            p.write_bytes(b"\xff\xd8\xff")
            self.assertTrue(generate_video.image_ref_to_value(str(p))
                            .startswith("data:image/jpeg;base64,"))

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            generate_video.image_ref_to_value("/no/such/file.png")

    def test_unsupported_ext_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ref.bmp"
            p.write_bytes(b"BM")
            with self.assertRaises(ValueError):
                generate_video.image_ref_to_value(str(p))


class BuildPayload(unittest.TestCase):
    def test_minimal(self):
        self.assertEqual(generate_video.build_payload("m", "a cat"),
                         {"model": "m", "prompt": "a cat"})

    def test_with_image_and_duration(self):
        p = generate_video.build_payload("m", "a cat",
                                         image_value="data:image/png;base64,AAAA", duration=5)
        self.assertEqual(p["image"], "data:image/png;base64,AAAA")
        self.assertEqual(p["duration"], 5)


if __name__ == "__main__":
    unittest.main()
