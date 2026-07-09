#!/usr/bin/env python3
"""Image generation via octer.ai (dual route, selected by models.json "route").

  image_chat   -> POST <base>/chat/completions; image comes back embedded in the
                  assistant message as ![image](data:image/<ext>;base64,...)
  image_openai -> POST <base>/images/generations; image in data[].b64_json

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: POST <base>/chat/completions, POST <base>/images/generations
  File I/O:  writes images to <skill-root>/images/
"""

import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}


def build_openai_payload(model_id, prompt, n=1, aspect=None):
    payload = {"model": model_id, "prompt": prompt, "n": n}
    if aspect:
        size = ASPECT_TO_SIZE.get(aspect)
        if size:
            payload["size"] = size
    return payload


def build_chat_payload(model_id, prompt, aspect=None):
    content = prompt
    if aspect:
        content = f"{prompt}\n\nAspect ratio: {aspect}"
    return {"model": model_id, "messages": [{"role": "user", "content": content}]}


def generate_openai(model_id, prompt, n, aspect):
    result = common.api_request("POST", "/images/generations",
                                build_openai_payload(model_id, prompt, n, aspect),
                                timeout=600)
    images = []
    for item in result.get("data") or []:
        b64 = item.get("b64_json")
        if b64:
            images.append(("png", base64.b64decode(b64)))
    return images


def generate_chat(model_id, prompt, aspect):
    result = common.api_request("POST", "/chat/completions",
                                build_chat_payload(model_id, prompt, aspect),
                                timeout=600)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("Unexpected API response:", file=sys.stderr)
        print(str(result)[:500], file=sys.stderr)
        sys.exit(1)
    images = common.extract_data_uris(content)
    if not images:
        print("No image found in the model response. The model said:", file=sys.stderr)
        print(content[:500], file=sys.stderr)
        print("(possibly a content-policy refusal — try rephrasing)", file=sys.stderr)
        sys.exit(1)
    return images


def main():
    parser = argparse.ArgumentParser(description="Generate images via octer.ai")
    parser.add_argument("prompt", help="Image prompt")
    parser.add_argument("--model", default=None, help="Image model (default from config)")
    parser.add_argument("--aspect", default=None, help="1:1 | 16:9 | 9:16 | 3:2 | 2:3")
    parser.add_argument("--n", type=int, default=1,
                        help="number of images (image_openai route only)")
    args = parser.parse_args()

    model_id, info = common.resolve_model_cli("image", args.model)
    route = info.get("route")
    print(f"🎨 Generating with {model_id} (route: {route}) ...", file=sys.stderr)

    if route == "image_openai":
        if args.aspect and args.aspect not in ASPECT_TO_SIZE:
            print(f"Warning: no size mapping for aspect {args.aspect}; using model default",
                  file=sys.stderr)
        images = generate_openai(model_id, args.prompt, args.n, args.aspect)
    elif route == "image_chat":
        if args.n != 1:
            print("Note: --n is only supported on the image_openai route; making one call",
                  file=sys.stderr)
        images = generate_chat(model_id, args.prompt, args.aspect)
    else:
        print(f"Error: unknown image route '{route}' in models.json", file=sys.stderr)
        sys.exit(1)

    if not images:
        print("No images returned", file=sys.stderr)
        sys.exit(1)

    paths = [common.save_media(raw, "images", index=i, ext=ext)
             for i, (ext, raw) in enumerate(images, 1)]
    print(f"✓ Saved {len(paths)} image(s)", file=sys.stderr)
    common.print_media(paths)


if __name__ == "__main__":
    main()
