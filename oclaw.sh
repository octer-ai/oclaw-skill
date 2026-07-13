#!/bin/bash
# oclaw-skill: octer.ai API wrapper (image / video / chat)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

usage() {
  cat << 'EOF'
oclaw.sh — octer.ai API wrapper v1.0.0
Image generation, video generation, and chat via one OpenAI-compatible gateway.

USAGE:
  oclaw.sh <command> [options]

COMMANDS:
  generate-image <prompt>   Generate image(s)
  generate-video <prompt>   Generate a video (async; auto-polls until done)
  chat <prompt>             Chat completion (prints text)
  watch <task-id>           Resume watching a video task  [--model <name>]
  models                    List models  [--json] [--category image|video|chat]
  status                    Show tracked tasks
  help                      This help

IMAGE OPTIONS:
  --model <name>            default: gpt-image-2
  --aspect <ratio>          1:1 | 16:9 | 9:16 | 3:2 | 2:3
  --n <int>                 number of images (image_openai route only; default 1)

VIDEO OPTIONS:
  --model <name>            default: doubao-seedance-2-0-260128
  --image <path|url>        reference image (image-to-video; doubao-seedance only)
  --duration <sec>          requested duration
  --aspect <ratio>          e.g. 16:9 | 9:16 | 1:1
  --resolution <res>        e.g. 480p | 720p | 1080p
  --max-wait <sec>          poll timeout (default 600)

CHAT OPTIONS:
  --model <name>            default: gpt-5.5
  --system <text>           system prompt

ENVIRONMENT:
  OCLAW_API_KEY             API key (required)
  OCLAW_BASE_URL            override API base (default https://oclaw.octer.ai;
                            also settable as "base_url" in config.json)

EXAMPLES:
  oclaw.sh generate-image "a red apple on a white table"
  oclaw.sh generate-image "cyberpunk city" --model gemini-3-pro-image-preview --aspect 16:9
  oclaw.sh generate-video "a cat walking in a garden" --model doubao-seedance-2-0-mini-260615
  oclaw.sh generate-video "the apple rotates slowly" --image ./ref.png
  oclaw.sh generate-video "a red ball rolls" --model grok-imagine-video --resolution 720p
  oclaw.sh chat "explain quicksort briefly" --model claude-opus-4-8
  oclaw.sh watch task_abc123
EOF
}

case "${1:-help}" in
  generate-image)
    shift; exec python3 "$LIB_DIR/generate_image.py" "$@" ;;
  generate-video)
    shift; exec python3 "$LIB_DIR/generate_video.py" "$@" ;;
  chat)
    shift; exec python3 "$LIB_DIR/chat.py" "$@" ;;
  watch)
    shift; exec python3 "$LIB_DIR/watch_task.py" "$@" ;;
  models)
    shift; exec python3 "$LIB_DIR/list_models.py" "$@" ;;
  status)
    exec python3 "$LIB_DIR/state_manager.py" list ;;
  help|--help|-h)
    usage ;;
  *)
    echo "Error: unknown command '$1'" >&2
    echo "" >&2
    usage >&2
    exit 1 ;;
esac
