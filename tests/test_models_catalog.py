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

    def test_catalog_uses_current_public_gateway_ids(self):
        expected = {
            "chat": {"deepseek-v4-flash", "deepseek-v4-pro", "glm-5.2"},
            "image": {"gemini-3-pro-image", "gemini-3.1-flash-image"},
            "video": {
                "doubao-seedance-2-0-mini-260615",
                "doubao-seedance-2-0-fast-260128",
                "doubao-seedance-2-0-260128",
                "doubao-seedance-2-5-260628",
            },
        }
        for category, model_ids in expected.items():
            with self.subTest(category=category):
                self.assertTrue(model_ids.issubset(self.catalog[category]))

        retired = {
            "gemini-3-pro-image-preview",
            "gemini-3.1-flash-image-preview",
            "seedance-2.0",
            "seedance-2.0-mini",
            "grok-imagine-1.5-video",
        }
        all_ids = {
            model_id
            for models in self.catalog.values()
            for model_id in models
        }
        self.assertTrue(retired.isdisjoint(all_ids))


if __name__ == "__main__":
    unittest.main()
