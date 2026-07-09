#!/usr/bin/env python3
"""Video generation via octer.ai (async task API).

Flow: POST <base>/video/generations -> {task_id, status: queued}
      GET  <base>/videos/{task_id}  -> status queued|in_progress|completed|failed,
                                       progress 0-100, metadata.url when completed
      download the MP4 immediately (the CDN link expires in ~24h).

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: POST <base>/video/generations, GET <base>/videos/{id},
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


def build_payload(model_id, prompt, image_value=None, duration=None):
    payload = {"model": model_id, "prompt": prompt}
    if image_value:
        payload["image"] = image_value
    if duration:
        payload["duration"] = duration
    return payload


def submit(model_id, prompt, image_value=None, duration=None):
    result = common.api_request("POST", "/video/generations",
                                build_payload(model_id, prompt, image_value, duration),
                                timeout=120)
    task_id = result.get("task_id") or result.get("id")
    if not task_id:
        print(f"Unexpected submit response: {str(result)[:500]}", file=sys.stderr)
        sys.exit(1)
    return task_id


def poll_and_download(task_id, max_wait=600, interval=5):
    """Poll until the task finishes, then download. Exit 1 on failure, 2 on timeout."""
    start = time.time()
    last_status = None
    while time.time() - start < max_wait:
        time.sleep(interval)
        data = common.api_request("GET", f"/videos/{task_id}", timeout=60)
        status = str(data.get("status", "unknown")).lower()
        progress = data.get("progress", "?")
        if status != last_status:
            print(f"  [{int(time.time() - start)}s] {status} ({progress}%)", file=sys.stderr)
            last_status = status
            state_manager.update_task(task_id, status)

        if status == "completed":
            url = (data.get("metadata") or {}).get("url", "")
            if not url:
                print("Completed but no video URL in the response:", file=sys.stderr)
                print(str(data)[:500], file=sys.stderr)
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
            reason = data.get("fail_reason") or data.get("error") or "unknown"
            print(f"❌ Task failed: {reason}", file=sys.stderr)
            state_manager.update_task(task_id, "failed", {"reason": str(reason)})
            sys.exit(1)

    print(f"⏱️  Timeout after {max_wait}s; the task keeps running server-side.", file=sys.stderr)
    print(f"Resume with: ./oclaw.sh watch {task_id}", file=sys.stderr)
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Generate a video via octer.ai")
    parser.add_argument("prompt", help="Video prompt")
    parser.add_argument("--model", default=None, help="Video model (default from config)")
    parser.add_argument("--image", default=None,
                        help="reference image for image-to-video (local path or URL)")
    parser.add_argument("--duration", type=int, default=None, help="duration in seconds")
    parser.add_argument("--max-wait", type=int, default=600, help="poll timeout seconds")
    args = parser.parse_args()

    model_id, _info = common.resolve_model_cli("video", args.model)

    image_value = None
    if args.image:
        try:
            image_value = image_ref_to_value(args.image)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        print("Note: some gateways silently ignore the reference image — "
              "verify the output actually uses it", file=sys.stderr)

    print(f"🎬 Submitting video task ({model_id}) ...", file=sys.stderr)
    task_id = submit(model_id, args.prompt, image_value, args.duration)
    print(f"Task ID: {task_id}", file=sys.stderr)
    state_manager.add_task(task_id, args.prompt, model_id,
                           {"image": bool(args.image), "duration": args.duration})

    poll_and_download(task_id, max_wait=args.max_wait)


if __name__ == "__main__":
    main()
