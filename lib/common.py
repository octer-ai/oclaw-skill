#!/usr/bin/env python3
"""Shared helpers for oclaw-skill: config, API requests, media handling.

Security manifest:
  Env vars:  OCLAW_API_KEY (required), OCLAW_BASE_URL (optional override)
  Endpoints: <base_url>/v1/* (octer.ai gateway; default https://oclaw.octer.ai)
             raw.githubusercontent.com/octer-ai/oclaw-skill/master/models.json
             (GET only; no API key, prompt, or auth header is sent)
             pre-signed CDN URLs returned by the API (GET, download only, no auth sent)
  File I/O:  writes media under <skill-root>/images/ and <skill-root>/videos/
             caches the model catalog under ~/.cache/oclaw-skill/ by default
  No data is sent to any endpoint other than those listed above.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://oclaw.octer.ai"
USER_AGENT = "oclaw-skill/1.0"  # Cloudflare 会拦默认的 Python-urllib UA(error 1010)
MODEL_CATALOG_URL = (
    "https://raw.githubusercontent.com/octer-ai/oclaw-skill/master/models.json"
)
MODEL_SYNC_INTERVAL_SECONDS = 7 * 24 * 60 * 60
MODEL_SYNC_TIMEOUT_SECONDS = 5
MODEL_CATALOG_MAX_BYTES = 1024 * 1024

KNOWN_MODEL_ROUTES = {
    "chat": {"chat"},
    "image": {"image_openai", "image_gemini"},
    "video": {"video_volcengine", "video_xai"},
}

DEFAULT_MODELS = {
    "image": "gpt-image-2",
    "video": "doubao-seedance-2-0-260128",
    "chat": "gpt-5.5",
}

_DATA_URI_RE = re.compile(r"data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)")


def load_config():
    """config.json at skill root; missing or corrupt -> {}."""
    config_path = SKILL_ROOT / "config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return {}


def resolve_base_url(env_value, config):
    """Priority: OCLAW_BASE_URL env > config.json base_url > production default.

    The base is the gateway root, not the OpenAI prefix: the gateway also serves
    /v1beta, /volcengine and /xai, and each call site supplies its own prefix.
    A trailing /v1 is dropped so bases written for the older convention still work.
    """
    url = (env_value or config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
    if url.endswith("/v1"):
        url = url[: -len("/v1")]
    return url


def base_url():
    return resolve_base_url(os.getenv("OCLAW_BASE_URL"), load_config())


def get_api_key():
    key = os.getenv("OCLAW_API_KEY")
    if not key:
        print("Error: OCLAW_API_KEY environment variable not set", file=sys.stderr)
        print('Set it with: export OCLAW_API_KEY="sk-..."', file=sys.stderr)
        sys.exit(1)
    return key


def auth_headers(key, auth="bearer"):
    """Gemini's native /v1beta route authenticates with x-goog-api-key, not Bearer."""
    if auth == "goog":
        return {"x-goog-api-key": key}
    return {"Authorization": f"Bearer {key}"}


