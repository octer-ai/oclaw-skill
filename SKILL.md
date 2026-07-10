---
name: oclaw
version: 1.0.0
description: |
  Unified access to octer.ai's OpenAI-compatible gateway - image generation (GPT Image 2, Gemini image models), video generation (Doubao Seedance, Grok Imagine), and chat (GPT-5.5, Claude Opus 4.8, Gemini). Local storage, async task resume, model catalog.
files:
  - "oclaw.sh"
  - "lib/*"
  - "models.json"
  - "config.example.json"
metadata:
  author: smallke
  clawdbot:
    emoji: "🐙"
    primaryEnv: OCLAW_API_KEY
    requires:
      env:
        - OCLAW_API_KEY
      bins:
        - python3
---

# oclaw — octer.ai API Wrapper

Unified access to image generation, video generation, and chat through octer.ai's OpenAI-compatible gateway.

## Features

- 🎨 **Image Generation**: GPT Image 2, Gemini 3/3.1 image models — dual API routing handled automatically
- 🎬 **Video Generation**: Doubao Seedance 2.0 (quality/fast/mini), Grok Imagine — async with auto-polling, resume via `watch`
- 💬 **Chat**: GPT-5.5, Claude Opus 4.8, Gemini 3.x
- 💾 **Local Storage**: media saved to `images/` and `videos/` before anything else
- 🔁 **Task Resume**: interrupted video tasks resumable by task id

## Quick Start

```bash
export OCLAW_API_KEY="sk-..."

./oclaw.sh generate-image "A serene Japanese garden at sunset"
./oclaw.sh generate-video "a cat walking in a garden" --model doubao-seedance-2-0-mini-260615
./oclaw.sh chat "Explain quicksort briefly" --model claude-opus-4-8
./oclaw.sh models
```

## Commands

### generate-image

```
./oclaw.sh generate-image <prompt> [--model <name>] [--aspect <ratio>] [--n <int>]
```

- default model: `gpt-image-2`
- `--aspect`: 1:1, 16:9, 9:16, 3:2, 2:3 (mapped to `size` on the openai route, appended to the prompt on the chat route)
- `--n`: image count (image_openai route only)

Output ends with `MEDIA: <path>` lines pointing at saved PNGs in `images/`.

### generate-video

```
./oclaw.sh generate-video <prompt> [--model <name>] [--image <path|url>] [--duration <sec>] [--max-wait <sec>]
```

- default model: `doubao-seedance-2-0-260128`
- `--image`: reference image for image-to-video (local file or URL)
- async: submits a task, polls until done (typically 1–3 min), downloads the MP4 to `videos/`
- on timeout the task keeps running server-side — resume with `./oclaw.sh watch <task-id>`

> **Known gateway limitation (2026-07-09):** the test gateway accepts but currently
> ignores `--image` and `--duration` (videos come back text-to-video at the default
> length). The flags are kept for forward-compatibility; a note is printed when you
> use `--image` so you remember to verify the output.

### chat

```
./oclaw.sh chat <prompt> [--model <name>] [--system <text>]
```

- default model: `gpt-5.5`; prints the reply text to stdout

### watch / status / models

```
./oclaw.sh watch <task-id> [--max-wait <sec>]   # resume a video task
./oclaw.sh status                               # local task history
./oclaw.sh models [--json] [--category image|video|chat]
```

## Configuration

Copy `config.example.json` to `config.json` (gitignored) to override defaults:

```json
{
  "base_url": "https://oclaw.octer.ai/v1",
  "defaults": {
    "image": "gpt-image-2",
    "video": "doubao-seedance-2-0-260128",
    "chat": "gpt-5.5"
  }
}
```

Base URL priority: `OCLAW_BASE_URL` env > `config.json` `base_url` > `https://oclaw.octer.ai/v1`.
Point it at a staging gateway (e.g. `https://test.octer.ai/v1`) via either mechanism.

## File Storage

```
images/YYYY-MM-DD-HH-MM-SS-{n}.png
videos/YYYY-MM-DD-HH-MM-SS-{n}.mp4
```

Both directories are gitignored. Video CDN links expire (~24h), so files are downloaded immediately on completion.

## Security

### Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `OCLAW_API_KEY` | Yes | Authenticates all requests to the octer.ai gateway |
| `OCLAW_BASE_URL` | No | Override the gateway base URL (default `https://oclaw.octer.ai/v1`) |

### External Endpoints

| Endpoint | Method | Data Sent | Used By |
|---|---|---|---|
| `<base>/chat/completions` | POST | prompt, optional system text, model | `chat.py`, `generate_image.py` (image_chat route) |
| `<base>/images/generations` | POST | prompt, model, n, size | `generate_image.py` (image_openai route) |
| `<base>/video/generations` | POST | prompt, model, optional reference image, duration | `generate_video.py` |
| `<base>/videos/{task_id}` | GET | task id | `generate_video.py`, `watch_task.py` |
| pre-signed CDN URLs | GET | — (no auth header sent) | video download |

### Data Leaving This Machine

- **Prompt text** (and optional system text) is sent to the configured octer.ai gateway.
- **Reference images** (for image-to-video) are sent to the gateway inline as base64.
- **API key** is sent as an `Authorization: Bearer` header to the gateway only — never to CDN hosts, never logged, never written to disk by this skill.
- No telemetry, analytics, or usage data is collected by this skill.

### Trust Statement

This skill sends data to one third-party service: the configured octer.ai gateway. Review that service's privacy policy before use. Generated media is stored locally only.

### Autonomous Invocation

This skill can be invoked autonomously by an agent when asked to generate images/videos or chat. It never executes on its own — it must be called explicitly.

## Troubleshooting

### "OCLAW_API_KEY not set"

```bash
export OCLAW_API_KEY="sk-..."
```

### HTTP 403 "error code: 1010"

Cloudflare blocks unknown user agents. The skill already sends `User-Agent: oclaw-skill/1.0`; if you still see 1010, your network may be blocked — try from another network.

### Video timeout

The task keeps running server-side. Resume with:

```bash
./oclaw.sh watch <task-id>
```

Find the task id with `./oclaw.sh status`.

### "No image found in the model response"

The image model replied with text instead of an image — usually a content-policy refusal. Rephrase the prompt.

## License

MIT
