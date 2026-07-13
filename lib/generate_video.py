#!/usr/bin/env python3
"""Video generation via octer.ai, in each vendor's native async-task format.

Two backends, chosen by the model's "route" in models.json:

  video_volcengine (Doubao Seedance) — Volcengine ARK
    POST <base>/volcengine/api/v3/contents/generations/tasks      -> {id}
    GET  <base>/volcengine/api/v3/contents/generations/tasks/{id} -> status
         queued|running|succeeded|failed, URL in content.video_url

  video_xai (Grok Imagine) — xAI REST
    POST <base>/xai/v1/videos/generations  -> {request_id}
    GET  <base>/xai/v1/videos/{request_id} -> status done|failed|expired,
         URL in video.url

Each backend normalises the vendor's status vocabulary to queued|running|
completed|failed so the local task state stays uniform. The MP4 is downloaded
immediately: the CDN link expires in ~24h.

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: POST/GET <base>/volcengine/api/v3/contents/generations/tasks[/{id}],
             POST <base>/xai/v1/videos/generations, GET <base>/xai/v1/videos/{id},
             GET <pre-signed CDN url> (download only, no auth sent)
  File I/O:  writes videos to <skill-root>/videos/; reads the --image file if
             given; reads/writes <skill-root>/.task-state.json
"""

import argparse
import base64
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import state_manager

MIME_BY_EXT = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "webp": "webp", "gif": "gif"}

# Vendor status -> local vocabulary. Anything unrecognised is treated as still running.
VOLC_STATUS = {"queued": "queued", "running": "running",
               "succeeded": "completed", "failed": "failed"}
XAI_STATUS = {"pending": "queued", "queued": "queued", "processing": "running",
              "done": "completed", "failed": "failed", "expired": "failed"}

XAI_RESOLUTIONS = ("480p", "720p")
XAI_MIN_DURATION, XAI_MAX_DURATION = 6, 30


def image_ref_to_value(ref):
    """--image argument -> API value: URLs pass through, local files become data URIs."""
    if re.match(r"^https?://", ref):
        return ref
    path = Path(ref)
    if not path.is_file():
        raise ValueError(f"reference image not found: {ref}")
    ext = path.suffix.lstrip(".").lower()
    mime = MIME_BY_EXT.get(ext)
    if not mime:
        raise ValueError(f"unsupported reference image type: .{ext} (use png/jpg/webp/gif)")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


# --- volcengine (Doubao Seedance) -------------------------------------------------

VOLC_TASKS = "/volcengine/api/v3/contents/generations/tasks"


def build_volc_payload(model_id, prompt, image_value=None, duration=None,
                       aspect=None, resolution=None):
    content = [{"type": "text", "text": prompt}]
    if image_value:
        content.append({"type": "image_url", "image_url": {"url": image_value}})
    payload = {"model": model_id, "content": content}
    if duration:
        payload["duration"] = duration
    if aspect:
        payload["ratio"] = aspect
    if resolution:
        payload["resolution"] = resolution
    return payload


def volc_submit(model_id, prompt, image_value=None, duration=None,
                aspect=None, resolution=None):
    result = common.api_request(
        "POST", VOLC_TASKS,
        build_volc_payload(model_id, prompt, image_value, duration, aspect, resolution),
        timeout=120)
    return result.get("id"), result


def volc_poll(task_id):
    """-> (local_status, video_url, error, progress)"""
    data = common.api_request("GET", f"{VOLC_TASKS}/{task_id}", timeout=60)
    raw = str(data.get("status", "")).lower()
    url = (data.get("content") or {}).get("video_url", "")
    error = data.get("error") or data.get("failure_reason")
    return VOLC_STATUS.get(raw, "running"), url, error, data.get("progress")


# --- xai (Grok Imagine) -----------------------------------------------------------

def build_xai_payload(model_id, prompt, duration=None, aspect=None, resolution=None):
    payload = {"model": model_id, "prompt": prompt}
    if duration:
        payload["duration"] = duration
    if aspect:
        payload["aspect_ratio"] = aspect
    if resolution:
        payload["resolution"] = resolution
    return payload


def warn_xai_limits(duration=None, resolution=None):
    """The grok upstream is an aggregator, not xAI, so some xAI-legal values get
    coerced. Say so before submitting rather than let the output surprise anyone."""
    if resolution and resolution not in XAI_RESOLUTIONS:
        print(f"Note: the grok upstream only serves {'/'.join(XAI_RESOLUTIONS)}; "
              f"{resolution} will be downgraded to 720p", file=sys.stderr)
    if duration and duration < XAI_MIN_DURATION:
        print(f"Note: the grok upstream has a {XAI_MIN_DURATION}s floor; "
              f"{duration}s will be raised to {XAI_MIN_DURATION}s", file=sys.stderr)
    if duration and duration > XAI_MAX_DURATION:
        print(f"Note: the grok upstream has a {XAI_MAX_DURATION}s ceiling; "
              f"{duration}s will be clamped to {XAI_MAX_DURATION}s", file=sys.stderr)


