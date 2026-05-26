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


def install_guides_dir() -> Path:
    """Output directory for generated install guide MD files.

    Checks, in order:
    1. config.json ``install_guides.directory`` override
    2. package_manager/config.toml ``[install_guides] directory``
    3. Default: ``install_guides/`` relative to project root

    Directory values containing ``..`` or absolute paths are rejected
    as a traversal guard — they fall through to the default.
    """
    def _safe_dir(path_val: str) -> Path | None:
        """Resolve a user-supplied directory value, returning None if unsafe."""
        if not path_val:
            return None
        if ".." in path_val or path_val.startswith("/"):
            return None  # reject traversal attempts
        p = PROJECT_DIR / path_val
        p.mkdir(parents=True, exist_ok=True)
        return p

    # 1. config.json override
    path = load_config().get("install_guides", {}).get("directory")
    if path is not None:
        result = _safe_dir(path)
        if result is not None:
            return result

    # The guard rejects traversal patterns — fall through to per-skill config

    # 2. Per-skill config (package_manager/config.toml)
    import tomllib
    skill_config_path = (PROJECT_DIR / "src" / "tools" / "package_manager"
                         / "config.toml")
    if skill_config_path.exists():
        try:
            sc = tomllib.loads(skill_config_path.read_text())
            path = sc.get("install_guides", {}).get("directory")
            if path is not None:
                result = _safe_dir(path)
                if result is not None:
                    return result
        except Exception:
            pass

    # 3. Default
    p = PROJECT_DIR / "install_guides"
    p.mkdir(parents=True, exist_ok=True)
    return p


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
    """Check config.json ``skills.<name>`` override. Returns True if not set.

    For per-skill enable/disable, use the skill's own ``config.toml`` file.
    This function is the main-config override — the authoritative check is
    ``_is_skill_enabled()`` in ``src.tools.__init__`` which reads per-skill config.
    """
    return bool(load_config().get("skills", {}).get(name, True))
