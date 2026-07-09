import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import generate_image


class BuildOpenaiPayload(unittest.TestCase):
    def test_minimal(self):
        p = generate_image.build_openai_payload("gpt-image-2", "an apple")
        self.assertEqual(p, {"model": "gpt-image-2", "prompt": "an apple", "n": 1})

    def test_aspect_maps_to_size(self):
        p = generate_image.build_openai_payload("gpt-image-2", "x", n=2, aspect="16:9")
        self.assertEqual(p["size"], "1536x1024")
        self.assertEqual(p["n"], 2)

    def test_unmapped_aspect_omits_size(self):
        p = generate_image.build_openai_payload("gpt-image-2", "x", aspect="21:9")
        self.assertNotIn("size", p)


class BuildChatPayload(unittest.TestCase):
    def test_plain(self):
        p = generate_image.build_chat_payload("m", "an apple")
        self.assertEqual(p["messages"], [{"role": "user", "content": "an apple"}])

    def test_aspect_appended_to_prompt(self):
        p = generate_image.build_chat_payload("m", "an apple", aspect="16:9")
        self.assertIn("Aspect ratio: 16:9", p["messages"][0]["content"])
        self.assertTrue(p["messages"][0]["content"].startswith("an apple"))


if __name__ == "__main__":
    unittest.main()
