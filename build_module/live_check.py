"""Live end-to-end check against the real account (read-only CloudWatch/CE).

Run: uv run python build_module/live_check.py
Uses EVAL_AWS_* env vars. Small window, two regions - a few cents of API calls.
Not shipped in the exe.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bedrock_checker import config, creds, widgets
from bedrock_checker.methods import cloudwatch, cost_explorer


def main() -> int:
    cfg = config.load_config()
    kw, msg = creds.resolve(cfg)
    if kw is None:
        print(f"SKIP: {msg}")
        return 0
    print(f"credentials: {msg}")

    res = cloudwatch.scan(hours=6, regions=["us-east-1", "ap-southeast-1"],
                          cw_kwargs=kw, cfg=cfg, log=lambda m, t=None: print(m))
    assert res["status"] == "ok", res["status"]
    totals = {}
    for r in res["rows"]:
        totals[r["class"]] = totals.get(r["class"], 0.0) + r["costs"]["total"]
    print(widgets.render_rollup(totals, cfg["classes"]))

    ce = cost_explorer.report(3, "DAILY", kw, lambda m, t=None: print(m))
    if ce["status"] == "ok":
        ce_totals = {}
        for r in ce["rows"]:
            if r["class"] != "other":
                ce_totals[r["class"]] = ce_totals.get(r["class"], 0.0) + r["amount"]
        print(widgets.render_rollup(ce_totals, cfg["classes"]))
    else:
        print(f"CE: {ce['status']}")
    print("LIVE CHECK OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
