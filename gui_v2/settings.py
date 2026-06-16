# SPDX-License-Identifier: GPL-3.0-or-later
"""Persisted UI settings (JSON under config/, survives reinstalls)."""

import json
import os
import sys
import logging
from typing import Any

_log = logging.getLogger(__name__)


def _config_dir() -> str:
    """Writable v2 config dir. Frozen: %LOCALAPPDATA%\\WorkerBee\\config
    (bundle is not a safe write target). Dev: the repo's config/."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "WorkerBee", "config")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def _bundled_config_path(filename: str):
    """Read-only bundled defaults for first run; None outside a frozen build."""
    mei = getattr(sys, "_MEIPASS", None)
    return os.path.join(mei, "config", filename) if mei else None


_CONFIG_DIR = _config_dir()
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "v2_ui.json")
_log.info("v2 settings dir: %s", _CONFIG_DIR)


def _ensure_dir():
    os.makedirs(_CONFIG_DIR, exist_ok=True)


def _read_json_dict(path):
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def load_settings() -> dict[str, Any]:
    data = _read_json_dict(_CONFIG_PATH)
    if data is not None:
        return data
    # First run: fall back to bundled defaults.
    data = _read_json_dict(_bundled_config_path("v2_ui.json"))
    return data if data is not None else {}


def save_settings(updates: dict[str, Any]) -> None:
    """Merge updates into the existing file and rewrite atomically."""
    current = load_settings()
    current.update(updates)
    try:
        _ensure_dir()
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        os.replace(tmp, _CONFIG_PATH)
    except OSError as exc:
        # Never crash over persistence, but log so a broken save is diagnosable.
        _log.warning("settings save failed (%s): %s", _CONFIG_PATH, exc)


def load_section(name: str) -> dict[str, Any]:
    """Return one named section (e.g. 'mirror'), or an empty dict if absent."""
    sec = load_settings().get(name)
    return sec if isinstance(sec, dict) else {}


def save_section(name: str, data: dict[str, Any]) -> None:
    """Persist one named section, replacing it wholesale."""
    save_settings({name: data})


def get_splash_size(default_w: int, default_h: int) -> tuple[int, int]:
    """Persisted splash size, or the supplied defaults."""
    s = load_settings()
    try:
        return int(s.get("splash_width", default_w)), \
            int(s.get("splash_height", default_h))
    except (TypeError, ValueError):
        return default_w, default_h


def set_splash_size(w: int, h: int) -> None:
    save_settings({"splash_width": int(w), "splash_height": int(h)})


def replace_all_settings(data: dict[str, Any]) -> None:
    """Overwrite the active settings file. Pages must re-read afterwards."""
    if not isinstance(data, dict):
        return
    try:
        _ensure_dir()
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _CONFIG_PATH)
    except OSError as exc:
        _log.warning("settings replace failed (%s): %s", _CONFIG_PATH, exc)


# Named configs: a full snapshot of active settings, stored by name. Kept in
# a separate file so snapshots never nest.
_CONFIGS_PATH = os.path.join(_CONFIG_DIR, "v2_configs.json")
_EXPORT_TAG = "workerbee_config_v2"   # single-file export format marker


def _load_configs() -> dict[str, Any]:
    data = _read_json_dict(_CONFIGS_PATH)
    if data is not None:
        return data
    data = _read_json_dict(_bundled_config_path("v2_configs.json"))
    return data if data is not None else {}


def _save_configs(configs: dict[str, Any]) -> None:
    try:
        _ensure_dir()
        tmp = _CONFIGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=2)
        os.replace(tmp, _CONFIGS_PATH)
    except OSError as exc:
        _log.warning("configs save failed (%s): %s", _CONFIGS_PATH, exc)


def list_configs() -> list[str]:
    return sorted(_load_configs().keys(), key=str.lower)


def save_config(name: str) -> None:
    """Snapshot active settings under `name` (overwrites)."""
    name = (name or "").strip()
    if not name:
        return
    configs = _load_configs()
    configs[name] = load_settings()
    _save_configs(configs)


def load_config(name: str) -> bool:
    """Make the named config active. Returns True on success."""
    configs = _load_configs()
    if name not in configs:
        return False
    replace_all_settings(dict(configs[name]))
    return True


def delete_config(name: str) -> None:
    configs = _load_configs()
    if configs.pop(name, None) is not None:
        _save_configs(configs)


def export_config_to(name: str, path: str) -> bool:
    """Write one config to a JSON file. Falls back to live settings if
    `name` is not a saved config."""
    configs = _load_configs()
    settings = configs.get(name) if name in configs else load_settings()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": _EXPORT_TAG, "name": name,
                       "settings": settings}, f, indent=2)
        return True
    except OSError as exc:
        _log.warning("config export failed (%s): %s", path, exc)
        return False


def import_config_from(path: str) -> str | None:
    """Import an exported config file and store it as a named config.
    Accepts both the export format and a raw settings dict. Returns the
    imported name, or None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    if doc.get("format") == _EXPORT_TAG:
        settings = doc.get("settings", {})
        name = doc.get("name") or os.path.splitext(os.path.basename(path))[0]
    else:
        settings = doc  # raw settings snapshot
        name = os.path.splitext(os.path.basename(path))[0]
    if not isinstance(settings, dict):
        return None
    configs = _load_configs()
    configs[name] = settings
    _save_configs(configs)
    return name


