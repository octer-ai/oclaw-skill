import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import common

PNG_BYTES = b"\x89PNG\r\n\x1a\nfakepayload"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()

MODELS = {
    "models": {
        "chat": {"gpt-5.5": {"route": "chat"}},
        "image": {
            "gpt-image-2": {"route": "image_openai"},
            "gemini-3-pro-image": {"route": "image_gemini"},
            "gemini-3.1-flash-image": {"route": "image_gemini"},
        },
        "video": {
            "doubao-seedance-2-0-260128": {"route": "video_volcengine"},
        },
    }
}
DEFAULTS = {
    "chat": "gpt-5.5",
    "image": "gpt-image-2",
    "video": "doubao-seedance-2-0-260128",
}


def model_catalog(last_updated, video_model):
    return {
        "lastUpdated": last_updated,
        "models": {
            "chat": {
                "gpt-5.5": {"name": "GPT-5.5", "route": "chat", "tested": True}
            },
            "image": {
                "gpt-image-2": {
                    "name": "GPT Image 2",
                    "route": "image_openai",
                    "tested": True,
                }
            },
            "video": {
                video_model: {
                    "name": video_model,
                    "route": "video_volcengine",
                    "tested": True,
                }
            },
        },
    }


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


class ModelCatalogSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.cache_dir = self.root / "cache"
        self.bundled = model_catalog("2026-07-01", "bundled-video")
        (self.root / "models.json").write_text(json.dumps(self.bundled))
        self.root_patch = mock.patch.object(common, "SKILL_ROOT", self.root)
        self.env_patch = mock.patch.dict(
            common.os.environ,
            {
                "OCLAW_MODEL_CACHE_DIR": str(self.cache_dir),
                "OCLAW_MODEL_SYNC": "1",
            },
        )
        self.root_patch.start()
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.root_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def response_for(data):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps(data).encode("utf-8")
        return response

    def test_fetches_newer_catalog_without_forwarding_credentials(self):
        remote = model_catalog("2026-08-12", "remote-video")
        response = self.response_for(remote)
        with mock.patch.object(
            common.urllib.request, "urlopen", return_value=response
        ) as urlopen:
            loaded = common.load_models()

        self.assertIn("remote-video", loaded["models"]["video"])
        request = urlopen.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("X-goog-api-key"))
        self.assertTrue((self.cache_dir / "models.json").exists())

    def test_fresh_attempt_marker_prevents_repeated_fetch(self):
        remote = model_catalog("2026-08-12", "remote-video")
        with mock.patch.object(
            common.urllib.request, "urlopen", return_value=self.response_for(remote)
        ):
            common.load_models()

        with mock.patch.object(common.urllib.request, "urlopen") as urlopen:
            loaded = common.load_models()
        urlopen.assert_not_called()
        self.assertIn("remote-video", loaded["models"]["video"])

    def test_offline_fetch_falls_back_to_newer_cached_catalog(self):
        cached = model_catalog("2026-08-01", "cached-video")
        self.cache_dir.mkdir(parents=True)
        (self.cache_dir / "models.json").write_text(json.dumps(cached))

        with mock.patch.object(
            common.urllib.request,
            "urlopen",
            side_effect=common.urllib.error.URLError("offline"),
        ):
            loaded = common.load_models()
        self.assertIn("cached-video", loaded["models"]["video"])

    def test_remote_catalog_with_unknown_route_is_rejected(self):
        remote = model_catalog("2026-08-12", "unsupported-video")
        remote["models"]["video"]["unsupported-video"]["route"] = "video_future"
        with mock.patch.object(
            common.urllib.request, "urlopen", return_value=self.response_for(remote)
        ):
            loaded = common.load_models()
        self.assertIn("bundled-video", loaded["models"]["video"])
        self.assertNotIn("unsupported-video", loaded["models"]["video"])


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
        mid, info = common.resolve_model(MODELS, "image", "gemini-3.1-flash-image", DEFAULTS)
        self.assertEqual(mid, "gemini-3.1-flash-image")
        self.assertEqual(info["route"], "image_gemini")

    def test_legacy_model_ids_are_normalized(self):
        cases = (
            ("image", "gemini-3-pro-image-preview", "gemini-3-pro-image"),
            ("image", "gemini-3.1-flash-image-preview", "gemini-3.1-flash-image"),
        )
        for category, legacy, current in cases:
            with self.subTest(legacy=legacy):
                mid, _info = common.resolve_model(
                    MODELS, category, legacy, DEFAULTS
                )
                self.assertEqual(mid, current)

    def test_current_seedance_id_is_preserved(self):
        mid, _info = common.resolve_model(
            MODELS, "video", "doubao-seedance-2-0-260128", DEFAULTS
        )
        self.assertEqual(mid, "doubao-seedance-2-0-260128")

    def test_retired_seedance_id_is_rejected(self):
        with self.assertRaises(ValueError):
            common.resolve_model(MODELS, "video", "seedance-2.0", DEFAULTS)

    def test_none_picks_default(self):
        mid, _ = common.resolve_model(MODELS, "image", None, DEFAULTS)
        self.assertEqual(mid, "gpt-image-2")

    def test_wrong_category_raises_listing_available(self):
        with self.assertRaises(ValueError) as ctx:
            common.resolve_model(MODELS, "image", "gpt-5.5", DEFAULTS)
        self.assertIn("gpt-image-2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
