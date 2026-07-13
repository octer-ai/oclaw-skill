import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import generate_video

MODELS = {
    "models": {
        "video": {
            "doubao-seedance-2-0-260128": {"route": "video_volcengine"},
            "grok-imagine-video": {"route": "video_xai"},
        }
    }
}


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


class BuildVolcPayload(unittest.TestCase):
    """Volcengine takes the prompt as a list of content parts, not a "prompt" string."""

    def test_minimal(self):
        self.assertEqual(
            generate_video.build_volc_payload("m", "a cat"),
            {"model": "m", "content": [{"type": "text", "text": "a cat"}]},
        )

    def test_image_becomes_a_content_part(self):
        p = generate_video.build_volc_payload("m", "a cat",
                                              image_value="data:image/png;base64,AAAA")
        self.assertEqual(p["content"][1],
                         {"type": "image_url",
                          "image_url": {"url": "data:image/png;base64,AAAA"}})

    def test_aspect_is_named_ratio(self):
        p = generate_video.build_volc_payload("m", "a cat", duration=4,
                                              aspect="9:16", resolution="480p")
        self.assertEqual(p["ratio"], "9:16")
        self.assertEqual(p["resolution"], "480p")
        self.assertEqual(p["duration"], 4)


class BuildXaiPayload(unittest.TestCase):
    def test_minimal(self):
        self.assertEqual(generate_video.build_xai_payload("m", "a cat"),
                         {"model": "m", "prompt": "a cat"})

    def test_aspect_is_named_aspect_ratio(self):
        p = generate_video.build_xai_payload("m", "a cat", duration=6,
                                             aspect="9:16", resolution="480p")
        self.assertEqual(p["aspect_ratio"], "9:16")
        self.assertEqual(p["resolution"], "480p")
        self.assertEqual(p["duration"], 6)


class XaiRejectsImage(unittest.TestCase):
    def test_image_to_video_is_refused_rather_than_silently_dropped(self):
        with self.assertRaises(ValueError):
            generate_video.xai_submit("grok-imagine-video", "a cat",
                                      image_value="https://x.com/a.png")


class PollNormalisesVendorStatus(unittest.TestCase):
    def poll(self, fn, payload):
        with mock.patch.object(generate_video.common, "api_request", return_value=payload):
            return fn("task_1")

    def test_volc_succeeded_is_completed(self):
        status, url, _err, _p = self.poll(
            generate_video.volc_poll,
            {"status": "succeeded", "content": {"video_url": "https://cdn/v.mp4"}})
        self.assertEqual(status, "completed")
        self.assertEqual(url, "https://cdn/v.mp4")

    def test_volc_running(self):
        status, _u, _e, _p = self.poll(generate_video.volc_poll, {"status": "running"})
        self.assertEqual(status, "running")

    def test_xai_done_is_completed(self):
        status, url, _err, _p = self.poll(
            generate_video.xai_poll,
            {"status": "done", "video": {"url": "https://cdn/v.mp4"}})
        self.assertEqual(status, "completed")
        self.assertEqual(url, "https://cdn/v.mp4")

    def test_xai_expired_is_a_failure_with_a_reason(self):
        status, _url, err, _p = self.poll(generate_video.xai_poll, {"status": "expired"})
        self.assertEqual(status, "failed")
        self.assertTrue(err)

    def test_unknown_status_keeps_polling(self):
        status, _u, _e, _p = self.poll(generate_video.volc_poll, {"status": "whatever"})
        self.assertEqual(status, "running")


class RouteForTask(unittest.TestCase):
    """Both vendors mint task_... ids, so the route has to come from the model."""

    def test_explicit_model_wins(self):
        self.assertEqual(
            generate_video.route_for_task("task_1", model_id="grok-imagine-video",
                                          models_data=MODELS),
            "video_xai")

    def test_recovered_from_task_state(self):
        self.assertEqual(
            generate_video.route_for_task("task_1", models_data=MODELS,
                                          task={"model": "doubao-seedance-2-0-260128"}),
            "video_volcengine")

    def test_unknown_task_asks_for_the_model(self):
        with mock.patch.object(generate_video.state_manager, "get_task", return_value=None):
            with self.assertRaises(ValueError) as cm:
                generate_video.route_for_task("task_1", models_data=MODELS)
        self.assertIn("--model", str(cm.exception))


class GetBackend(unittest.TestCase):
    def test_unknown_route_raises(self):
        with self.assertRaises(ValueError):
            generate_video.get_backend("video")  # the pre-vendor-split route name


if __name__ == "__main__":
    unittest.main()
