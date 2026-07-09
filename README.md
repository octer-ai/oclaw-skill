# oclaw-skill

Unified access to [octer.ai](https://octer.ai)'s OpenAI-compatible gateway — image generation, video generation, and chat from one CLI.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.6+-blue.svg)

## Features

- 🎨 **Image**: GPT Image 2, Gemini 3/3.1 image models (dual API routing handled automatically)
- 🎬 **Video**: Doubao Seedance 2.0 family, Grok Imagine — async tasks with auto-poll and resume
- 💬 **Chat**: GPT-5.5, Claude Opus 4.8, Gemini 3.x
- 💾 Media saved locally to `images/` / `videos/`; no cloud uploads
- 🧩 Zero dependencies beyond Python 3 stdlib

## Quick Start

```bash
git clone <repo-url> && cd oclaw-skill
chmod +x oclaw.sh lib/*.py
export OCLAW_API_KEY="sk-..."

./oclaw.sh generate-image "A red apple on a wooden table"
./oclaw.sh generate-video "a cat walking in a garden" --model doubao-seedance-2-0-mini-260615
./oclaw.sh chat "Say hello"
```

## Commands

| Command | What it does |
|---|---|
| `generate-image <prompt>` | Generate image(s); `--model`, `--aspect`, `--n` |
| `generate-video <prompt>` | Async video; `--model`, `--image` (i2v), `--duration`, `--max-wait` |
| `chat <prompt>` | Chat completion; `--model`, `--system` |
| `watch <task-id>` | Resume a video task |
| `models` | List catalog; `--json`, `--category` |
| `status` | Local task history |

## Models

See `./oclaw.sh models` for the live catalog (✓ = verified against the API).

| Category | Models |
|---|---|
| image | gpt-image-2 (default), gemini-3-pro-image-preview, gemini-3.1-flash-image-preview |
| video | doubao-seedance-2-0 (default) / -fast / -mini, grok-imagine-1.5-video |
| chat | gpt-5.5 (default), claude-opus-4-8, gemini-3-flash / 3.5-flash / 3.1-pro |

**Known gateway limitations (2026-07-09):** the test gateway accepts but ignores the
reference-image (`--image`) and `--duration` parameters for video — outputs come back
text-to-video at the default length. Flags are kept for forward-compatibility.

## Configuration

`config.json` (copy from `config.example.json`, gitignored):

```json
{
  "base_url": "https://octer.ai/v1",
  "defaults": {"image": "gpt-image-2", "video": "doubao-seedance-2-0-260128", "chat": "gpt-5.5"}
}
```

Base URL priority: `OCLAW_BASE_URL` env > `config.json` > default `https://octer.ai/v1`.

## Architecture

```
oclaw-skill/
├── oclaw.sh                 # CLI dispatcher
├── lib/
│   ├── common.py            # auth, base-url resolution, API client, data-URI decode, media I/O
│   ├── chat.py              # chat completions
│   ├── generate_image.py    # dual-route image generation
│   ├── generate_video.py    # async video: submit + poll + download
│   ├── watch_task.py        # resume video tasks
│   ├── list_models.py       # catalog printer
│   └── state_manager.py     # .task-state.json tracking
├── models.json              # model catalog + routing
└── tests/                   # unittest suite (stdlib only)
```

How routing works: each model in `models.json` carries a `route` —

| route | endpoint | image comes back as |
|---|---|---|
| `chat` | `POST /chat/completions` | (text reply) |
| `image_chat` | `POST /chat/completions` | `![image](data:image/png;base64,...)` in the message |
| `image_openai` | `POST /images/generations` | `data[].b64_json` |
| `video` | `POST /video/generations` + `GET /videos/{id}` | pre-signed MP4 URL in `metadata.url` |

## Development

```bash
python3 -m unittest discover -s tests -v
```

## Security

See the Security section in [SKILL.md](SKILL.md) for the full endpoint/data-flow manifest. Summary: prompts and optional reference images go to the configured octer.ai gateway; the API key goes only there; media is stored locally; no telemetry.

## License

MIT
