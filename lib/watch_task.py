#!/usr/bin/env python3
"""Resume watching an async video task by task id.

Both vendors mint task_... ids, so the id alone does not say which one to poll.
The route is recovered from the model recorded in .task-state.json, or from an
explicit --model when the task is not in the local history.

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional)
  Endpoints: GET <base>/volcengine/api/v3/contents/generations/tasks/{id}
             or GET <base>/xai/v1/videos/{id} (whichever the route selects);
             GET <pre-signed CDN url> (download only)
  File I/O:  writes videos to <skill-root>/videos/; updates .task-state.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_video import poll_and_download, route_for_task


def main():
    parser = argparse.ArgumentParser(description="Watch an octer.ai video task")
    parser.add_argument("task_id", help="Task ID (task_...)")
    parser.add_argument("--model", default=None,
                        help="the model the task was submitted with "
                             "(only needed if the task is not in the local history)")
    parser.add_argument("--max-wait", type=int, default=600, help="poll timeout seconds")
    args = parser.parse_args()

    try:
        route = route_for_task(args.task_id, args.model)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"👀 Watching {args.task_id} (route: {route}) ...", file=sys.stderr)
    poll_and_download(args.task_id, route, max_wait=args.max_wait)


if __name__ == "__main__":
    main()
