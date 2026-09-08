"""Config loading/saving for bedrock_checker.

Hard rules (workplan section 4):
- config.json is read as utf-8-sig (Notepad and PowerShell 5.1 both add BOMs)
  and written BOM-free.
- A malformed config is a hard error, NEVER a silent fallback to defaults:
  a fallback would report a busy account as idle.
- Credentials are never stored here.
- The five report classes are always present even if the operator deletes one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REQUIRED_CLASSES = ["sonnet", "opus", "fable", "haiku", "mythos"]

DEFAULTS = {
    "hours": 24,
    "days": 8,
    "regions": ["us-east-1", "ap-southeast-1"],
    "auto_discover_regions": False,
    "classes": list(REQUIRED_CLASSES),
    "cache_write_ttl": "5m",
    "regional_premium_pct": 10,
    "calibration_lookback_days": 10,
    "calibration_skip_recent_days": 2,
    "cloudwatch_period_s": 3600,
    "request_timeout_s": 20,
    "max_worker_threads": 6,
    "credentials_env_prefix": "EVAL_AWS",
    # Each credential is EITHER a literal value you paste in, OR (via the *_env
    # fields) the name of a system environment variable that holds it. Literal
    # fields win when non-empty. config.json may therefore contain secrets -
    # it is gitignored here; do not share it.
    "credentials": {
        "access_key_id": "",
        "secret_access_key": "",
        "session_token": "",
        "access_key_id_env": "EVAL_AWS_ACCESS_KEY_ID",
        "secret_access_key_env": "EVAL_AWS_SECRET_ACCESS_KEY",
        "session_token_env": "EVAL_AWS_SESSION_TOKEN",
    },
    "pricing_overrides": {},
}

_COMMENT = ("Credentials: paste literal keys into credentials.access_key_id / "
            "secret_access_key, or leave them empty to read the env vars named "
            "in the *_env fields. config.json may contain secrets - do not share it.")


class ConfigError(Exception):
    """Raised when config.json exists but cannot be parsed or is invalid."""


def app_dir() -> Path:
    """Directory that owns runtime data. run_exe.py sets APP_DIR when frozen."""
    base = os.environ.get("APP_DIR")
    if base:
        return Path(base)
    return Path.cwd()


def config_path() -> Path:
    return app_dir() / "config.json"


def load_config(path: Path | None = None) -> dict:
    p = path or config_path()
    cfg = dict(DEFAULTS)
    if p.exists():
        try:
            text = p.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ConfigError(f"cannot read {p}: {exc}") from exc
        try:
            user = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"{p} is not valid JSON: {exc}. "
                "Fix the file or delete it to regenerate defaults."
            ) from exc
        if not isinstance(user, dict):
            raise ConfigError(f"{p} must contain a JSON object at the top level.")
        cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
    # The report classes are always present, canonical order first.
    classes = list(REQUIRED_CLASSES)
    for c in cfg.get("classes") or []:
        if c not in classes:
            classes.append(c)
    cfg["classes"] = classes
    if cfg.get("cache_write_ttl") not in ("5m", "1h"):
        raise ConfigError(
            f"cache_write_ttl must be '5m' or '1h', got {cfg.get('cache_write_ttl')!r}")
    if not isinstance(cfg.get("regions"), list):
        raise ConfigError("regions must be a JSON list of region names.")
    if not isinstance(cfg.get("credentials"), dict):
        raise ConfigError("credentials must be a JSON object.")
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> Path:
    p = path or config_path()
    payload = {"_comment": _COMMENT}
    payload.update({k: v for k, v in cfg.items() if not k.startswith("_")})
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")  # BOM-free
    return p