def xai_submit(model_id, prompt, image_value=None, duration=None,
               aspect=None, resolution=None):
    if image_value:
        raise ValueError("--image is not supported on the grok route (the upstream has "
                         "no reference-image equivalent); use a doubao-seedance model "
                         "for image-to-video")
    warn_xai_limits(duration, resolution)
    result = common.api_request(
        "POST", "/xai/v1/videos/generations",
        build_xai_payload(model_id, prompt, duration, aspect, resolution),
        timeout=120)
    return result.get("request_id"), result


def xai_poll(task_id):
    """-> (local_status, video_url, error, progress)"""
    data = common.api_request("GET", f"/xai/v1/videos/{task_id}", timeout=60)
    raw = str(data.get("status", "")).lower()
    url = (data.get("video") or {}).get("url", "")
    error = data.get("error")
    if raw == "expired" and not error:
        error = "the task expired before the video could be fetched"
    return XAI_STATUS.get(raw, "running"), url, error, data.get("progress")


BACKENDS = {
    "video_volcengine": {"submit": volc_submit, "poll": volc_poll},
    "video_xai": {"submit": xai_submit, "poll": xai_poll},
}


def get_backend(route):
    backend = BACKENDS.get(route)
    if not backend:
        raise ValueError(f"unknown video route '{route}' in models.json "
                         f"(expected one of: {', '.join(sorted(BACKENDS))})")
    return backend


def route_for_task(task_id, model_id=None, models_data=None, task=None):
    """A task id alone does not say which vendor issued it — both mint task_... ids.
    Recover the route from the model, given explicitly or recalled from local state."""
    if model_id is None:
        task = task if task is not None else state_manager.get_task(task_id)
        if not task or not task.get("model"):
            raise ValueError(
                f"{task_id} is not in the local task history, so its vendor is unknown. "
                "Re-run with --model <the model the task was submitted with>.")
        model_id = task["model"]
    models_data = models_data if models_data is not None else common.load_models()
    _model_id, info = common.resolve_model(models_data, "video", model_id,
                                           common.load_defaults())
    return info.get("route")


def submit(route, model_id, prompt, image_value=None, duration=None,
           aspect=None, resolution=None):
    task_id, raw = get_backend(route)["submit"](
        model_id, prompt, image_value, duration, aspect, resolution)
    if not task_id:
        print(f"Unexpected submit response: {str(raw)[:500]}", file=sys.stderr)
        sys.exit(1)
    return task_id


def poll_and_download(task_id, route, max_wait=600, interval=5):
    """Poll until the task finishes, then download. Exit 1 on failure, 2 on timeout."""
    poll = get_backend(route)["poll"]
    start = time.time()
    last_status = None
    while time.time() - start < max_wait:
        time.sleep(interval)
        status, url, error, progress = poll(task_id)
        if status != last_status:
            suffix = f" ({progress}%)" if progress is not None else ""
            print(f"  [{int(time.time() - start)}s] {status}{suffix}", file=sys.stderr)
            last_status = status
            state_manager.update_task(task_id, status)

        if status == "completed":
            if not url:
                print("Completed but no video URL in the response", file=sys.stderr)
                sys.exit(1)
            out_dir = common.SKILL_ROOT / "videos"
            out_dir.mkdir(exist_ok=True)
            path = out_dir / common.timestamped_name(index=1, ext="mp4")
            print("Downloading video ...", file=sys.stderr)
            common.download_file(url, path, timeout=300)
            state_manager.update_task(task_id, "completed", {"url": url, "file": str(path)})
            print("🎉 Video ready", file=sys.stderr)
            common.print_media([path])
            return [path]

        if status == "failed":
            print(f"❌ Task failed: {error or 'unknown'}", file=sys.stderr)
            state_manager.update_task(task_id, "failed", {"reason": str(error)})
            sys.exit(1)

    print(f"⏱️  Timeout after {max_wait}s; the task keeps running server-side.", file=sys.stderr)
    print(f"Resume with: ./oclaw.sh watch {task_id}", file=sys.stderr)
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Generate a video via octer.ai")
    parser.add_argument("prompt", help="Video prompt")
    parser.add_argument("--model", default=None, help="Video model (default from config)")
    parser.add_argument("--image", default=None,
                        help="reference image for image-to-video "
                             "(local path or URL; doubao-seedance only)")
    parser.add_argument("--duration", type=int, default=None, help="duration in seconds")
    parser.add_argument("--aspect", default=None, help="aspect ratio, e.g. 16:9 | 9:16 | 1:1")
    parser.add_argument("--resolution", default=None, help="e.g. 480p | 720p | 1080p")
    parser.add_argument("--max-wait", type=int, default=600, help="poll timeout seconds")
    args = parser.parse_args()

    model_id, info = common.resolve_model_cli("video", args.model)
    route = info.get("route")

    image_value = None
    if args.image:
        try:
            image_value = image_ref_to_value(args.image)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"🎬 Submitting video task ({model_id}, route: {route}) ...", file=sys.stderr)
    try:
        task_id = submit(route, model_id, args.prompt, image_value, args.duration,
                         args.aspect, args.resolution)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Task ID: {task_id}", file=sys.stderr)
    state_manager.add_task(task_id, args.prompt, model_id,
                           {"image": bool(args.image), "duration": args.duration,
                            "aspect": args.aspect, "resolution": args.resolution})

    poll_and_download(task_id, route, max_wait=args.max_wait)


if __name__ == "__main__":
    main()
