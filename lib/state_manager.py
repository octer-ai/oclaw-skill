#!/usr/bin/env python3
"""Task state tracking for async (video) tasks: resume support + local history.

File I/O: reads/writes <skill-root>/.task-state.json only. No network.
"""

import json
import sys
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent.parent / ".task-state.json"

TERMINAL_STATUSES = ("completed", "failed")


def load_state(state_file=None):
    path = Path(state_file or STATE_FILE)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def save_state(state, state_file=None):
    path = Path(state_file or STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def add_task(task_id, prompt, model, metadata=None, state_file=None):
    state = load_state(state_file)
    now = int(time.time())
    state[task_id] = {
        "prompt": prompt,
        "model": model,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }
    save_state(state, state_file)


def update_task(task_id, status, result=None, state_file=None):
    state = load_state(state_file)
    if task_id not in state:
        return False
    state[task_id]["status"] = status
    state[task_id]["updated_at"] = int(time.time())
    if result is not None:
        state[task_id]["result"] = result
    save_state(state, state_file)
    return True


def get_task(task_id, state_file=None):
    return load_state(state_file).get(task_id)


def list_tasks(state_file=None):
    """All tasks, most recent first."""
    state = load_state(state_file)
    return sorted(state.items(), key=lambda kv: kv[1].get("created_at", 0), reverse=True)


def list_active_tasks(state_file=None):
    return [(tid, t) for tid, t in list_tasks(state_file)
            if t.get("status") not in TERMINAL_STATUSES]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        tasks = list_tasks()
        if not tasks:
            print("No tasks recorded")
            return
        active = [t for t in tasks if t[1].get("status") not in TERMINAL_STATUSES]
        print(f"Tasks: {len(tasks)} total, {len(active)} active")
        for task_id, t in tasks[:20]:
            print(f"  {task_id}  [{t.get('status', '?'):<12}] {t.get('model', '?')}  {t.get('prompt', '')[:50]}")
    elif cmd == "get" and len(sys.argv) > 2:
        task = get_task(sys.argv[2])
        if task:
            print(json.dumps(task, indent=2, ensure_ascii=False))
        else:
            print(f"Task {sys.argv[2]} not found", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage: state_manager.py [list|get <task-id>]", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
