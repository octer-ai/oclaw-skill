#!/usr/bin/env python3
"""Chat completion via the octer.ai gateway.

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: POST <base>/v1/chat/completions (sends prompt + optional system text)
  File I/O:  none
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def build_messages(prompt, system=None):
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return messages


def main():
    parser = argparse.ArgumentParser(description="Chat with a model via octer.ai")
    parser.add_argument("prompt", help="User prompt")
    parser.add_argument("--model", default=None, help="Chat model (default from config)")
    parser.add_argument("--system", default=None, help="Optional system prompt")
    args = parser.parse_args()

    model_id, _info = common.resolve_model_cli("chat", args.model)
    print(f"💬 {model_id} ...", file=sys.stderr)

    result = common.api_request(
        "POST", "/v1/chat/completions",
        {"model": model_id, "messages": build_messages(args.prompt, args.system)},
        timeout=300,
    )
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        print("Unexpected API response:", file=sys.stderr)
        print(str(result)[:500], file=sys.stderr)
        sys.exit(1)
    print(content)


if __name__ == "__main__":
    main()
