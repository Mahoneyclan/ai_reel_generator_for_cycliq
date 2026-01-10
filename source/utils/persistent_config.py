# source/utils/persistent_config.py
"""
Persistent user configuration storage.
Stores ALL user preferences that should persist across sessions.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

# Store config in user's home directory
USER_CONFIG_PATH = Path.home() / ".cycliq_reel_generator" / "config.json"


def _serialize_value(value: Any) -> Any:
    """Convert Python objects to JSON-serializable values."""
    if isinstance(value, Path):
        return str(value)
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_serialize_value(v) for v in value]
    elif isinstance(value, tuple):
        return [_serialize_value(v) for v in value]
    else:
        return value


def _deserialize_value(value: Any, original_type: Any = None) -> Any:
    """Convert JSON values back to Python objects."""
    # Don't try to convert None
    if value is None:
        return None
    
    # If we know it should be a Path, convert it
    if original_type is Path or (isinstance(value, str) and ('/' in value or '\\' in value)):
        # Only convert to Path if it looks like a path
        if isinstance(value, str) and (value.startswith('/') or value.startswith('~') or ':' in value):
            return Path(value)
    
    return value


def load_persistent_config() -> Dict[str, Any]:
    """Load persistent user configuration."""
    if not USER_CONFIG_PATH.exists():
        return {}
    
    try:
        with USER_CONFIG_PATH.open('r') as f:
            config = json.load(f)
        
        # Convert certain known path fields
        path_fields = [
            'PROJECTS_ROOT', 'INPUT_BASE_DIR', 'PROJECT_ROOT',
            'INPUT_DIR', 'INPUT_VIDEOS_DIR', 'INPUT_GPX_FILE',
            'MUSIC_DIR', 'INTRO_MUSIC', 'OUTRO_MUSIC', 'ASSETS_DIR'
        ]
        
        for field in path_fields:
            if field in config and config[field]:
                config[field] = Path(config[field])
        
        return config
    except Exception as e:
        print(f"Warning: Failed to load persistent config: {e}")
        return {}


def save_persistent_config(config: Dict[str, Any]) -> None:
    """Save persistent user configuration.

    Merges provided config with existing config, so different windows
    can save their own settings without overwriting each other.
    """
    # Ensure directory exists
    USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config and merge with new values
    existing_config = load_persistent_config()

    # Convert existing Path objects back to strings for merging
    existing_serialized = {
        key: _serialize_value(value)
        for key, value in existing_config.items()
    }

    # Convert new values to JSON-serializable format
    new_serialized = {
        key: _serialize_value(value)
        for key, value in config.items()
    }

    # Merge: new values override existing
    merged_config = {**existing_serialized, **new_serialized}

    # Clean up stale dotted keys (e.g., SCORE_WEIGHTS.xxx) that should be nested
    stale_keys = [k for k in merged_config if '.' in k]
    for key in stale_keys:
        del merged_config[key]

    try:
        with USER_CONFIG_PATH.open('w') as f:
            json.dump(merged_config, f, indent=2, sort_keys=True)
        # Do not print success messages to stdout; saving is silent.
    except Exception as e:
        print(f"Error: Failed to save persistent config: {e}")
        raise


def get_persistent_value(key: str, default: Any = None) -> Any:
    """Get a single persistent config value."""
    config = load_persistent_config()
    return config.get(key, default)


def clear_persistent_config() -> None:
    """Clear all persistent configuration (reset to defaults)."""
    if USER_CONFIG_PATH.exists():
        USER_CONFIG_PATH.unlink()
        # Clearing config is silent.


def reload_all_config() -> None:
    """
    Reload persistent config and reset all cached config values.

    Call this after saving settings to ensure pipeline uses new values
    without requiring application restart.
    """
    # Reload the global config in config.py
    from ..config import reload_config
    reload_config()

    # Reset the CameraRegistry singleton
    from ..models.camera_registry import reset_registry
    reset_registry()