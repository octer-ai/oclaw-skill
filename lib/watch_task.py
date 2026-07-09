#!/usr/bin/env python3
"""Resume watching an async video task by task id.

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: GET <base>/videos/{id}; GET <pre-signed CDN url> (download only)
  File I/O:  writes videos to <skill-root>/videos/; updates .task-state.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_video import poll_and_download


def main():
    parser = argparse.ArgumentParser(description="Watch an octer.ai video task")
    parser.add_argument("task_id", help="Task ID (task_...)")
    parser.add_argument("--max-wait", type=int, default=600, help="poll timeout seconds")
    args = parser.parse_args()

    print(f"👀 Watching {args.task_id} ...", file=sys.stderr)
    poll_and_download(args.task_id, max_wait=args.max_wait)


if __name__ == "__main__":
    main()
