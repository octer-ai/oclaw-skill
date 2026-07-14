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
            "gemini-3.1-flash-image-preview": {"route": "image_gemini"},
        },
    }
}
DEFAULTS = {"chat": "gpt-5.5", "image": "gpt-image-2", "video": "doubao-seedance-2-0-260128"}


class ResolveBaseUrl(unittest.TestCase):
    def test_env_wins(self):
        self.assertEqual(
            common.resolve_base_url("https://test.octer.ai/", {"base_url": "https://x"}),
            "https://test.octer.ai",  # 尾斜杠被去除
        )

    def test_config_next(self):
        self.assertEqual(
            common.resolve_base_url(None, {"base_url": "https://test.octer.ai"}),
            "https://test.octer.ai",
        )

    def test_default_fallback(self):
        self.assertEqual(common.resolve_base_url(None, {}), "https://oclaw.octer.ai")

    def test_legacy_v1_suffix_stripped(self):
        """旧写法 <host>/v1 仍可用：去掉 /v1，避免各调用点再拼出 /v1/v1。"""
        self.assertEqual(
            common.resolve_base_url("https://test.octer.ai/v1/", {}),
            "https://test.octer.ai",
        )

    def test_v1beta_suffix_kept(self):
        """只剥 /v1，不误伤 /v1beta 之类的其它前缀。"""
        self.assertEqual(
            common.resolve_base_url("https://test.octer.ai/v1beta", {}),
            "https://test.octer.ai/v1beta",
        )


class AuthHeaders(unittest.TestCase):
    def test_bearer_is_the_default(self):
        self.assertEqual(common.auth_headers("sk-x"), {"Authorization": "Bearer sk-x"})

    def test_gemini_native_uses_a_goog_header(self):
        """The /v1beta route rejects Bearer auth; it wants x-goog-api-key."""
        self.assertEqual(common.auth_headers("sk-x", "goog"), {"x-goog-api-key": "sk-x"})


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
        self.assertEqual(info["route"], "image_gemini")

    def test_none_picks_default(self):
        mid, _ = common.resolve_model(MODELS, "image", None, DEFAULTS)
        self.assertEqual(mid, "gpt-image-2")

    def test_wrong_category_raises_listing_available(self):
        with self.assertRaises(ValueError) as ctx:
            common.resolve_model(MODELS, "image", "gpt-5.5", DEFAULTS)
        self.assertIn("gpt-image-2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
