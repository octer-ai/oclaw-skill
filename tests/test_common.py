import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import common

PNG_BYTES = b"\x89PNG\r\n\x1a\nfakepayload"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()

MODELS = {
    "models": {
        "chat": {"gpt-5.5": {"route": "chat"}},
        "image": {
            "gpt-image-2": {"route": "image_openai"},
            "gemini-3.1-flash-image-preview": {"route": "image_chat"},
        },
    }
}
DEFAULTS = {"chat": "gpt-5.5", "image": "gpt-image-2", "video": "doubao-seedance-2-0-260128"}


class ResolveBaseUrl(unittest.TestCase):
    def test_env_wins(self):
        self.assertEqual(
            common.resolve_base_url("https://test.octer.ai/v1/", {"base_url": "https://x/v1"}),
            "https://test.octer.ai/v1",  # 尾斜杠被去除
        )

    def test_config_next(self):
        self.assertEqual(
            common.resolve_base_url(None, {"base_url": "https://test.octer.ai/v1"}),
            "https://test.octer.ai/v1",
        )

    def test_default_fallback(self):
        self.assertEqual(common.resolve_base_url(None, {}), "https://oclaw.octer.ai/v1")


class ExtractDataUris(unittest.TestCase):
    def test_extracts_single_png(self):
        text = f"here ![image](data:image/png;base64,{PNG_B64}) done"
        self.assertEqual(common.extract_data_uris(text), [("png", PNG_BYTES)])

    def test_extracts_multiple_mixed_ext(self):
        text = f"![a](data:image/png;base64,{PNG_B64}) ![b](data:image/jpeg;base64,{PNG_B64})"
        self.assertEqual([e for e, _ in common.extract_data_uris(text)], ["png", "jpeg"])

    def test_plain_text_gives_empty(self):
        self.assertEqual(common.extract_data_uris("I cannot generate that."), [])

    def test_undecodable_payload_skipped(self):
        self.assertEqual(common.extract_data_uris("data:image/png;base64,AAA"), [])


class TimestampedName(unittest.TestCase):
    def test_format(self):
        self.assertRegex(common.timestamped_name(index=2, ext="mp4"),
                         r"^\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-2\.mp4$")

    def test_defaults(self):
        self.assertRegex(common.timestamped_name(), r"-1\.png$")


class ResolveModel(unittest.TestCase):
    def test_explicit_model(self):
        mid, info = common.resolve_model(MODELS, "image", "gemini-3.1-flash-image-preview", DEFAULTS)
        self.assertEqual(mid, "gemini-3.1-flash-image-preview")
        self.assertEqual(info["route"], "image_chat")

    def test_none_picks_default(self):
        mid, _ = common.resolve_model(MODELS, "image", None, DEFAULTS)
        self.assertEqual(mid, "gpt-image-2")

    def test_wrong_category_raises_listing_available(self):
        with self.assertRaises(ValueError) as ctx:
            common.resolve_model(MODELS, "image", "gpt-5.5", DEFAULTS)
        self.assertIn("gpt-image-2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
