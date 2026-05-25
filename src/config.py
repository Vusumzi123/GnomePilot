import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_DIR / "config.json"
PROMPTS_DIR = PROJECT_DIR / "prompts"

DEFAULT_CONFIG = {
    "models": {
        "orchestrator": "llama3.1:8b",
        "vision": "minicpm-v:8b",
    },
    "orchestrator": {
        "temperature": 0,
        "chat_history_size": 10,
        "recursion_limit": 10,
    },
    "skills": {
        "application": True,
        "package_manager": True,
        "window_manager": True,
        "vision": True,
    },
}


def load_config() -> dict:
    """Read config.json from the project root, falling back to DEFAULT_CONFIG."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def get_model(key: str, default: str = "") -> str:
    """Look up a model name from the 'models' section of the config."""
    cfg = load_config()
    return cfg.get("models", {}).get(key, default)


def unified_model() -> str | None:
    """Return the shared model name when unified_model is set, else None."""
    cfg = load_config()
    val = cfg.get("unified_model")
    if val and isinstance(val, str) and val.strip():
        return val.strip()
    return None


def read_prompt(name: str, fallback: str = "") -> str:
    """Read a system prompt from prompts/<name>.md, returning fallback if missing."""
    path = PROMPTS_DIR / f"{name}.md"
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        return fallback


def get_setting(key: str, default=None):
    """Walk a dotted-key path through the config dict (e.g. 'orchestrator.temperature')."""
    cfg = load_config()
    sections = key.split(".")
    for section in sections:
        cfg = cfg.get(section, {})
        if not isinstance(cfg, dict):
            return cfg
    return cfg if cfg else default


def screenshot_dir() -> Path:
    """Storage directory for captured screenshots."""
    cfg = load_config()
    path = cfg.get("screenshots", {}).get("directory", "/tmp/os-assistant/screenshots")
    return Path(path)


def screenshot_retention() -> int:
    """Maximum number of screenshots to keep (oldest deleted first)."""
    cfg = load_config()
    return int(cfg.get("screenshots", {}).get("max_retention", 10))


def unload_before_analysis() -> bool:
    """Whether to unload other models from VRAM before running vision analysis."""
    cfg = load_config()
    return cfg.get("screenshots", {}).get("unload_before_analysis", True)


def formatter_enabled() -> bool:
    """Whether the regex-based response formatter is active."""
    cfg = load_config()
    return cfg.get("formatter", {}).get("enabled", False)


def num_ctx() -> int | None:
    """Context window size for Ollama models (None = use model default, typically 2048)."""
    cfg = load_config()
    val = cfg.get("orchestrator", {}).get("num_ctx")
    if val is not None:
        return int(val)
    return None


def chat_history_size() -> int:
    """Number of previous conversation turns to keep as context (0 = disabled)."""
    cfg = load_config()
    return int(cfg.get("orchestrator", {}).get("chat_history_size", 10))


def recursion_limit() -> int:
    """Max LangGraph recursion steps per agent call (default 10)."""
    return int(load_config().get("orchestrator", {}).get("recursion_limit", 10))


def debug_enabled() -> bool:
    """Whether the debug/logging system is active."""
    return bool(load_config().get("debug", {}).get("enabled", False))


def debug_verbose() -> bool:
    """Whether to include full LLM prompt dumps in debug output."""
    return bool(load_config().get("debug", {}).get("verbose", False))


def debug_log_dir() -> str:
    """Directory for persistent debug log files (relative to project root)."""
    return load_config().get("debug", {}).get("log_dir", "logs")


def debug_retention_days() -> int:
    """Number of days to keep rotated log files."""
    return int(load_config().get("debug", {}).get("retention_days", 7))


def debug_rotation() -> str:
    """Max log file size before rotation (e.g. '10 MB', '1 GB')."""
    return load_config().get("debug", {}).get("rotation", "10 MB")


def skill_enabled(name: str) -> bool:
    """Whether a skill module should be loaded. Defaults to True."""
    return bool(load_config().get("skills", {}).get(name, True))




