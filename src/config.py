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
    "unified_model": None,
    "screenshots": {
        "directory": "/tmp/os-assistant/screenshots",
        "max_retention": 10,
        "unload_before_analysis": False,
    },
    "formatter": {
        "enabled": True,
    },
    "orchestrator": {
        "temperature": 0,
        "num_ctx": 32768,
        "chat_history_size": 10,
        "history_max_tokens": 2000,
        "recursion_limit": 10,
        "router_timeout": 15,
        "executor_timeout": 60,
    },
    "debug": {
        "enabled": False,
        "verbose": False,
        "log_dir": "logs",
        "retention_days": 7,
        "rotation": "10 MB",
    },
    "skills": {},
}

# Per-role defaults used by model_config() when the role key is missing.
# MUST match the models section above.
_MODEL_DEFAULTS: dict[str, dict[str, str]] = {
    "orchestrator": {"provider": "ollama", "model": "llama3.1:8b"},
    "vision": {"provider": "ollama", "model": "minicpm-v:8b"},
    "router": {"provider": "ollama", "model": "llama3.1:8b"},
}


def load_config() -> dict:
    """Read config.json from the project root, falling back to DEFAULT_CONFIG."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def bootstrap_config_if_missing() -> bool:
    """Create config.json from DEFAULT_CONFIG if it does not exist.

    Returns True if a new file was created, False otherwise.
    """
    if CONFIG_PATH.exists():
        return False
    CONFIG_PATH.write_text(
        json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n"
    )
    return True


def _normalize_model_value(val) -> dict | None:
    """Normalize a model config value to a {provider, model, ...} dict.

    Strings are treated as Ollama model names.
    Dicts are passed through with provider defaulting to 'ollama'.
    Returns None for None / empty values.
    """
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if not val:
            return None
        return {"provider": "ollama", "model": val}
    if isinstance(val, dict):
        normalized = dict(val)
        normalized.setdefault("provider", "ollama")
        return normalized
    return None


def model_config(role: str) -> dict:
    """Return the per-role provider+model config for *role*.

    Roles: ``"orchestrator"``, ``"vision"``, ``"router"``.

    Resolution order:
    1. ``models.<role>`` in config.json:
       - string  → ``{"provider": "ollama", "model": "<string>"}``
       - object  → used as-is (provider defaults to ``"ollama"``)
    2. Missing  → hardcoded Ollama default for that role

    Returns a flat dict ready to pass to ``create_llm()``.
    """
    cfg = load_config()
    val = cfg.get("models", {}).get(role)
    result = _normalize_model_value(val)
    if result is not None:
        return result
    return dict(_MODEL_DEFAULTS.get(role, _MODEL_DEFAULTS["orchestrator"]))


def unified_model_config() -> dict | None:
    """Return the unified-model config dict, or None if per-role mode is active.

    ``unified_model`` in config.json can be:
    - string  → ``{"provider": "ollama", "model": "<string>"}``
    - object  → used as-is (provider defaults to ``"ollama"``)
    - null / missing → ``None`` (per-role mode)
    """
    cfg = load_config()
    return _normalize_model_value(cfg.get("unified_model"))


def get_model(key: str, default: str = "") -> str:
    """Look up a model name from the 'models' section of the config."""
    cfg = load_config()
    return cfg.get("models", {}).get(key, default)


def unified_model() -> str | None:
    """(Deprecated) Return the shared model name when unified_model is set, else None.

    Prefer ``unified_model_config()`` which supports per-provider configuration.
    This function is kept for backward compatibility and only recognizes
    string ``unified_model`` values (Ollama only).
    """
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


def history_max_tokens() -> int:
    """Token budget for conversation history (key 'history_max_tokens'). Default 2000.

    Oldest turns are dropped when the estimated token count exceeds this value.
    Estimation uses a simple chars // 4 heuristic — accurate within ±20%.
    """
    return int(load_config().get("orchestrator", {}).get("history_max_tokens", 2000))


def recursion_limit() -> int:
    """Max LangGraph recursion steps per agent call (default 10)."""
    return int(load_config().get("orchestrator", {}).get("recursion_limit", 10))


def router_timeout() -> int:
    """Router LLM call timeout in seconds (key 'router_timeout'). Default 15."""
    return int(load_config().get("orchestrator", {}).get("router_timeout", 15))


def executor_timeout() -> int:
    """Per-agent execution timeout in seconds (key 'executor_timeout'). Default 60."""
    return int(load_config().get("orchestrator", {}).get("executor_timeout", 60))


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
