import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import list_models

DATA = {
    "lastUpdated": "2026-07-09",
    "models": {"image": {"gpt-image-2": {"name": "GPT Image 2", "route": "image_openai", "tested": True}}},
}


class FormatCatalog(unittest.TestCase):
    def test_contains_model_route_and_header(self):
        out = list_models.format_catalog(DATA)
        self.assertIn("gpt-image-2", out)
        self.assertIn("image_openai", out)
        self.assertIn("IMAGE:", out)

    def test_category_filter(self):
        out = list_models.format_catalog(DATA, "image")
        self.assertIn("gpt-image-2", out)

    def test_unknown_category_raises(self):
        with self.assertRaises(ValueError):
            list_models.format_catalog(DATA, "music")


if __name__ == "__main__":
    unittest.main()
