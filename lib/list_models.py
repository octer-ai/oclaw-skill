#!/usr/bin/env python3
"""Print the model catalog from models.json. Local file only, no network."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common


def format_catalog(data, category=None):
    lines = [f"📊 oclaw models (updated {data.get('lastUpdated', '?')})"]
    categories = data.get("models", {})
    if category:
        if category not in categories:
            raise ValueError(f"Unknown category '{category}'. Available: {', '.join(categories)}")
        categories = {category: categories[category]}
    for cat, models in categories.items():
        lines.append("")
        lines.append(f"{cat.upper()}:")
        for model_id, info in models.items():
            tested = "✓" if info.get("tested") else " "
            lines.append(f"  [{tested}] {model_id:<35} route={info.get('route', '?')}")
    lines.append("")
    lines.append("✓ = tested against the live API")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="List available models")
    parser.add_argument("--json", action="store_true", help="Print raw models.json")
    parser.add_argument("--category", default=None, help="image | video | chat")
    args = parser.parse_args()

    data = common.load_models()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    try:
        print(format_catalog(data, args.category))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
