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
./oclaw.sh generate-video <prompt> [--model <name>] [--image <path|url>] [--duration <sec>]
                                   [--aspect <ratio>] [--resolution <res>] [--max-wait <sec>]
```

- default model: `doubao-seedance-2-0-260128`
- `--image`: reference image for image-to-video (local file or URL) — **doubao-seedance only**; the grok route rejects it rather than silently dropping it
- async: submits a task, polls until done (typically 1–3 min), downloads the MP4 to `videos/`
- on timeout the task keeps running server-side — resume with `./oclaw.sh watch <task-id>`

Each model speaks its vendor's own async-task format, and the two differ in every
respect that matters — submit body, status vocabulary, and where the URL lands:

| | doubao-seedance (`video_volcengine`) | grok (`video_xai`) |
|---|---|---|
| submit | `POST /volcengine/api/v3/contents/generations/tasks` → `{id}` | `POST /xai/v1/videos/generations` → `{request_id}` |
| poll | `GET .../tasks/{id}` | `GET /xai/v1/videos/{id}` |
| terminal status | `succeeded` / `failed` | `done` / `failed` / `expired` |
| video URL | `content.video_url` | `video.url` |

Both are normalised to `queued`/`running`/`completed`/`failed` in the local task state.

> **Grok upstream limits:** the grok channel is served by an aggregator rather than
> xAI itself, so some xAI-legal values get coerced — `1080p` is downgraded to `720p`,
> and duration is clamped into 6–30s. The skill warns before submitting instead of
> letting the output surprise you.

### chat

```
./oclaw.sh chat <prompt> [--model <name>] [--system <text>]
```

- default model: `gpt-5.5`; prints the reply text to stdout

### watch / status / models

```
./oclaw.sh watch <task-id> [--model <name>] [--max-wait <sec>]   # resume a video task
./oclaw.sh status                                                # local task history
./oclaw.sh models [--json] [--category image|video|chat]
```

Both vendors mint `task_...` ids, so `watch` recovers the vendor from the model
recorded in `.task-state.json`. Pass `--model` if the task isn't in the local history.

## Configuration

Copy `config.example.json` to `config.json` (gitignored) to override defaults:

```json
{
  "base_url": "https://oclaw.octer.ai",
  "defaults": {
    "image": "gpt-image-2",
    "video": "doubao-seedance-2-0-260128",
    "chat": "gpt-5.5"
  }
}
```

Base URL priority: `OCLAW_BASE_URL` env > `config.json` `base_url` > `https://oclaw.octer.ai`.
Point it at a staging gateway (e.g. `https://test.octer.ai`) via either mechanism.

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
| `OCLAW_BASE_URL` | No | Override the gateway base URL (default `https://oclaw.octer.ai`) |

### External Endpoints

| Endpoint | Method | Auth | Data Sent | Used By |
|---|---|---|---|---|
| `<base>/v1/chat/completions` | POST | Bearer | prompt, optional system text, model | `chat.py` |
| `<base>/v1/images/generations` | POST | Bearer | prompt, model, n, size | `generate_image.py` (image_openai) |
| `<base>/v1beta/models/{model}:generateContent` | POST | `x-goog-api-key` | prompt, response modalities | `generate_image.py` (image_gemini) |
| `<base>/volcengine/api/v3/contents/generations/tasks` | POST | Bearer | prompt, model, optional reference image, duration, ratio, resolution | `generate_video.py` (video_volcengine) |
| `<base>/volcengine/api/v3/contents/generations/tasks/{id}` | GET | Bearer | task id | `generate_video.py`, `watch_task.py` |
| `<base>/xai/v1/videos/generations` | POST | Bearer | prompt, model, duration, aspect ratio, resolution | `generate_video.py` (video_xai) |
| `<base>/xai/v1/videos/{request_id}` | GET | Bearer | task id | `generate_video.py`, `watch_task.py` |
| pre-signed CDN URLs | GET | — (no auth header sent) | — | video download |

All of the above are paths on the single configured gateway host. The API key is sent
as `Authorization: Bearer` everywhere except the Gemini-native image route, which the
gateway authenticates with `x-goog-api-key` — the same key, a different header.

### Data Leaving This Machine

- **Prompt text** (and optional system text) is sent to the configured octer.ai gateway.
- **Reference images** (for image-to-video) are sent to the gateway inline as base64.
- **API key** is sent to the gateway only (as `Authorization: Bearer`, or as `x-goog-api-key` on the Gemini-native image route) — never to CDN hosts, never logged, never written to disk by this skill.
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
