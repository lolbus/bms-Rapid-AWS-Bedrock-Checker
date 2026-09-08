"""Source smoke test: pricing classification order, CE mapping, rollup zeros.

Run: uv run python build_module/smoke_test.py
Not shipped in the exe; not part of the release.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root

from bedrock_checker import pricing, widgets, config

CASES = [
    ("us.anthropic.claude-sonnet-4-5-20250929-v1:0", "sonnet"),
    ("anthropic.claude-3-5-sonnet-20241022-v2:0", "sonnet"),
    ("global.anthropic.claude-sonnet-4-6", "sonnet"),
    ("apac.anthropic.claude-opus-4-8", "opus"),
    ("anthropic.claude-fable-5", "fable"),
    ("anthropic.claude-fable-5-1", "fable"),
    ("anthropic.claude-mythos-5-1", "mythos"),
    ("us.anthropic.claude-haiku-4-5-20251001-v1:0", "haiku"),
    ("anthropic.claude-3-haiku-20240307-v1:0", "haiku"),
    ("anthropic.claude-3-5-haiku-20241022-v1:0", "haiku"),
    ("anthropic.claude-zzz-9", None),
]


def main() -> int:
    for mid, want in CASES:
        hit = pricing.classify(mid)
        got = hit[0] if hit else None
        assert got == want, (mid, got, want)

    # legacy sonnet $6/$30 (extended access), generic sonnet $3/$15
    assert pricing.classify("anthropic.claude-3-5-sonnet-20241022-v2:0")[2]["input"] == 6.0
    assert pricing.classify("us.anthropic.claude-sonnet-4-5-20250929-v1:0")[2]["input"] == 3.0

    # global vs regional inference profile
    assert pricing.is_global_profile("global.anthropic.claude-fable-5") is True
    assert pricing.is_global_profile("us.anthropic.claude-fable-5") is False

    # Cost Explorer service-name mapping
    assert pricing.classify_ce_service("Claude Sonnet 4.5 (Amazon Bedrock Edition)") == "sonnet"
    assert pricing.classify_ce_service("Claude Fable 5 (Amazon Bedrock Edition)") == "fable"
    assert pricing.classify_ce_service("Claude Mythos 5 (Amazon Bedrock Edition)") == "mythos"
    assert pricing.classify_ce_service("Claude Haiku 4.5 (Amazon Bedrock Edition)") == "haiku"
    assert pricing.classify_ce_service("Claude Opus 4.8 (Amazon Bedrock Edition)") == "opus"
    assert pricing.classify_ce_service("Cohere Embed 3 Model - English (Amazon Bedrock Edition)") == "other"

    # cost math: 1M in + 1M out on global fable at 0% premium = $60
    rates = pricing.classify("anthropic.claude-fable-5")[2]
    c = pricing.cost_breakdown({"input": 1_000_000, "output": 1_000_000,
                                "cache_read": 0, "cache_write": 0}, rates, "5m", 0.0)
    assert abs(c["total"] - 60.0) < 1e-9, c
    # regional premium 10% -> $66
    c = pricing.cost_breakdown({"input": 1_000_000, "output": 1_000_000,
                                "cache_read": 0, "cache_write": 0}, rates, "5m", 10.0)
    assert abs(c["total"] - 66.0) < 1e-9, c

    # rollup prints zeros for all five classes
    out = widgets.render_rollup({"opus": 103.84, "fable": 0.8}, config.REQUIRED_CLASSES)
    print(out)
    assert "USD$0.00 sonnet" in out
    assert "USD$103.84 opus" in out
    assert "USD$0.80 fable" in out
    assert "USD$0.00 haiku" in out
    assert "USD$0.00 mythos" in out

    # config: malformed JSON must raise, never silently fall back
    import tempfile, pathlib
    bad = pathlib.Path(tempfile.mkdtemp()) / "config.json"
    bad.write_text("{not json", encoding="utf-8")
    try:
        config.load_config(bad)
    except config.ConfigError:
        pass
    else:
        raise AssertionError("malformed config did not raise ConfigError")
    # BOM-tainted config must parse (utf-8-sig)
    bom = pathlib.Path(tempfile.mkdtemp()) / "config.json"
    bom.write_bytes(b'\xef\xbb\xbf{"hours": 6}')
    assert config.load_config(bom)["hours"] == 6

    # --- credential resolution ------------------------------------------
    import os
    from bedrock_checker import creds

    def _clear_env():
        for name in ("EVAL_AWS_ACCESS_KEY_ID", "EVAL_AWS_SECRET_ACCESS_KEY",
                     "EVAL_AWS_SESSION_TOKEN", "AWS_ACCESS_KEY_ID",
                     "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                     "MY_BILLING_KEY", "MY_BILLING_SECRET", "AWS_PROFILE"):
            os.environ.pop(name, None)

    # Placeholder IDs deliberately avoid the AKIA/ASIA + 16-char shape and
    # 40-char base64 secret shape that GitHub secret scanning treats as AWS keys.
    _clear_env()
    # 1. literal pasted keys win over everything
    kw, src = creds.resolve({"credentials": {
        "access_key_id": "TESTKEYIDLITERAL0001",
        "secret_access_key": "test-secret-not-an-aws-key-01"}})
    assert kw["aws_access_key_id"] == "TESTKEYIDLITERAL0001" and "pasted" in src
    # 2. named env vars from the *_env fields (custom names)
    os.environ["MY_BILLING_KEY"] = "TESTKEYIDNAMEDENV002"
    os.environ["MY_BILLING_SECRET"] = "test-secret-not-an-aws-key-02"
    kw, src = creds.resolve({"credentials": {
        "access_key_id_env": "MY_BILLING_KEY",
        "secret_access_key_env": "MY_BILLING_SECRET"}})
    assert kw["aws_access_key_id"] == "TESTKEYIDNAMEDENV002" and "MY_BILLING_KEY" in src
    # 3. default EVAL_AWS_* names when no block given
    _clear_env()
    os.environ["EVAL_AWS_ACCESS_KEY_ID"] = "TESTKEYIDEVALPREFIX03"
    os.environ["EVAL_AWS_SECRET_ACCESS_KEY"] = "test-secret-not-an-aws-key-03"
    kw, src = creds.resolve({})
    assert kw["aws_access_key_id"] == "TESTKEYIDEVALPREFIX03"
    # 4. AWS_* fallback
    _clear_env()
    os.environ["AWS_ACCESS_KEY_ID"] = "TESTKEYIDAWSTDENV004"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret-not-an-aws-key-04"
    kw, src = creds.resolve({})
    assert kw["aws_access_key_id"] == "TESTKEYIDAWSTDENV004" and "AWS_*" in src
    # 5. nothing anywhere -> error (or ambient chain on machines that have one)
    _clear_env()
    kw, src = creds.resolve({})
    if os.path.exists(os.path.expanduser("~/.aws/credentials")):
        assert kw == {} and "ambient" in src
    else:
        assert kw is None and "No credentials" in src
    # 6. half-filled literal block falls through to env (no partial creds)
    os.environ["EVAL_AWS_ACCESS_KEY_ID"] = "TESTKEYIDHALFFILL005"
    os.environ["EVAL_AWS_SECRET_ACCESS_KEY"] = "test-secret-not-an-aws-key-05"
    kw, src = creds.resolve({"credentials": {"access_key_id": "TESTKEYIDONLYHALF"}})
    assert kw["aws_access_key_id"] == "TESTKEYIDHALFFILL005"
    _clear_env()

    print("SMOKE TEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
