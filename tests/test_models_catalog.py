"""The catalog and the code that dispatches on it must not drift apart:
every route named in models.json has to be one some module actually implements.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import common
import generate_image
import generate_video

KNOWN_ROUTES = {
    "chat": {"chat"},
    "image": {"image_openai", "image_gemini"},
    "video": set(generate_video.BACKENDS),
}


class CatalogRoutes(unittest.TestCase):
    def setUp(self):
        self.catalog = common.load_models(sync=False)["models"]

    def test_every_route_is_implemented(self):
        for category, models in self.catalog.items():
            for model_id, info in models.items():
                with self.subTest(model=model_id):
                    self.assertIn(info.get("route"), KNOWN_ROUTES[category])

    def test_defaults_exist_in_the_catalog(self):
        for category, model_id in common.DEFAULT_MODELS.items():
            with self.subTest(category=category):
                self.assertIn(model_id, self.catalog[category])

    def test_image_routes_are_dispatchable(self):
        """generate_image branches on these names; a rename in one place only would
        turn every call into 'unknown image route'."""
        source = Path(generate_image.__file__).read_text()
        for route in KNOWN_ROUTES["image"]:
            with self.subTest(route=route):
                self.assertIn(f'"{route}"', source)


if __name__ == "__main__":
    unittest.main()
