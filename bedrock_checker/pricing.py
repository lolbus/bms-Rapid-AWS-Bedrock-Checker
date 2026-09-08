"""Rate card for Claude models on AWS Bedrock (USD per 1M tokens).

Verified 2026-09-08 against public Bedrock / Anthropic pricing sources.
Cache read = 0.1x input; 5-min cache write = 1.25x input; 1-h cache write = 2x input.
Regional inference profiles carry a premium over global.* profiles (default 10%).

ORDER MATTERS: first substring hit wins, so legacy SKUs (claude-3-5-sonnet at
$6/$30 extended-access pricing) precede the generic family row, and mythos
precedes fable. A new model release that matches nothing shows up as UNMATCHED
in the Discovery tab instead of being silently mispriced.
"""
from __future__ import annotations

# (substring, class, label, input, output, cache_read, cache_write_5m, cache_write_1h)
RATE_CARD = [
    ("mythos",            "mythos", "Claude Mythos 5",             10.00, 50.00, 1.00,  12.50,  20.00),
    ("fable",             "fable",  "Claude Fable 5",              10.00, 50.00, 1.00,  12.50,  20.00),
    ("opus",              "opus",   "Claude Opus",                  5.00, 25.00, 0.50,   6.25,  10.00),
    ("claude-3-5-sonnet", "sonnet", "Claude 3.5 Sonnet (legacy)",   6.00, 30.00, 0.60,   7.50,  12.00),
    ("claude-3-sonnet",   "sonnet", "Claude 3 Sonnet (legacy)",     6.00, 30.00, 0.60,   7.50,  12.00),
    ("sonnet",            "sonnet", "Claude Sonnet",                3.00, 15.00, 0.30,   3.75,   6.00),
    ("haiku-3-5",         "haiku",  "Claude 3.5 Haiku (legacy)",    0.80,  4.00, 0.08,   1.00,   1.60),
    ("claude-3-haiku",    "haiku",  "Claude 3 Haiku (legacy)",      0.25,  1.25, 0.025,  0.3125, 0.50),
    ("haiku",             "haiku",  "Claude Haiku",                 1.00,  5.00, 0.10,   1.25,   2.00),
]

_RATE_KEYS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")


def classify(model_id: str):
    """Map a CloudWatch ModelId to (class, label, rates) or None if unmatched."""
    m = model_id.lower()
    for pattern, cls, label, i, o, cr, c5, c1h in RATE_CARD:
        if pattern in m:
            return cls, label, dict(zip(_RATE_KEYS, (i, o, cr, c5, c1h)))
    return None


def classify_ce_service(name: str):
    """Map a Cost Explorer SERVICE dimension value to a class.

    Claude-on-Bedrock bills as AWS Marketplace products named
    'Claude Sonnet 4.5 (Amazon Bedrock Edition)' etc. Returns 'other' for
    non-Claude Bedrock marketplace products (e.g. Cohere Embed), None when the
    name is not a Bedrock Edition line item at all.
    """
    n = name.lower()
    if "edition" not in n:
        return None
    for cls in ("mythos", "fable", "opus", "sonnet", "haiku"):
        if cls in n:
            return cls
    return "other"


def is_global_profile(model_id: str) -> bool:
    return model_id.lower().startswith("global.")


def cost_breakdown(tokens: dict, rates: dict, cache_ttl: str = "5m",
                   premium_pct: float = 0.0) -> dict:
    """USD cost per category for a token-totals dict."""
    mult = 1.0 + (premium_pct or 0.0) / 100.0
    cw = rates["cache_write_5m"] if cache_ttl == "5m" else rates["cache_write_1h"]
    costs = {
        "input": tokens.get("input", 0) / 1e6 * rates["input"] * mult,
        "output": tokens.get("output", 0) / 1e6 * rates["output"] * mult,
        "cache_read": tokens.get("cache_read", 0) / 1e6 * rates["cache_read"] * mult,
        "cache_write": tokens.get("cache_write", 0) / 1e6 * cw * mult,
    }
    costs["total"] = sum(costs.values())
    return costs


def apply_overrides(overrides: dict) -> None:
    """Apply config pricing_overrides: {class: {input:.., output:.., ...}}."""
    if not overrides:
        return
    global RATE_CARD
    new_card = []
    for pattern, cls, label, i, o, cr, c5, c1h in RATE_CARD:
        ov = overrides.get(cls)
        if isinstance(ov, dict):
            cur = dict(zip(_RATE_KEYS, (i, o, cr, c5, c1h)))
            for k, v in ov.items():
                if k in cur:
                    try:
                        cur[k] = float(v)
                    except (TypeError, ValueError):
                        pass
            i, o, cr, c5, c1h = (cur[k] for k in _RATE_KEYS)
        new_card.append((pattern, cls, label, i, o, cr, c5, c1h))
    RATE_CARD = new_card