def api_request(method, endpoint, data=None, timeout=300, auth="bearer"):
    """Authenticated JSON request to the gateway; returns parsed JSON, exits on error.

    endpoint carries its own prefix (/v1, /v1beta, /volcengine, /xai) since the
    base is the gateway root.
    """
    url = f"{base_url()}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **auth_headers(get_api_key(), auth),
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(error_body).get("error", {}).get("message", error_body)
        except (ValueError, AttributeError):
            msg = error_body
        print(f"API Error (HTTP {e.code}): {str(msg)[:500]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def _validate_model_catalog(data):
    """Reject malformed catalogs and routes this installed code cannot dispatch."""
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise ValueError("model catalog must contain a models object")
    if not isinstance(data.get("lastUpdated"), str):
        raise ValueError("model catalog must contain a lastUpdated string")

    categories = data["models"]
    if set(categories) != set(KNOWN_MODEL_ROUTES):
        raise ValueError("model catalog categories do not match this skill")
    for category, routes in KNOWN_MODEL_ROUTES.items():
        models = categories.get(category)
        if not isinstance(models, dict) or not models:
            raise ValueError("model category must be a non-empty object")
        for model_id, info in models.items():
            if not isinstance(model_id, str) or not model_id:
                raise ValueError("model ids must be non-empty strings")
            if not isinstance(info, dict) or not isinstance(info.get("name"), str):
                raise ValueError("each model must contain a name")
            if info.get("route") not in routes:
                raise ValueError("model route is not supported by this skill")
    return data


def _read_model_catalog(path):
    try:
        with open(path) as f:
            return _validate_model_catalog(json.load(f))
    except (OSError, ValueError, TypeError):
        return None


def _model_cache_dir():
    override = os.getenv("OCLAW_MODEL_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    base = Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache"
    return base / "oclaw-skill"


def _model_sync_enabled():
    value = os.getenv("OCLAW_MODEL_SYNC", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _sync_due(marker_path):
    try:
        age = time.time() - marker_path.stat().st_mtime
        return age >= MODEL_SYNC_INTERVAL_SECONDS
    except OSError:
        return True


def _mark_sync_attempt(marker_path):
    try:
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.touch()
    except OSError:
        pass


def _write_model_cache(cache_path, data):
    """Atomically replace the cache so interrupted writes cannot corrupt it."""
    temp_path = cache_path.with_name(
        ".{0}.{1}.tmp".format(cache_path.name, os.getpid())
    )
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(str(temp_path), str(cache_path))
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def _fetch_model_catalog():
    """Fetch the public catalog without forwarding gateway credentials."""
    req = urllib.request.Request(
        MODEL_CATALOG_URL,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=MODEL_SYNC_TIMEOUT_SECONDS) as resp:
        body = resp.read(MODEL_CATALOG_MAX_BYTES + 1)
    if len(body) > MODEL_CATALOG_MAX_BYTES:
        raise ValueError("remote model catalog is too large")
    return _validate_model_catalog(json.loads(body.decode("utf-8")))


def _newest_model_catalog(*catalogs):
    valid = [catalog for catalog in catalogs if catalog is not None]
    if not valid:
        raise ValueError("no valid model catalog is available")
    newest = valid[0]
    for catalog in valid[1:]:
        if catalog["lastUpdated"] >= newest["lastUpdated"]:
            newest = catalog
    return newest


def load_models(sync=True):
    """Load the newest valid bundled/cached catalog and refresh GitHub weekly."""
    bundled = _read_model_catalog(SKILL_ROOT / "models.json")
    if bundled is None:
        raise ValueError("bundled models.json is missing or invalid")

    cache_dir = _model_cache_dir()
    cache_path = cache_dir / "models.json"
    marker_path = cache_dir / ".last-model-sync"
    cached = _read_model_catalog(cache_path)
    fetched = None

    if sync and _model_sync_enabled() and _sync_due(marker_path):
        try:
            fetched = _fetch_model_catalog()
            try:
                _write_model_cache(cache_path, fetched)
            except OSError:
                pass
        except (OSError, ValueError, TypeError, UnicodeError, urllib.error.URLError):
            pass
        finally:
            _mark_sync_attempt(marker_path)

    return _newest_model_catalog(bundled, cached, fetched)


def load_defaults():
    defaults = dict(DEFAULT_MODELS)
    defaults.update(load_config().get("defaults", {}))
    return defaults


def resolve_model(models_data, category, model_id, defaults):
    """Validate model_id (or pick the category default). Returns (model_id, info).

    Raises ValueError listing available models when not found in the category.
    """
    models = models_data.get("models", {}).get(category, {})
    if model_id is None:
        model_id = defaults[category]
    if model_id not in models:
        available = ", ".join(sorted(models))
        raise ValueError(
            f"'{model_id}' is not an available {category} model. Available: {available}"
        )
    return model_id, models[model_id]


def resolve_model_cli(category, model_id):
    try:
        return resolve_model(load_models(), category, model_id, load_defaults())
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def extract_data_uris(text):
    """Extract (ext, raw_bytes) from data:image/<ext>;base64,<payload> URIs in text.

    Whitespace inside the payload is tolerated; undecodable payloads are skipped.
    """
    results = []
    for m in _DATA_URI_RE.finditer(text or ""):
        ext = m.group(1).lower()
        b64 = re.sub(r"\s+", "", m.group(2))
        try:
            raw = base64.b64decode(b64)
        except ValueError:  # binascii.Error is a ValueError subclass
            continue
        results.append((ext, raw))
    return results


def timestamped_name(index=1, ext="png"):
    """Media filename: YYYY-MM-DD-HH-MM-SS-{index}.{ext}"""
    return f"{time.strftime('%Y-%m-%d-%H-%M-%S')}-{index}.{ext}"


def save_media(raw_bytes, subdir, index=1, ext="png"):
    """Write bytes under <skill-root>/<subdir>/; returns the Path."""
    out_dir = SKILL_ROOT / subdir
    out_dir.mkdir(exist_ok=True)
    path = out_dir / timestamped_name(index, ext)
    with open(path, "wb") as f:
        f.write(raw_bytes)
    return path


def download_file(url, output_path, timeout=120):
    """Download a (pre-signed) URL to output_path. Deliberately no auth header."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        with open(output_path, "wb") as f:
            f.write(resp.read())


def print_media(paths):
    """Emit MEDIA: lines on stdout for agent consumption."""
    for p in paths:
        print(f"MEDIA: {p}")
