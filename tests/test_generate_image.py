import base64
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


class BuildGeminiPayload(unittest.TestCase):
    def test_plain(self):
        p = generate_image.build_gemini_payload("an apple")
        self.assertEqual(p["contents"], [{"parts": [{"text": "an apple"}]}])

    def test_image_modality_is_requested(self):
        """Without IMAGE in responseModalities the model replies with text only."""
        p = generate_image.build_gemini_payload("an apple")
        self.assertIn("IMAGE", p["generationConfig"]["responseModalities"])

    def test_aspect_appended_to_prompt(self):
        p = generate_image.build_gemini_payload("an apple", aspect="16:9")
        text = p["contents"][0]["parts"][0]["text"]
        self.assertIn("Aspect ratio: 16:9", text)
        self.assertTrue(text.startswith("an apple"))


PNG = b"\x89PNG\r\n\x1a\nx"
PNG_B64 = base64.b64encode(PNG).decode()


class ExtractInlineImages(unittest.TestCase):
    def test_camel_case_rest_shape(self):
        result = {"candidates": [{"content": {"parts": [
            {"text": "here you go"},
            {"inlineData": {"mimeType": "image/png", "data": PNG_B64}},
        ]}}]}
        self.assertEqual(generate_image.extract_inline_images(result), [("png", PNG)])

    def test_snake_case_sdk_shape(self):
        result = {"candidates": [{"content": {"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": PNG_B64}},
        ]}}]}
        self.assertEqual(generate_image.extract_inline_images(result), [("jpeg", PNG)])

    def test_text_only_response_yields_no_images(self):
        result = {"candidates": [{"content": {"parts": [{"text": "I can't do that"}]}}]}
        self.assertEqual(generate_image.extract_inline_images(result), [])

    def test_text_is_recoverable_to_explain_a_refusal(self):
        result = {"candidates": [{"content": {"parts": [{"text": "I can't do that"}]}}]}
        self.assertEqual(generate_image.gemini_text(result), "I can't do that")

    def test_empty_response_is_survivable(self):
        self.assertEqual(generate_image.extract_inline_images({}), [])


if __name__ == "__main__":
    unittest.main()
