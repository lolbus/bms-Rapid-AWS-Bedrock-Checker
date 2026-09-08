"""Credential resolution.

Each credential comes from one of two places, configured in config.json:

  "credentials": {
    "access_key_id": "",                          <- paste a literal key here
    "secret_access_key": "",                      <- paste a literal secret here
    "session_token": "",                          <- optional literal
    "access_key_id_env": "EVAL_AWS_ACCESS_KEY_ID",        <- ...or name the
    "secret_access_key_env": "EVAL_AWS_SECRET_ACCESS_KEY",     system env var
    "session_token_env": "EVAL_AWS_SESSION_TOKEN"               that holds it
  }

Resolution order (first hit wins):
  1. literal keys pasted into config.json
  2. the system env vars NAMED in the *_env fields (defaults: EVAL_AWS_*)
  3. AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
  4. ambient boto3 chain (AWS profile / shared credentials / instance role)

Only the last 4 characters of an access key are ever shown. config.json may
contain secrets when mode 1 is used - treat that file as a secret.
"""
from __future__ import annotations

import os


def _mask(ak: str) -> str:
    return f"...{ak[-4:]}" if ak and len(ak) >= 4 else "(set)"


def resolve(cfg: dict | None = None, prefix: str | None = None):
    """Return (client_kwargs, source_description) or (None, error_message)."""
    cfg = cfg or {}
    prefix = prefix or cfg.get("credentials_env_prefix", "EVAL_AWS")
    block = cfg.get("credentials") or {}

    # 1. literal keys pasted into config.json
    ak = (block.get("access_key_id") or "").strip()
    sk = (block.get("secret_access_key") or "").strip()
    if ak and sk:
        kw = {"aws_access_key_id": ak, "aws_secret_access_key": sk}
        tok = (block.get("session_token") or "").strip()
        if tok:
            kw["aws_session_token"] = tok
        return kw, f"config.json pasted keys (key {_mask(ak)})"

    # 2. system env vars named by the *_env fields
    ak_name = (block.get("access_key_id_env") or "").strip() or f"{prefix}_ACCESS_KEY_ID"
    sk_name = (block.get("secret_access_key_env") or "").strip() or f"{prefix}_SECRET_ACCESS_KEY"
    tok_name = (block.get("session_token_env") or "").strip() or f"{prefix}_SESSION_TOKEN"
    ak, sk = os.getenv(ak_name), os.getenv(sk_name)
    if ak and sk:
        kw = {"aws_access_key_id": ak, "aws_secret_access_key": sk}
        tok = os.getenv(tok_name)
        if tok:
            kw["aws_session_token"] = tok
        return kw, f"env vars {ak_name} / {sk_name} (key {_mask(ak)})"

    # 3. standard AWS_* env vars
    ak = os.getenv("AWS_ACCESS_KEY_ID")
    sk = os.getenv("AWS_SECRET_ACCESS_KEY")
    if ak and sk:
        kw = {"aws_access_key_id": ak, "aws_secret_access_key": sk}
        tok = os.getenv("AWS_SESSION_TOKEN")
        if tok:
            kw["aws_session_token"] = tok
        return kw, f"AWS_* env vars (key {_mask(ak)})"

    # 4. ambient chain: shared config, instance role, etc.
    if os.getenv("AWS_PROFILE") or os.path.exists(
            os.path.expanduser("~/.aws/credentials")):
        return {}, "ambient boto3 chain (AWS profile / shared credentials)"

    return None, (
        "No credentials found. Paste keys on the Settings tab, or set the env "
        f"vars named there (default {ak_name} / {sk_name}), or AWS_*, "
        "or configure an AWS profile."
    )


def status(cfg: dict | None = None):
    kw, msg = resolve(cfg)
    return ("ok", msg) if kw is not None else ("missing", msg)
