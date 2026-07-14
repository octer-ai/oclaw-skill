#!/usr/bin/env python3
"""Image generation via octer.ai (dual route, selected by models.json "route").

  image_openai -> POST <base>/v1/images/generations; image in data[].b64_json
  image_gemini -> POST <base>/v1beta/models/{model}:generateContent (Gemini's native
                  format, x-goog-api-key auth); image bytes in
                  candidates[].content.parts[].inlineData.data

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: POST <base>/v1/images/generations,
             POST <base>/v1beta/models/{model}:generateContent
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


def build_gemini_payload(prompt, aspect=None):
    """Gemini native generateContent. The model only emits an image when IMAGE is
    among the requested response modalities."""
    text = f"{prompt}\n\nAspect ratio: {aspect}" if aspect else prompt
    return {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }


def extract_inline_images(result):
    """(ext, raw_bytes) for every inline image part of a generateContent response.

    The REST API returns camelCase (inlineData/mimeType); snake_case is accepted too
    because the Python SDK surfaces it that way.
    """
    images = []
    for candidate in result.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        for part in parts:
            blob = part.get("inlineData") or part.get("inline_data")
            if not blob:
                continue
            data = blob.get("data")
            if not data:
                continue
            mime = blob.get("mimeType") or blob.get("mime_type") or "image/png"
            ext = mime.split("/")[-1].lower() or "png"
            try:
                images.append((ext, base64.b64decode(data)))
            except ValueError:
                continue
    return images


def gemini_text(result):
    """Any text parts — used to explain an image-less response (e.g. a policy refusal)."""
    chunks = []
    for candidate in result.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts")) or []
        chunks.extend(p["text"] for p in parts if p.get("text"))
    return "\n".join(chunks)


def generate_openai(model_id, prompt, n, aspect):
    result = common.api_request("POST", "/v1/images/generations",
                                build_openai_payload(model_id, prompt, n, aspect),
                                timeout=600)
    images = []
    for item in result.get("data") or []:
        b64 = item.get("b64_json")
        if b64:
            images.append(("png", base64.b64decode(b64)))
    return images


def generate_gemini(model_id, prompt, aspect):
    result = common.api_request("POST", f"/v1beta/models/{model_id}:generateContent",
                                build_gemini_payload(prompt, aspect),
                                timeout=600, auth="goog")
    images = extract_inline_images(result)
    if not images:
        said = gemini_text(result)
        print("No image found in the model response. The model said:", file=sys.stderr)
        print((said or str(result))[:500], file=sys.stderr)
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
    elif route == "image_gemini":
        if args.n != 1:
            print("Note: --n is only supported on the image_openai route; making one call",
                  file=sys.stderr)
        images = generate_gemini(model_id, args.prompt, args.aspect)
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
